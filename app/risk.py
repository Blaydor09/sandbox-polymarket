import os
import json
import datetime
import logging
import uuid
from typing import Dict, Any, List
from app.event_bus import bus
from app.config import (
    MAX_EXPOSURE_USD,
    MAX_DAILY_LOSS_USD,
    LOOP_TIME_WINDOW_SEC,
    LOOP_MAX_ORDERS,
    RISK_STATE_FILE,
    INITIAL_PORTFOLIO_USD
)

logger = logging.getLogger("RiskEngine")

class RiskEngine:
    def __init__(self):
        self.state_file = RISK_STATE_FILE
        self.global_circuit_breaker = False
        self.agent_daily_loss: Dict[str, float] = {}       # agentId -> loss in USD
        self.agent_exposure: Dict[str, float] = {}         # agentId -> exposure in USD
        self.recent_orders: List[Dict[str, Any]] = []      # Lista de timestamps de órdenes para loop detection
        self.load_state()

    def load_state(self) -> None:
        """Carga el estado del motor de riesgo desde el archivo JSON de persistencia."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                    self.global_circuit_breaker = state.get("global_circuit_breaker", False)
                    self.agent_daily_loss = state.get("agent_daily_loss", {})
                    self.agent_exposure = state.get("agent_exposure", {})
                    # Limpiamos el historial de órdenes al reiniciar
                    self.recent_orders = []
                logger.info("Estado del Risk Engine cargado correctamente.")
            except Exception as e:
                logger.error(f"Error cargando estado de riesgo: {e}")
                self.global_circuit_breaker = False
        else:
            self.save_state()

    def save_state(self) -> None:
        """Guarda el estado actual del motor de riesgo en disco."""
        try:
            state = {
                "global_circuit_breaker": self.global_circuit_breaker,
                "agent_daily_loss": self.agent_daily_loss,
                "agent_exposure": self.agent_exposure,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error persistiendo estado de riesgo: {e}")

    def update_exposure(self, agent_id: str, amount_usd: float) -> None:
        """Actualiza la exposición activa de un agente y persiste el estado."""
        current = self.agent_exposure.get(agent_id, 0.0)
        self.agent_exposure[agent_id] = round(current + amount_usd, 4)
        self.save_state()

    def add_loss(self, agent_id: str, loss_usd: float) -> None:
        """Registra una pérdida (drawdown) diaria para el agente y verifica el límite."""
        current = self.agent_daily_loss.get(agent_id, 0.0)
        new_loss = round(current + loss_usd, 4)
        self.agent_daily_loss[agent_id] = new_loss
        logger.info(f"Pérdida registrada para {agent_id}: +{loss_usd} USD. Pérdida acumulada diaria: {new_loss} USD.")
        
        if new_loss >= MAX_DAILY_LOSS_USD:
            self.global_circuit_breaker = True
            logger.warning(
                f"[CIRCUIT BREAKER] Límite de pérdida diaria excedido para {agent_id} ({new_loss} >= {MAX_DAILY_LOSS_USD} USD). "
                "Cerrando operativa global."
            )
        self.save_state()

    def check_loop_detection(self, agent_id: str, market_address: str, outcome_index: int) -> bool:
        """
        Algoritmo de Detección de Bucles Infinitos en Ventana Deslizante.
        Si hay más de LOOP_MAX_ORDERS órdenes en los últimos LOOP_TIME_WINDOW_SEC segundos
        para el mismo agente, mercado y outcome, dispara el circuit breaker.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(seconds=LOOP_TIME_WINDOW_SEC)
        
        # Limpiar registros antiguos fuera de la ventana deslizante
        self.recent_orders = [o for o in self.recent_orders if datetime.datetime.fromisoformat(o["timestamp"]) > cutoff]
        
        # Contar órdenes que coinciden con los criterios del bucle
        matches = [
            o for o in self.recent_orders 
            if o["agentId"] == agent_id 
            and o["marketAddress"] == market_address 
            and o["outcomeIndex"] == outcome_index
        ]
        
        # Agregar orden actual al historial
        self.recent_orders.append({
            "timestamp": now.isoformat(),
            "agentId": agent_id,
            "marketAddress": market_address,
            "outcomeIndex": outcome_index
        })
        
        if len(matches) >= LOOP_MAX_ORDERS:
            logger.critical(
                f"[LOOP DETECTED] Agente {agent_id} ejecutó {len(matches) + 1} órdenes consecutivas "
                f"en el mercado {market_address} para el outcome {outcome_index} "
                f"dentro de {LOOP_TIME_WINDOW_SEC} segundos. ¡Disparando Circuit Breaker!"
            )
            self.global_circuit_breaker = True
            self.save_state()
            return True
            
        return False

    async def validate_order(self, event_data: Dict[str, Any]) -> None:
        """
        Manejador del evento strategy.order.validated.
        Aplica límites de exposición, drawdown diario y detección de loops.
        """
        correlation_id = event_data.get("correlationId")
        payload = event_data.get("payload", {})
        
        order_id = payload.get("orderId")
        agent_id = payload.get("agentId")
        market_address = payload.get("marketAddress")
        outcome_index = payload.get("outcomeIndex")
        amount_usd = payload.get("amountUsd", 0.0)

        logger.info(f"Evaluando riesgos para orden {order_id}. correlationId={correlation_id}")

        # 1. Chequear Circuit Breaker Global
        if self.global_circuit_breaker:
            await self._reject(order_id, correlation_id, "CIRCUIT_BREAKER_ACTIVE_GLOBAL", payload)
            return

        # 2. Chequear Exposición Máxima por Orden
        if amount_usd > MAX_EXPOSURE_USD:
            await self._reject(
                order_id, 
                correlation_id, 
                f"EXPOSURE_LIMIT_EXCEEDED: Operación de {amount_usd} USD supera el límite de {MAX_EXPOSURE_USD} USD",
                payload
            )
            return

        # 3. Chequear Drawdown acumulado diario (basado en el NAV real de la cartera)
        from app.portfolio import portfolio_manager
        current_nav = portfolio_manager.get_net_asset_value()
        current_loss = max(0.0, INITIAL_PORTFOLIO_USD - current_nav)
        
        if current_loss >= MAX_DAILY_LOSS_USD:
            self.global_circuit_breaker = True
            self.save_state()
            await self._reject(
                order_id, 
                correlation_id, 
                f"DAILY_DRAWDOWN_LIMIT_EXCEEDED: Pérdida real de {current_loss:.2f} USD supera el límite de {MAX_DAILY_LOSS_USD} USD (NAV={current_nav:.2f} USD)", 
                payload
            )
            return

        # 4. Chequear Loop Detection
        if self.check_loop_detection(agent_id, market_address, outcome_index):
            await self._reject(order_id, correlation_id, "RUNAWAY_AGENT_LOOP_DETECTED", payload)
            return

        # Si pasa todas las validaciones de riesgo
        logger.info(f"Riesgo Aprobado para orden {order_id}. correlationId={correlation_id}")
        
        # Aumentar la exposición activa de forma temporal (se reduce cuando se procesa el fill o la pérdida)
        self.update_exposure(agent_id, amount_usd)

        approval_event = {
            "eventId": f"evt_{uuid.uuid4()}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0.0",
            "correlationId": correlation_id,
            "payload": {
                "orderId": order_id,
                "agentId": agent_id,
                "marketAddress": market_address,
                "outcomeIndex": outcome_index,
                "side": payload.get("side"),
                "sizeTokens": payload.get("sizeTokens"),
                "amountUsd": amount_usd,
                "limitPrice": payload.get("limitPrice"),
                "slippageTolerancePct": payload.get("slippageTolerancePct"),
                "strategyId": payload.get("strategyId"),
                "reasoning": payload.get("reasoning"),
                "riskDecision": "APPROVED",
                "circuitBreakersStatus": {
                    "globalStopActive": self.global_circuit_breaker,
                    "currentDailyLoss": current_loss
                }
            }
        }
        from app.config import SUPERVISION_ENABLED
        if SUPERVISION_ENABLED:
            logger.info(f"Supervisión activada. Publicando orden {order_id} a cola de supervisión humana.")
            await bus.publish("risk.order.pending_approval", approval_event)
        else:
            logger.info(f"Supervisión desactivada. Enviando orden {order_id} directamente a ejecución.")
            await bus.publish("risk.order.approved", approval_event)

    async def _reject(self, order_id: str, correlation_id: str, reason: str, original_payload: Dict[str, Any]) -> None:
        """Emite evento de rechazo en el Event Bus."""
        logger.warning(f"Orden {order_id} rechazada por motor de riesgo. Razón: {reason}. correlationId={correlation_id}")
        
        rejection_event = {
            "eventId": f"evt_{uuid.uuid4()}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0.0",
            "correlationId": correlation_id,
            "payload": {
                "orderId": order_id,
                "agentId": original_payload.get("agentId"),
                "marketAddress": original_payload.get("marketAddress"),
                "riskDecision": "REJECTED",
                "reason": reason,
                "circuitBreakersStatus": {
                    "globalStopActive": self.global_circuit_breaker,
                    "currentDailyLoss": self.agent_daily_loss.get(original_payload.get("agentId"), 0.0)
                }
            }
        }
        await bus.publish("risk.order.rejected", rejection_event)

    async def handle_execution_report(self, event_data: Dict[str, Any]) -> None:
        """
        Suscrito al reporte de ejecución final (broker.order.execution_report).
        Ajusta la exposición activa y simula ganancias/pérdidas para el tracking del drawdown diario.
        """
        payload = event_data.get("payload", {})
        agent_id = payload.get("agentId")
        status = payload.get("status")
        amount_usd = payload.get("amountUsd", 0.0)
        
        if not agent_id:
            return

        # Liberar exposición
        current_exp = self.agent_exposure.get(agent_id, 0.0)
        self.agent_exposure[agent_id] = max(0.0, round(current_exp - amount_usd, 4))
        self.save_state()

# Instancia global del Risk Engine
risk_engine = RiskEngine()

def setup():
    bus.subscribe("strategy.order.validated", risk_engine.validate_order)
    bus.subscribe("broker.order.execution_report", risk_engine.handle_execution_report)
