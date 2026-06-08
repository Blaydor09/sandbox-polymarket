import os
import json
import logging
import uuid
import datetime
from typing import Dict, Any, List, Optional
from app.event_bus import bus
from app.config import SUPERVISION_STATE_FILE

logger = logging.getLogger("SupervisionManager")

class SupervisionManager:
    def __init__(self):
        self.state_file = SUPERVISION_STATE_FILE
        # Formato: {order_id: order_event_data}
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        self.load_state()

    def load_state(self) -> None:
        """Carga el estado de órdenes pendientes de disco para resiliencia ante reinicios."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.pending_orders = json.load(f)
                logger.info(f"Cargadas {len(self.pending_orders)} órdenes pendientes de supervisión humana.")
            except Exception as e:
                logger.error(f"Error cargando órdenes pendientes de supervisión: {e}")
                self.pending_orders = {}
        else:
            self.save_state()

    def save_state(self) -> None:
        """Persiste la cola de supervisión en disco."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.pending_orders, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando estado de supervisión: {e}")

    async def handle_pending_approval(self, event_data: Dict[str, Any]) -> None:
        """
        Suscrito al tópico risk.order.pending_approval.
        Registra la orden en la cola de aprobación y la persiste.
        """
        payload = event_data.get("payload", {})
        order_id = payload.get("orderId")
        if not order_id:
            logger.error("Recibido evento pending_approval sin orderId.")
            return

        # Guardamos la orden completa para poder re-publicarla con su estructura intacta
        self.pending_orders[order_id] = event_data
        self.save_state()
        
        logger.info(
            f"[SUPERVISION PENDING] Orden {order_id} encolada esperando aprobación del operador. "
            f"Monto: {payload.get('amountUsd')} USD | Mercado: {payload.get('marketAddress')}"
        )

    async def approve_order(self, order_id: str) -> Dict[str, Any]:
        """
        Aprueba una orden pendiente y la inyecta al flujo de ejecución (risk.order.approved).
        """
        if order_id not in self.pending_orders:
            logger.warning(f"Intento de aprobar orden inexistente o ya procesada: {order_id}")
            return {
                "status": "ERROR",
                "message": f"La orden {order_id} no se encuentra pendiente de supervisión."
            }

        event_data = self.pending_orders.pop(order_id)
        self.save_state()

        # Emitimos el evento de aprobación de riesgo para gatillar el broker o execution service
        # Actualizamos la marca de tiempo de la decisión
        event_data["payload"]["supervisedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        event_data["payload"]["supervisorDecision"] = "APPROVED"
        
        logger.info(f"[SUPERVISION APPROVED] Orden {order_id} aprobada por supervisor humano. Publicando a ejecución.")
        await bus.publish("risk.order.approved", event_data)

        return {
            "status": "SUCCESS",
            "message": f"Orden {order_id} aprobada y enviada a ejecución.",
            "order": event_data
        }

    async def reject_order(self, order_id: str, reason: str = "Rechazado por operador") -> Dict[str, Any]:
        """
        Rechaza una orden pendiente emitiendo el evento de descarte (risk.order.rejected).
        """
        if order_id not in self.pending_orders:
            logger.warning(f"Intento de rechazar orden inexistente o ya procesada: {order_id}")
            return {
                "status": "ERROR",
                "message": f"La orden {order_id} no se encuentra pendiente de supervisión."
            }

        event_data = self.pending_orders.pop(order_id)
        self.save_state()

        payload = event_data.get("payload", {})
        correlation_id = event_data.get("correlationId")
        
        rejection_event = {
            "eventId": f"evt_{uuid.uuid4()}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0.0",
            "correlationId": correlation_id,
            "payload": {
                "orderId": order_id,
                "agentId": payload.get("agentId"),
                "marketAddress": payload.get("marketAddress"),
                "riskDecision": "REJECTED",
                "reason": f"SUPERVISOR_REJECTED: {reason}",
                "circuitBreakersStatus": {
                    "globalStopActive": False,
                    "currentDailyLoss": 0.0
                }
            }
        }

        logger.info(f"[SUPERVISION REJECTED] Orden {order_id} rechazada por supervisor humano. Razón: {reason}")
        await bus.publish("risk.order.rejected", rejection_event)

        return {
            "status": "SUCCESS",
            "message": f"Orden {order_id} rechazada con éxito.",
            "rejectionReason": reason
        }

    def get_pending_orders_list(self) -> List[Dict[str, Any]]:
        """Devuelve un listado de los payloads de las órdenes encoladas."""
        return [event.get("payload", {}) for event in self.pending_orders.values()]

# Instancia global del SupervisionManager
supervision_manager = SupervisionManager()

def setup():
    bus.subscribe("risk.order.pending_approval", supervision_manager.handle_pending_approval)
