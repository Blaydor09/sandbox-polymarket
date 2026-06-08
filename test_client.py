import asyncio
import json
import urllib.request
import urllib.error
import websockets
import time

API_URL = "http://localhost:8000/api/v1/trade"
RESET_URL = "http://localhost:8000/api/v1/reset-risk"
WS_URL = "ws://localhost:8000/ws/signals"

# Plantilla base para señales de agente
BASE_SIGNAL = {
    "agentId": "openclaw_v2_alpha",
    "marketAddress": "0x4b7c2957b6b15efb1f7281fbf2a2c2b0d5c0b8de",
    "outcomeIndex": 1,
    "side": "BUY",
    "amountUsd": 100.0,
    "maxPrice": 0.60,
    "confidenceScore": 0.85,
    "strategyId": "polymarket_volatility_arb",
    "reasoning": {
        "llmModel": "gemini-3.5-flash",
        "promptsUsed": ["prompt_v3_analysis_financial"],
        "marketAnalysisSummary": "Se observa un spread ineficiente temporal.",
        "technicalIndicators": {"rsi_14": 42.5}
    }
}

def send_post_request(url: str, data: dict) -> dict:
    """Helper síncrono para enviar peticiones HTTP POST usando urllib."""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
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
    """Ejecuta los escenarios de simulación ordenados en tiempo real."""
    print("\n=== REINICIANDO ESTADO DE RIESGO DE PRUEBAS ===")
    reset_res = send_post_request(RESET_URL, {})
    print(f"Resultado del Reset: {reset_res}\n")

    await asyncio.sleep(2)  # Dar tiempo para ver conexión WS

    print("==================================================")
    print("ESCENARIO 1: Envío de Señal Válida (BUY 100 USD, conf 0.85)")
    print("Resultado Esperado: Aprobada por riesgo y ejecutada con slippage y latencia.")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    res1 = send_post_request(API_URL, signal)
    print(f"Respuesta HTTP Adapter: {res1}")
    await asyncio.sleep(3) # Esperar a que se procese y se imprima la notificación WS

    print("\n==================================================")
    print("ESCENARIO 2: Confianza Insuficiente (BUY 100 USD, conf 0.60)")
    print("Resultado Esperado: Rechazada en Strategy Controller.")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    signal["confidenceScore"] = 0.60
    res2 = send_post_request(API_URL, signal)
    print(f"Respuesta HTTP Adapter: {res2}")
    await asyncio.sleep(3)

    print("\n==================================================")
    print("ESCENARIO 3: Exposición Excesiva (BUY 1500 USD, conf 0.90)")
    print("Resultado Esperado: Rechazada por Risk Engine (Excede Límite de 1000 USD).")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    signal["amountUsd"] = 1500.0
    res3 = send_post_request(API_URL, signal)
    print(f"Respuesta HTTP Adapter: {res3}")
    await asyncio.sleep(3)

    print("\n==================================================")
    print("ESCENARIO 4: Detección de Bucle (Loop Storm - 4 órdenes rápidas)")
    print("Resultado Esperado: Las primeras pasan, la 4ta dispara el Circuit Breaker de loop.")
    print("==================================================")
    for i in range(1, 5):
        print(f"\nEnviando señal de bucle #{i}...")
        signal = BASE_SIGNAL.copy()
        signal["amountUsd"] = 50.0  # Menor tamaño
        res = send_post_request(API_URL, signal)
        print(f"Respuesta HTTP Adapter #{i}: {res}")
        await asyncio.sleep(0.5) # Muy rápido para disparar la ventana de 10s

    await asyncio.sleep(3) # Esperar a que lleguen todas las notificaciones

    print("\n==================================================")
    print("ESCENARIO 5: Intento de Operación post-bloqueo")
    print("Resultado Esperado: Rechazo inmediato por Circuit Breaker Global Activo.")
    print("==================================================")
    signal = BASE_SIGNAL.copy()
    res5 = send_post_request(API_URL, signal)
    print(f"Respuesta HTTP Adapter: {res5}")
    await asyncio.sleep(3)

    print("\n=== PRUEBAS FINALIZADAS ===")

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
