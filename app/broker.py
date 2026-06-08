import asyncio
import random
import datetime
import logging
import uuid
from typing import Dict, Any, List
from app.event_bus import bus
from app.config import (
    SLIPPAGE_K_FACTOR,
    SLIPPAGE_GAUSSIAN_NOISE_STD,
    LATENCY_GAMMA_ALPHA,
    LATENCY_GAMMA_BETA
)

logger = logging.getLogger("SandboxBroker")

class SandboxBroker:
    def __init__(self):
        # Base de libros de órdenes locales por mercado para simular (Outcome 1)
        # Formato de niveles: [precio, volumen_disponible]
        self.mock_orderbooks: Dict[str, Dict[str, List[List[float]]]] = {}

    def get_or_create_orderbook(self, market_address: str, default_price: float = 0.50) -> Dict[str, List[List[float]]]:
        """Devuelve o inicializa un libro de órdenes simulado para el mercado.
        Si el mercado no tiene orderbook (ni mock ni live), lo crea alrededor de default_price.
        """
        if market_address not in self.mock_orderbooks:
            p = default_price
            self.mock_orderbooks[market_address] = {
                "asks": [
                    [round(p, 3), 500.0],
                    [round(p + 0.02, 3), 1000.0],
                    [round(p + 0.05, 3), 2500.0],
                    [round(p + 0.10, 3), 5000.0]
                ],
                "bids": [
                    [round(p - 0.02, 3), 600.0],
                    [round(p - 0.04, 3), 1200.0],
                    [round(p - 0.07, 3), 2500.0],
                    [round(p - 0.12, 3), 5000.0]
                ]
            }
        return self.mock_orderbooks[market_address]

    async def handle_market_data(self, event_data: Dict[str, Any]) -> None:
        """Actualiza el libro de órdenes con ticks provenientes del feed histórico o live."""
        payload = event_data.get("payload", {})
        market_address = payload.get("marketAddress")
        if market_address:
            self.mock_orderbooks[market_address] = {
                "asks": payload.get("asks", []),
                "bids": payload.get("bids", [])
            }
            logger.info(f"Orderbook actualizado para {market_address} desde bus de eventos.")

    async def execute_order(self, event_data: Dict[str, Any]) -> None:
        """
        Suscrito al tópico risk.order.approved.
        Simula latencia de blockchain, realiza matching contra el orderbook virtual y aplica slippage.
        """
        correlation_id = event_data.get("correlationId")
        payload = event_data.get("payload", {})
        
        order_id = payload.get("orderId")
        agent_id = payload.get("agentId")
        market_address = payload.get("marketAddress")
        side = payload.get("side")
        size_tokens = payload.get("sizeTokens", 0.0)
        limit_price = payload.get("limitPrice", 1.0)
        amount_usd = payload.get("amountUsd", 0.0)
        outcome_index = payload.get("outcomeIndex", 1)

        logger.info(f"Ejecutando orden {order_id} en SandboxBroker. correlationId={correlation_id}")

        # 1. Simulación estocástica de Latencia (Distribución Gamma)
        # Media = alpha * beta. Para alpha=2 y beta=50, la media es de 100ms.
        simulated_latency_ms = int(random.gammavariate(LATENCY_GAMMA_ALPHA, LATENCY_GAMMA_BETA))
        await asyncio.sleep(simulated_latency_ms / 1000.0)

        # Obtener el orderbook de este mercado
        orderbook = self.get_or_create_orderbook(market_address, default_price=limit_price)
        targets = orderbook["asks"] if side == "BUY" else orderbook["bids"]
        
        # 2. Algoritmo de Matching
        remaining_size = size_tokens
        total_cost = 0.0
        executed_size = 0.0
        ideal_price = targets[0][0] # Precio en la punta (ideal)

        for level in targets:
            price = level[0]
            volume_available = level[1]

            # Verificar si el precio límite de la orden cubre el precio del nivel
            if side == "BUY" and price > limit_price:
                break # El precio límite del agente es menor que el precio de venta disponible
            if side == "SELL" and price < limit_price:
                break # El precio límite del agente es mayor que la compra disponible

            if volume_available >= remaining_size:
                total_cost += remaining_size * price
                executed_size += remaining_size
                remaining_size = 0.0
                break
            else:
                total_cost += volume_available * price
                executed_size += volume_available
                remaining_size -= volume_available

        # 3. Evaluar resultado del Matching
        if executed_size == 0:
            # Orden Rechazada por precio fuera de rango o falta absoluta de liquidez
            logger.warning(f"Orden {order_id} rechazada por broker: Fuera de rango de precio o sin liquidez.")
            report_event = {
                "eventId": f"evt_{uuid.uuid4()}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "version": "1.0.0",
                "correlationId": correlation_id,
                "payload": {
                    "orderId": order_id,
                    "agentId": agent_id,
                    "marketAddress": market_address,
                    "amountUsd": amount_usd,
                    "status": "REJECTED",
                    "reason": "LIMIT_PRICE_EXCEEDED_OR_NO_LIQUIDITY",
                    "executedSize": 0.0,
                    "averagePrice": 0.0,
                    "slippageIncurredPct": 0.0,
                    "simulatedLatencyMs": simulated_latency_ms,
                    "nativeTransactionHash": "N/A"
                }
            }
            await bus.publish("broker.order.execution_report", report_event)
            return

        average_price = round(total_cost / executed_size, 4)
        
        # Calcular slippage incurrido real en porcentaje
        if side == "BUY":
            slippage_pct = ((average_price - ideal_price) / ideal_price) * 100
        else:
            slippage_pct = ((ideal_price - average_price) / ideal_price) * 100

        # Agregar ruido aleatorio gaussiano para simular movimientos de milisegundos
        noise = random.gauss(0, SLIPPAGE_GAUSSIAN_NOISE_STD)
        slippage_pct = max(0.0, round(slippage_pct + noise, 4))

        status = "FILLED" if remaining_size == 0.0 else "PARTIALLY_FILLED"
        tx_hash = f"sandbox_tx_{uuid.uuid4().hex[:32]}"

        logger.info(
            f"Orden {order_id} procesada. Estado={status}, "
            f"Precio Promedio={average_price}, Slippage={slippage_pct}%, Latencia={simulated_latency_ms}ms"
        )

        # Generar Reporte de Ejecución (Execution Report)
        report_event = {
            "eventId": f"evt_{uuid.uuid4()}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0.0",
            "correlationId": correlation_id,
            "payload": {
                "orderId": order_id,
                "agentId": agent_id,
                "marketAddress": market_address,
                "side": side,
                "outcomeIndex": outcome_index,
                "amountUsd": round(executed_size * average_price, 2),
                "status": status,
                "executedSize": round(executed_size, 4),
                "averagePrice": average_price,
                "slippageIncurredPct": slippage_pct,
                "simulatedLatencyMs": simulated_latency_ms,
                "nativeTransactionHash": tx_hash
            }
        }
        
        await bus.publish("broker.order.execution_report", report_event)

# Instancia global del broker
broker = SandboxBroker()

def setup():
    bus.subscribe("risk.order.approved", broker.execute_order)
    bus.subscribe("market.ticker.clob", broker.handle_market_data)
