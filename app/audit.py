import os
import json
import datetime
import logging
from typing import Dict, Any
from app.event_bus import bus
from app.config import AUDIT_LOG_FILE

logger = logging.getLogger("AuditSystem")

class AuditSystem:
    def __init__(self):
        self.log_file = AUDIT_LOG_FILE
        # Buffer temporal en memoria para asociar eventos por correlationId
        self._active_traces: Dict[str, Dict[str, Any]] = {}
        
        # Asegurar que el directorio de logs exista
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def write_to_log(self, record: Dict[str, Any]) -> None:
        """Escribe una línea append-only en el archivo JSONL de auditoría."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error escribiendo en registro de auditoría: {e}")

    async def handle_signal_received(self, event_data: Dict[str, Any]) -> None:
        """Suscrito a agent.signal.received. Inicia la traza analítica."""
        correlation_id = event_data.get("correlationId")
        payload = event_data.get("payload", {})
        
        self._active_traces[correlation_id] = {
            "correlationId": correlation_id,
            "agentId": payload.get("agentId"),
            "marketAddress": payload.get("marketAddress"),
            "outcomeIndex": payload.get("outcomeIndex"),
            "side": payload.get("side"),
            "amountUsd": payload.get("amountUsd"),
            "maxPrice": payload.get("maxPrice"),
            "confidenceScore": payload.get("confidenceScore"),
            "strategyId": payload.get("strategyId"),
            "reasoning": payload.get("reasoning"),
            "receivedAt": event_data.get("timestamp"),
            "riskDecision": "PENDING",
            "rejectionReason": "N/A",
            "executionStatus": "PENDING",
            "executedSize": 0.0,
            "averagePrice": 0.0,
            "slippageIncurredPct": 0.0,
            "simulatedLatencyMs": 0,
            "nativeTransactionHash": "N/A"
        }
        logger.debug(f"Audit log: Traza inicializada para correlationId={correlation_id}")

    async def handle_risk_rejected(self, event_data: Dict[str, Any]) -> None:
        """Suscrito a risk.order.rejected. Cierra la traza con estado rechazado."""
        correlation_id = event_data.get("correlationId")
        payload = event_data.get("payload", {})
        
        trace = self._active_traces.pop(correlation_id, None)
        if not trace:
            # Si se perdió o no existió por alguna razón
            trace = {"correlationId": correlation_id}
            
        trace["riskDecision"] = "REJECTED"
        trace["rejectionReason"] = payload.get("reason", "Unknown Risk Rejection")
        trace["executionStatus"] = "REJECTED"
        trace["resolvedAt"] = event_data.get("timestamp")
        
        logger.info(f"Audit log: Escribiendo traza REJECTED para correlationId={correlation_id}")
        self.write_to_log(trace)

    async def handle_execution_report(self, event_data: Dict[str, Any]) -> None:
        """Suscrito a broker.order.execution_report. Cierra la traza con el resultado del match."""
        correlation_id = event_data.get("correlationId")
        payload = event_data.get("payload", {})
        
        trace = self._active_traces.pop(correlation_id, None)
        if not trace:
            trace = {"correlationId": correlation_id}
            
        trace["riskDecision"] = "APPROVED"
        trace["executionStatus"] = payload.get("status")
        
        if payload.get("status") == "REJECTED":
            trace["rejectionReason"] = payload.get("reason", "Broker Rejection")
        else:
            trace["executedSize"] = payload.get("executedSize", 0.0)
            trace["averagePrice"] = payload.get("averagePrice", 0.0)
            trace["slippageIncurredPct"] = payload.get("slippageIncurredPct", 0.0)
            trace["nativeTransactionHash"] = payload.get("nativeTransactionHash", "N/A")
            
        trace["simulatedLatencyMs"] = payload.get("simulatedLatencyMs", 0)
        trace["resolvedAt"] = event_data.get("timestamp")
        
        logger.info(f"Audit log: Escribiendo traza {payload.get('status')} para correlationId={correlation_id}")
        self.write_to_log(trace)

# Instancia global del auditor
audit_system = AuditSystem()

def setup():
    bus.subscribe("agent.signal.received", audit_system.handle_signal_received)
    bus.subscribe("risk.order.rejected", audit_system.handle_risk_rejected)
    bus.subscribe("broker.order.execution_report", audit_system.handle_execution_report)
