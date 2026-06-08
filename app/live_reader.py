import asyncio
import json
import logging
import random
import datetime
from typing import Dict, Any, Optional, List
import websockets
from app.event_bus import bus
from app.config import POLYMARKET_WS_URL, LIVE_MARKETS_TO_TRACK

logger = logging.getLogger("LiveMarketReader")

class LiveMarketReader:
    def __init__(self):
        self.ws_url = POLYMARKET_WS_URL
        self.markets = LIVE_MARKETS_TO_TRACK
        self.status = "STOPPED"  # STOPPED, CONNECTING, CONNECTED, OFFLINE_FALLBACK
        self.is_active = False
        
        self._reader_task: Optional[asyncio.Task] = None
        self._fallback_task: Optional[asyncio.Task] = None
        self._reconnect_delay = 1.0

    def start(self) -> bool:
        """Inicia el lector en vivo en segundo plano."""
        if self.is_active:
            logger.warning("El Live Market Reader ya se encuentra activo.")
            return False

        self.is_active = True
        self.status = "CONNECTING"
        self._reader_task = asyncio.create_task(self._run_live_loop())
        logger.info("Live Market Reader iniciado en segundo plano.")
        return True

    def stop(self) -> bool:
        """Detiene el lector en vivo."""
        if not self.is_active:
            return False

        self.is_active = False
        self.status = "STOPPED"
        
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
            
        if self._fallback_task:
            self._fallback_task.cancel()
            self._fallback_task = None
            
        logger.info("Live Market Reader detenido manualmente.")
        return True

    async def _run_live_loop(self) -> None:
        """Bucle principal de conexión Websocket con reconexión y fallback."""
        consecutive_failures = 0
        
        while self.is_active:
            self.status = "CONNECTING"
            logger.info(f"Intentando conectar al WebSocket CLOB de Polymarket: {self.ws_url}")
            
            try:
                # Intentamos conectar con timeout de 5 segundos
                async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                    consecutive_failures = 0
                    self.status = "CONNECTED"
                    logger.info("Conexión WebSocket establecida con Polymarket CLOB.")
                    
                    # Detener el generador de contingencia (fallback) si estaba activo
                    if self._fallback_task:
                        self._fallback_task.cancel()
                        self._fallback_task = None
                        logger.info("Conexión real establecida. Deteniendo contingencia (Fallback).")
                    
                    self._reconnect_delay = 1.0  # Reset del backoff
                    
                    # Suscribirse a los canales de orderbook L2 para los mercados configurados
                    # Formato oficial de Polymarket CLOB WS API
                    subscribe_msg = {
                        "type": "subscribe",
                        "assets_ids": self.markets,
                        "channels": ["order_book_l2"]
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info(f"Suscripción enviada para mercados: {self.markets}")
                    
                    # Consumir mensajes continuamente
                    async for message in ws:
                        if not self.is_active:
                            break
                        
                        await self._process_ws_message(message)
                        
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Fallo en conexión WebSocket de Polymarket (Fallo #{consecutive_failures}): {e}")
                
                # Si falla más de 2 veces, activamos el modo Fallback para que el Sandbox siga vivo
                if consecutive_failures >= 2 and not self._fallback_task:
                    self.status = "OFFLINE_FALLBACK"
                    logger.warning("Fallo en API de Polymarket. Iniciando generador de contingencia (Fallback).")
                    self._fallback_task = asyncio.create_task(self._run_fallback_generator())
                
                # Algoritmo de Backoff Exponencial con Jitter
                sleep_time = min(60.0, self._reconnect_delay * 2) + random.uniform(0.0, 1.0)
                self._reconnect_delay = sleep_time
                logger.info(f"Reintentando conexión en {sleep_time:.2f} segundos...")
                
                try:
                    await asyncio.sleep(sleep_time)
                except asyncio.CancelledError:
                    break

    async def _process_ws_message(self, message_str: str) -> None:
        """Parsea y normaliza los mensajes del WebSocket real de Polymarket."""
        try:
            data = json.loads(message_str)
            
            # Polymarket WS envía típicamente eventos del tipo "book"
            if data.get("event") == "book" or "asks" in data or "bids" in data:
                market_address = data.get("asset_id") or self.markets[0]
                
                # Normalizar bids y asks al formato esperado por nuestro broker
                # Formato original en Polymarket: [{"price": "0.60", "size": "500"}, ...]
                # Nuestro formato interno: [[0.60, 500.0], ...]
                raw_asks = data.get("asks", [])
                raw_bids = data.get("bids", [])
                
                asks = []
                for a in raw_asks:
                    if isinstance(a, dict):
                        asks.append([float(a.get("price", 0)), float(a.get("size", 0))])
                    elif isinstance(a, list) and len(a) >= 2:
                        asks.append([float(a[0]), float(a[1])])
                        
                bids = []
                for b in raw_bids:
                    if isinstance(b, dict):
                        bids.append([float(b.get("price", 0)), float(b.get("size", 0))])
                    elif isinstance(b, list) and len(b) >= 2:
                        bids.append([float(b[0]), float(b[1])])

                # Si el payload está vacío por alguna razón, no actualizar
                if not asks and not bids:
                    return

                event_payload = {
                    "eventId": f"evt_live_{datetime.datetime.now(datetime.timezone.utc).timestamp()}",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "version": "1.0.0",
                    "payload": {
                        "marketAddress": market_address,
                        "asks": asks,
                        "bids": bids
                    }
                }
                
                logger.debug(f"Publicando actualización live de orderbook para {market_address}")
                await bus.publish("market.ticker.clob", event_payload)
                
        except Exception as e:
            logger.error(f"Error procesando mensaje WebSocket: {e}")

    async def _run_fallback_generator(self) -> None:
        """
        Generador de contingencia (Fallback).
        Genera orderbooks ficticios dinámicos pero estructurados cuando no hay conexión a Polymarket.
        """
        logger.info("Generador de contingencia (Fallback) activado y publicando...")
        
        # Precio pivote simulado que fluctúa
        pivot_price = 0.60
        market_address = self.markets[0]
        
        try:
            while self.is_active:
                # Hacer fluctuar el precio levemente (+-0.01 por segundo)
                pivot_price = max(0.10, min(0.90, pivot_price + random.choice([-0.005, 0.0, 0.005])))
                
                # Reconstruir asks y bids simulando liquidez
                asks = [
                    [round(pivot_price, 3), 500.0],
                    [round(pivot_price + 0.01, 3), 1000.0],
                    [round(pivot_price + 0.02, 3), 2500.0]
                ]
                bids = [
                    [round(pivot_price - 0.01, 3), 600.0],
                    [round(pivot_price - 0.02, 3), 1200.0],
                    [round(pivot_price - 0.03, 3), 2000.0]
                ]
                
                event_payload = {
                    "eventId": f"evt_fallback_{datetime.datetime.now(datetime.timezone.utc).timestamp()}",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "version": "1.0.0",
                    "payload": {
                        "marketAddress": market_address,
                        "asks": asks,
                        "bids": bids
                    }
                }
                
                logger.info(f"[FALLBACK FEED] Publicando tick simulado. Punta Ask: {asks[0][0]}")
                await bus.publish("market.ticker.clob", event_payload)
                
                # Publicar un tick cada 1.5 segundos
                await asyncio.sleep(1.5)
                
        except asyncio.CancelledError:
            logger.info("Generador de contingencia cancelado.")

# Instancia global del lector en vivo
live_market_reader = LiveMarketReader()
