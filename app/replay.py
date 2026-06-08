import asyncio
import json
import os
import datetime
import logging
from typing import Dict, Any, Optional
from app.event_bus import bus
from app.config import HISTORICAL_FEED_FILE

logger = logging.getLogger("MarketReplayEngine")

class MarketReplayEngine:
    def __init__(self):
        self.feed_file = HISTORICAL_FEED_FILE
        self.dilation_factor = 1.0
        self._replay_task: Optional[asyncio.Task] = None
        self.is_active = False

    def start(self, speed: float = 1.0) -> bool:
        """Inicia la tarea asíncrona de lectura y reproducción del dataset."""
        if self.is_active:
            logger.warning("El motor de Replay ya se encuentra activo.")
            return False

        if not os.path.exists(self.feed_file):
            logger.error(f"Archivo de feed histórico no encontrado en {self.feed_file}")
            return False

        self.dilation_factor = speed
        self.is_active = True
        self._replay_task = asyncio.create_task(self._run_replay_loop())
        logger.info(f"Replay histórico iniciado. Velocidad={speed}x")
        return True

    def stop(self) -> bool:
        """Detiene la tarea de reproducción."""
        if not self.is_active:
            return False

        self.is_active = False
        if self._replay_task:
            self._replay_task.cancel()
            self._replay_task = None
        logger.info("Replay histórico detenido manualmente.")
        return True

    async def _run_replay_loop(self) -> None:
        """
        Lee el archivo JSONL línea por línea, calcula la diferencia temporal
        de marcas de tiempo e inyecta los eventos aplicando la dilatación.
        """
        try:
            prev_timestamp: Optional[datetime.datetime] = None
            
            with open(self.feed_file, "r") as f:
                for line in f:
                    if not self.is_active:
                        break
                    
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        tick_data = json.loads(line)
                        timestamp_str = tick_data.get("timestamp")
                        curr_timestamp = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        
                        # Calcular el tiempo a esperar antes de inyectar el evento
                        if prev_timestamp is not None:
                            delta_sec = (curr_timestamp - prev_timestamp).total_seconds()
                            if delta_sec > 0:
                                # Aplicar la fórmula de dilatación temporal
                                sleep_duration = delta_sec / self.dilation_factor
                                logger.debug(f"Replay: esperando {sleep_duration:.3f}s (delta original: {delta_sec}s)")
                                await asyncio.sleep(sleep_duration)
                        
                        # Actualizar timestamp previo
                        prev_timestamp = curr_timestamp
                        
                        # Generar y publicar el evento de mercado
                        event_payload = {
                            "eventId": f"evt_market_{curr_timestamp.timestamp()}",
                            "timestamp": curr_timestamp.isoformat(),
                            "version": "1.0.0",
                            "payload": {
                                "marketAddress": tick_data.get("marketAddress"),
                                "asks": tick_data.get("asks", []),
                                "bids": tick_data.get("bids", [])
                            }
                        }
                        
                        logger.info(f"Inyectando tick histórico en bus: {timestamp_str}")
                        await bus.publish("market.ticker.clob", event_payload)

                    except ValueError as ve:
                        logger.error(f"Error parseando timestamp en dataset: {ve}")
                    except Exception as e:
                        logger.error(f"Error procesando línea de replay: {e}")

            logger.info("Fin del archivo de replay histórico alcanzado.")
        except asyncio.CancelledError:
            logger.info("Bucle de replay cancelado.")
        finally:
            self.is_active = False
            self._replay_task = None

# Instancia global del Replay Engine
replay_engine = MarketReplayEngine()
