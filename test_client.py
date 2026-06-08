import asyncio
import json
import urllib.request
import urllib.parse
import urllib.error
import websockets

API_URL = "http://127.0.0.1:8000/api/v1/trade"
RESET_URL = "http://127.0.0.1:8000/api/v1/reset-risk"
REPLAY_START_URL = "http://127.0.0.1:8000/api/v1/replay/start"
REPLAY_STOP_URL = "http://127.0.0.1:8000/api/v1/replay/stop"
WS_URL = "ws://127.0.0.1:8000/ws/signals"

# Plantilla base para señales de agente
BASE_SIGNAL = {
    "agentId": "openclaw_v2_alpha",
    "marketAddress": "0x4b7c2957b6b15efb1f7281fbf2a2c2b0d5c0b8de",
    "outcomeIndex": 1,
    "side": "BUY",
    "amountUsd": 100.0,
    "maxPrice": 0.70, # Límite alto para permitir matching
    "confidenceScore": 0.85,
    "strategyId": "polymarket_volatility_arb",
    "reasoning": {
        "llmModel": "gemini-3.5-flash",
        "promptsUsed": ["prompt_v3_analysis_financial"],
        "marketAnalysisSummary": "Se observa un spread ineficiente temporal.",
        "technicalIndicators": {"rsi_14": 42.5}
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

async def send_post_request_async(url: str, query_params: dict = None, data: dict = None) -> dict:
    """Ejecuta send_post_request en un hilo separado de forma no bloqueante para el Event Loop."""
    return await asyncio.to_thread(send_post_request, url, query_params, data)

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
    """Ejecuta los escenarios de simulación de replay histórico."""
    print("\n=== REINICIANDO ESTADO DE RIESGO DE PRUEBAS ===")
    reset_res = await send_post_request_async(RESET_URL)
    print(f"Resultado del Reset: {reset_res}\n")

    # Esperar a que el WebSocket termine de conectarse en segundo plano
    await asyncio.sleep(1.0)

    print("\n=== INICIANDO REPLAY HISTÓRICO (DILATACIÓN 2.0x) ===")
    # Con velocidad 2.0x: delta de 5 virtual seconds = 2.5 real seconds.
    # El replay tardará 7.5 segundos reales en completarse.
    replay_res = await send_post_request_async(REPLAY_START_URL, query_params={"speed": 2.0})
    print(f"Resultado Replay Start: {replay_res}\n")

    # Esperamos 0.2 segundos para asegurar la inyección de Tick 1 (Punta: 0.60)
    await asyncio.sleep(0.2)

    print("==================================================")
    print("ESCENARIO 1: Orden en Tick 1 (Precio esperado punta: 0.60)")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    signal["outcomeIndex"] = 0  # Usamos outcomeIndex distintos para no activar loop detection
    res1 = await send_post_request_async(API_URL, data=signal)
    print(f"Respuesta HTTP Adapter 1: {res1}")
    
    # Esperamos 2.5 segundos reales (transcurren 5 segundos virtuales: pasamos al Tick 2)
    await asyncio.sleep(2.5)

    print("\n==================================================")
    print("ESCENARIO 2: Orden en Tick 2 (Precio esperado punta: 0.62)")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    signal["outcomeIndex"] = 1
    res2 = await send_post_request_async(API_URL, data=signal)
    print(f"Respuesta HTTP Adapter 2: {res2}")

    # Esperamos 2.5 segundos reales (transcurren otros 5 segundos virtuales: pasamos al Tick 3)
    await asyncio.sleep(2.5)

    print("\n==================================================")
    print("ESCENARIO 3: Orden en Tick 3 (Precio esperado punta: 0.64)")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    signal["outcomeIndex"] = 2
    res3 = await send_post_request_async(API_URL, data=signal)
    print(f"Respuesta HTTP Adapter 3: {res3}")

    # Esperamos 2.5 segundos reales (transcurren otros 5 segundos virtuales: pasamos al Tick 4)
    await asyncio.sleep(2.5)

    print("\n==================================================")
    print("ESCENARIO 4: Límite de Precio Excedido (Ask 0.66, Máximo permitido por la orden: 0.61)")
    print("Resultado Esperado: El broker rechaza por límite de precio excedido.")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    signal["outcomeIndex"] = 3
    signal["maxPrice"] = 0.61  # Muy bajo para el nivel actual (0.66)
    res4 = await send_post_request_async(API_URL, data=signal)
    print(f"Respuesta HTTP Adapter 4: {res4}")

    # Esperamos a que se procese
    await asyncio.sleep(2)

    print("\n=== DETENIENDO REPLAY HISTÓRICO ===")
    stop_res = await send_post_request_async(REPLAY_STOP_URL)
    print(f"Resultado Replay Stop: {stop_res}\n")
    
    await asyncio.sleep(1)
    print("\n=== PRUEBAS DE REPLAY HISTÓRICO FINALIZADAS ===")

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
