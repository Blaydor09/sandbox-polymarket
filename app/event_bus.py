import asyncio
import logging
from typing import Callable, Any, Dict, List

logger = logging.getLogger("EventBus")

class EventBus:
    def __init__(self):
        # Mapea tópicos a una lista de callbacks asíncronos
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Suscribe una función callback (puede ser corrutina o normal) a un tópico."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.debug(f"Suscrito handler a: {topic}")

    async def publish(self, topic: str, event_data: Dict[str, Any]) -> None:
        """
        Publica un evento asincrónico a todos los suscriptores del tópico.
        Dispara tareas no bloqueantes para cada handler.
        """
        if topic not in self._subscribers or not self._subscribers[topic]:
            logger.debug(f"Publicado en {topic} sin suscriptores activos.")
            return

        logger.debug(f"Publicando en {topic}: {event_data.get('correlationId', 'N/A')}")
        
        # Iterar sobre una copia para evitar problemas de concurrencia al modificar la lista
        handlers = self._subscribers[topic].copy()
        
        for handler in handlers:
            # Creamos una tarea asincrónica para procesar el handler
            asyncio.create_task(self._safe_dispatch(handler, topic, event_data))

    async def _safe_dispatch(self, handler: Callable[[Dict[str, Any]], Any], topic: str, event_data: Dict[str, Any]) -> None:
        """Ejecuta de manera segura el callback, atrapando cualquier excepción."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event_data)
            else:
                handler(event_data)
        except Exception as e:
            logger.error(
                f"Error ejecutando handler en tópico {topic} "
                f"para correlationId {event_data.get('correlationId', 'unknown')}: {e}", 
                exc_info=True
            )

# Instancia global del bus para todo el ciclo de vida del sandbox
bus = EventBus()
