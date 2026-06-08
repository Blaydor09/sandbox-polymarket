import asyncio
import json
import urllib.request
import urllib.parse
import urllib.error
import websockets

API_URL = "http://127.0.0.1:8000/api/v1/trade"
RESET_URL = "http://127.0.0.1:8000/api/v1/reset-risk"
REPLAY_STOP_URL = "http://127.0.0.1:8000/api/v1/replay/stop"
LIVE_START_URL = "http://127.0.0.1:8000/api/v1/live/start"
LIVE_STOP_URL = "http://127.0.0.1:8000/api/v1/live/stop"
LIVE_STATUS_URL = "http://127.0.0.1:8000/api/v1/live/status"
WS_URL = "ws://127.0.0.1:8000/ws/signals"

# Plantilla base para señales de agente
BASE_SIGNAL = {
    "agentId": "openclaw_v2_alpha",
    "marketAddress": "0x4b7c2957b6b15efb1f7281fbf2a2c2b0d5c0b8de",
    "outcomeIndex": 10, # Usar index alto para evitar loops
    "side": "BUY",
    "amountUsd": 150.0,
    "maxPrice": 0.85, # Límite alto para permitir matching
    "confidenceScore": 0.88,
    "strategyId": "polymarket_live_feed_arb",
    "reasoning": {
        "llmModel": "gemini-3.5-flash",
        "promptsUsed": ["prompt_v3_live_analysis"],
        "marketAnalysisSummary": "Cruzando órdenes con datos en vivo/contingencia de Polymarket.",
        "technicalIndicators": {"rsi_14": 51.2}
    }
}

def send_post_request(url: str, query_params: dict = None, data: dict = None) -> dict:
    """Helper síncrono para enviar peticiones HTTP POST usando urllib."""
    full_url = url
    if query_params:
        params_str = urllib.parse.urlencode(query_params)
        full_url = f"{url}?{params_str}"
        
    req = urllib.request.Request(
        full_url,
        data=json.dumps(data).encode("utf-8") if data else None,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return json.loads(body)
        except:
            return {"error": e.code, "message": body}
    except Exception as e:
        return {"error": "connection_error", "message": str(e)}

def send_get_request(url: str) -> dict:
    """Helper síncrono para enviar peticiones HTTP GET usando urllib."""
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {"error": "connection_error", "message": str(e)}

async def send_post_request_async(url: str, query_params: dict = None, data: dict = None) -> dict:
    return await asyncio.to_thread(send_post_request, url, query_params, data)

async def send_get_request_async(url: str) -> dict:
    return await asyncio.to_thread(send_get_request, url)

async def listen_websocket():
    """Escucha el canal WebSocket de notificaciones del sandbox en tiempo real."""
    print(f"\n[*] Conectando al WebSocket del Sandbox: {WS_URL}")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("[+] WebSocket conectado con éxito. Esperando eventos...")
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                corr_id = data.get("correlationId")
                payload = data.get("payload", {})
                
                status = payload.get("status", "UNKNOWN")
                print(f"\n[WS NOTIFICATION] correlationId: {corr_id}")
                if "riskDecision" in payload and payload["riskDecision"] == "REJECTED":
                    print(f"    -> DECISIÓN: RIESGO RECHAZADO")
                    print(f"    -> RAZÓN: {payload.get('reason')}")
                else:
                    print(f"    -> ESTADO EJECUCIÓN: {status}")
                    if status == "FILLED" or status == "PARTIALLY_FILLED":
                        print(f"       Precio: {payload.get('averagePrice')} USD | Tamaño: {payload.get('executedSize')} tokens")
                        print(f"       Slippage: {payload.get('slippageIncurredPct')}% | Latencia: {payload.get('simulatedLatencyMs')}ms")
                        print(f"       TX Hash: {payload.get('nativeTransactionHash')}")
                    elif status == "REJECTED":
                        print(f"       Razón: {payload.get('reason')}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[-] Error en WebSocket: {e}")

async def run_scenarios():
    """Ejecuta los escenarios de simulación para verificar datos live read-only."""
    print("\n=== REINICIANDO ESTADO DE RIESGO DE PRUEBAS ===")
    reset_res = await send_post_request_async(RESET_URL)
    print(f"Resultado del Reset: {reset_res}\n")

    # Aseguramos que replay esté parado para no tener interferencias en el bus
    await send_post_request_async(REPLAY_STOP_URL)

    # Esperar a que el WebSocket termine de conectarse
    await asyncio.sleep(1.0)

    print("\n=== INICIANDO LECTOR EN VIVO (LIVE READ-ONLY) ===")
    live_res = await send_post_request_async(LIVE_START_URL)
    print(f"Resultado Live Start: {live_res}\n")

    # Esperar y verificar el estado del lector en vivo (esperar hasta 5 segundos para conexión)
    status = "STOPPED"
    for i in range(5):
        await asyncio.sleep(1.0)
        status_res = await send_get_request_async(LIVE_STATUS_URL)
        status = status_res.get("status", "UNKNOWN")
        print(f"    -> Intento {i+1}: Estado Lector en Vivo = {status}")
        if status in ("CONNECTED", "OFFLINE_FALLBACK"):
            break

    print(f"\n[+] Motor configurado en estado operativo: {status}")
    print("==================================================")
    print("ESCENARIO 1: Envío de señal contra Orderbook en Vivo (o Fallback)")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    res1 = await send_post_request_async(API_URL, data=signal)
    print(f"Respuesta HTTP Adapter 1: {res1}")

    # Dar tiempo para ver la ejecución en vivo en los logs
    await asyncio.sleep(4.0)

    print("\n=== DETENIENDO LECTOR EN VIVO ===")
    stop_res = await send_post_request_async(LIVE_STOP_URL)
    print(f"Resultado Live Stop: {stop_res}\n")
    
    await asyncio.sleep(1)
    print("\n=== PRUEBAS DE INGESTA EN VIVO FINALIZADAS ===")

async def main():
    # Arrancar la escucha de Websocket en segundo plano
    ws_task = asyncio.create_task(listen_websocket())
    
    # Arrancar la ejecución de escenarios de prueba
    await run_scenarios()
    
    # Cancelar Websocket al terminar
    ws_task.cancel()
    await asyncio.gather(ws_task, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCliente de prueba detenido manualmente.")
