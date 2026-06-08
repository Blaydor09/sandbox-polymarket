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

PORTFOLIO_URL = "http://127.0.0.1:8000/api/v1/portfolio"
PORTFOLIO_RESET_URL = "http://127.0.0.1:8000/api/v1/portfolio/reset"
PORTFOLIO_RESOLVE_URL = "http://127.0.0.1:8000/api/v1/portfolio/resolve-market"

EXECUTION_CONFIG_URL = "http://127.0.0.1:8000/api/v1/execution/config"
EXECUTION_BALANCE_URL = "http://127.0.0.1:8000/api/v1/execution/balance"
PORTFOLIO_RESET_URL = "http://127.0.0.1:8000/api/v1/portfolio/reset"
PORTFOLIO_RESOLVE_URL = "http://127.0.0.1:8000/api/v1/portfolio/resolve-market"

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
    """Ejecuta la suite de verificación de Micro Trading Real (Fase 5)."""
    print("\n==================================================")
    print("INICIANDO VERIFICACIÓN DE FASE 5: MICRO TRADING REAL")
    print("==================================================")

    # 1. Reiniciar estado de riesgo y de cartera
    print("\n[1] Reiniciando estados de riesgo y cartera...")
    res_risk = await send_post_request_async(RESET_URL)
    print(f"    -> Reset Riesgo: {res_risk}")
    res_port = await send_post_request_async(PORTFOLIO_RESET_URL)
    print(f"    -> Reset Cartera: {res_port}")

    # Aseguramos que replay esté parado
    await send_post_request_async(REPLAY_STOP_URL)

    # Esperar un momento para la conexión WS
    await asyncio.sleep(1.0)

    # 2. Consultar config inicial de ejecución
    print("\n[2] Consultando configuración inicial del Execution Service...")
    exec_config = await send_get_request_async(EXECUTION_CONFIG_URL)
    print(f"    -> Config de Ejecución: {exec_config}")
    assert exec_config.get("execution_mode") == "SANDBOX", "Debería iniciar en modo SANDBOX por defecto"

    # 3. Consultar balance en Gnosis RPC (mockeado/real)
    print("\n[3] Consultando balance de tokens en Gnosis Chain...")
    balance_res = await send_get_request_async(EXECUTION_BALANCE_URL)
    print(f"    -> Balance Gnosis: {balance_res}")

    # 4. Cambiar modo de ejecución a REAL
    print("\n[4] Migrando Execution Service a modo REAL...")
    update_res = await send_post_request_async(EXECUTION_CONFIG_URL, data={"executionMode": "REAL"})
    print(f"    -> Respuesta Migración: {update_res}")
    
    # Consultar config para confirmar cambio
    confirm_config = await send_get_request_async(EXECUTION_CONFIG_URL)
    print(f"    -> Config de Ejecución Post-Migración: {confirm_config}")
    assert confirm_config.get("execution_mode") == "REAL", "Debería haberse migrado a modo REAL"

    # 5. Enviar señal de compra (BUY) en modo REAL
    print("\n[5] Enviando señal de compra (BUY) en modo REAL...")
    signal = BASE_SIGNAL.copy()
    signal["amountUsd"] = 200.0
    signal["outcomeIndex"] = 1
    signal["maxPrice"] = 0.85
    signal["confidenceScore"] = 0.90
    
    trade_res = await send_post_request_async(API_URL, data=signal)
    print(f"    -> Respuesta Trade REAL (Aceptado en cola): {trade_res}")

    # Esperar a que se procese la orden, se firme con EIP-712 y se ejecute (dry-run)
    print("    -> Esperando firma y ejecución (3 segundos)...")
    await asyncio.sleep(3.0)

    # 6. Consultar estado de cartera post-compra en modo REAL
    print("\n[6] Consultando estado de la cartera después del trade REAL...")
    port = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Estado Cartera Post-Trade REAL: USD={port.get('usd_balance')}, NAV={port.get('net_asset_value')}, Posiciones={port.get('positions')}")

    # 7. Cambiar de nuevo a modo SANDBOX
    print("\n[7] Migrando de nuevo a modo SANDBOX...")
    restore_res = await send_post_request_async(EXECUTION_CONFIG_URL, data={"executionMode": "SANDBOX"})
    print(f"    -> Respuesta Restauración: {restore_res}")
    
    final_config = await send_get_request_async(EXECUTION_CONFIG_URL)
    print(f"    -> Config de Ejecución Final: {final_config}")
    assert final_config.get("execution_mode") == "SANDBOX", "Debería volver a modo SANDBOX"

    print("==================================================")
    print("SUITE DE FASE 5 COMPLETADA")
    print("==================================================")

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
