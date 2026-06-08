import json
import logging
from typing import Dict, Any
from app.event_bus import bus
from app.risk import risk_engine

logger = logging.getLogger("Observability")

class ObservabilityManager:
    def __init__(self):
        # Contadores y acumuladores locales en memoria
        self.metrics = {
            "signals_received": 0,
            "orders_validated": 0,
            "risk_approved": 0,
            "risk_rejected": 0,
            "broker_filled": 0,
            "broker_rejected": 0,
            "total_latency_ms": 0,
            "total_slippage_pct": 0.0,
            "filled_orders_count": 0
        }

    def print_structured_metrics(self) -> None:
        """Imprime un reporte estructurado JSON por consola para ingesta por agentes de monitoreo."""
        avg_latency = 0.0
        if self.metrics["risk_approved"] > 0:
            avg_latency = self.metrics["total_latency_ms"] / self.metrics["risk_approved"]

        avg_slippage = 0.0
        if self.metrics["filled_orders_count"] > 0:
            avg_slippage = self.metrics["total_slippage_pct"] / self.metrics["filled_orders_count"]

        report = {
            "metric_type": "SANDBOX_SYSTEM_REPORT",
            "active_circuit_breaker": risk_engine.global_circuit_breaker,
            "metrics": {
                "sandbox_agent_signals_total": self.metrics["signals_received"],
                "sandbox_strategy_validated_total": self.metrics["orders_validated"],
                "sandbox_risk_approved_total": self.metrics["risk_approved"],
                "sandbox_risk_rejected_total": self.metrics["risk_rejected"],
                "sandbox_broker_filled_total": self.metrics["broker_filled"],
                "sandbox_broker_rejected_total": self.metrics["broker_rejected"],
                "sandbox_average_latency_ms": round(avg_latency, 2),
                "sandbox_average_slippage_pct": round(avg_slippage, 4)
            }
        }
        # Output estructurado
        print(f"\n--- METRICS DUMP ---\n{json.dumps(report, indent=2)}\n--------------------\n")

    async def on_signal_received(self, event_data: Dict[str, Any]) -> None:
        self.metrics["signals_received"] += 1
        logger.info(f"[METRIC] Señal recibida. Total: {self.metrics['signals_received']}")

    async def on_order_validated(self, event_data: Dict[str, Any]) -> None:
        self.metrics["orders_validated"] += 1
        logger.info(f"[METRIC] Orden validada por Estrategia. Total: {self.metrics['orders_validated']}")

    async def on_risk_approved(self, event_data: Dict[str, Any]) -> None:
        self.metrics["risk_approved"] += 1
        logger.info(f"[METRIC] Orden aprobada por Riesgo. Total: {self.metrics['risk_approved']}")

    async def on_risk_rejected(self, event_data: Dict[str, Any]) -> None:
        self.metrics["risk_rejected"] += 1
        logger.info(f"[METRIC] Orden rechazada por Riesgo. Total: {self.metrics['risk_rejected']}")
        self.print_structured_metrics()

    async def on_execution_report(self, event_data: Dict[str, Any]) -> None:
        payload = event_data.get("payload", {})
        status = payload.get("status")
        latency = payload.get("simulatedLatencyMs", 0)
        slippage = payload.get("slippageIncurredPct", 0.0)

        self.metrics["total_latency_ms"] += latency

        if status in ("FILLED", "PARTIALLY_FILLED"):
            self.metrics["broker_filled"] += 1
            self.metrics["filled_orders_count"] += 1
            self.metrics["total_slippage_pct"] += slippage
        else:
            self.metrics["broker_rejected"] += 1

        logger.info(
            f"[METRIC] Ejecución de broker procesada ({status}). "
            f"Latencia: {latency}ms. Slippage: {slippage}%"
        )
        self.print_structured_metrics()

# Instancia global del administrador de observabilidad
observability = ObservabilityManager()

def setup():
    bus.subscribe("agent.signal.received", observability.on_signal_received)
    bus.subscribe("strategy.order.validated", observability.on_order_validated)
    bus.subscribe("risk.order.approved", observability.on_risk_approved)
    bus.subscribe("risk.order.rejected", observability.on_risk_rejected)
    bus.subscribe("broker.order.execution_report", observability.on_execution_report)
