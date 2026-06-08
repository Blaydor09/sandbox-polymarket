import uuid
import datetime
import logging
from typing import Dict, Any
from app.event_bus import bus
from app.config import STRATEGY_MIN_CONFIDENCE

logger = logging.getLogger("StrategyController")

async def handle_agent_signal(event_data: Dict[str, Any]) -> None:
    """
    Manejador del tópico agent.signal.received.
    Aplica reglas de negocio determinísticas como límites de confianza e indicadores técnicos.
    """
    correlation_id = event_data.get("correlationId")
    payload = event_data.get("payload", {})
    
    agent_id = payload.get("agentId")
    market_address = payload.get("marketAddress")
    side = payload.get("side")
    amount_usd = payload.get("amountUsd", 0.0)
    max_price = payload.get("maxPrice", 1.0)
    confidence_score = payload.get("confidenceScore", 0.0)
    strategy_id = payload.get("strategyId")
    outcome_index = payload.get("outcomeIndex")

    logger.info(f"Procesando señal en StrategyController. correlationId={correlation_id}")

    # 1. Regla: Validar Umbral Mínimo de Confianza de la IA
    if confidence_score < STRATEGY_MIN_CONFIDENCE:
        logger.warning(
            f"Señal rechazada: Confianza insuficiente ({confidence_score} < {STRATEGY_MIN_CONFIDENCE}). "
            f"correlationId={correlation_id}"
        )
        
        # Publicar rechazo inmediato en el bus
        rejection_event = {
            "eventId": f"evt_{uuid.uuid4()}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0.0",
            "correlationId": correlation_id,
            "payload": {
                "orderId": "N/A",
                "riskDecision": "REJECTED",
                "reason": f"STRATEGY_LOW_CONFIDENCE: Confianza {confidence_score} es menor al mínimo {STRATEGY_MIN_CONFIDENCE}",
                "circuitBreakersStatus": {
                    "globalStopActive": False
                }
            }
        }
        await bus.publish("risk.order.rejected", rejection_event)
        return

    # 2. Conversión a tokens teóricos en Polymarket
    # En Polymarket, cada share de outcome vale entre 0.0 y 1.0 USD.
    # Comprar tokens por un valor de X USD a un precio límite Y USD por token resulta en X / Y tokens.
    size_tokens = round(amount_usd / max_price, 4)

    # 3. Generación de Orden Validada por Estrategia
    order_id = f"ord_{uuid.uuid4()}"
    validated_order_event = {
        "eventId": f"evt_{uuid.uuid4()}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "version": "1.0.0",
        "correlationId": correlation_id,
        "payload": {
            "orderId": order_id,
            "agentId": agent_id,
            "marketAddress": market_address,
            "outcomeIndex": outcome_index,
            "side": side,
            "sizeTokens": size_tokens,
            "amountUsd": amount_usd,
            "limitPrice": max_price,
            "slippageTolerancePct": 0.5, # Configuración fija de slippage del 0.5% por defecto
            "strategyId": strategy_id,
            "reasoning": payload.get("reasoning") # Propagar reasoning para logs de auditoría
        }
    }

    logger.info(f"Estrategia validada. Orden creada: {order_id}. correlationId={correlation_id}")
    await bus.publish("strategy.order.validated", validated_order_event)

# Suscribir al bus de eventos
def setup():
    bus.subscribe("agent.signal.received", handle_agent_signal)
