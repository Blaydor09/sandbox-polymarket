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

SUPERVISION_PENDING_URL = "http://127.0.0.1:8000/api/v1/supervision/pending"
SUPERVISION_APPROVE_URL = "http://127.0.0.1:8000/api/v1/supervision/approve"
SUPERVISION_REJECT_URL = "http://127.0.0.1:8000/api/v1/supervision/reject"
SUPERVISION_TOGGLE_URL = "http://127.0.0.1:8000/api/v1/supervision/toggle"

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
    """Ejecuta la suite de verificación de Autonomía Parcial Supervisada (Fase 6)."""
    print("\n==================================================")
    print("INICIANDO VERIFICACIÓN DE FASE 6: AUTONOMÍA PARCIAL SUPERVISADA")
    print("==================================================")

    # 1. Reiniciar estados de riesgo, cartera y asegurar modo Sandbox
    print("\n[1] Reiniciando estados de riesgo y cartera...")
    res_risk = await send_post_request_async(RESET_URL)
    print(f"    -> Reset Riesgo: {res_risk}")
    res_port = await send_post_request_async(PORTFOLIO_RESET_URL)
    print(f"    -> Reset Cartera: {res_port}")
    await send_post_request_async(REPLAY_STOP_URL)
    await send_post_request_async(EXECUTION_CONFIG_URL, data={"executionMode": "SANDBOX"})

    # 2. Habilitar la supervisión humana
    print("\n[2] Habilitando la supervisión humana global...")
    toggle_res = await send_post_request_async(SUPERVISION_TOGGLE_URL, data={"enabled": True})
    print(f"    -> Estado Supervisión: {toggle_res}")

    # Verificar que la lista de pendientes esté vacía
    pending_init = await send_get_request_async(SUPERVISION_PENDING_URL)
    print(f"    -> Cola Inicial Pendiente: {pending_init}")

    # 3. Enviar señal de compra (BUY) y verificar retención
    print("\n[3] Enviando señal de compra (BUY) de $150 USD...")
    signal1 = BASE_SIGNAL.copy()
    signal1["amountUsd"] = 150.0
    signal1["outcomeIndex"] = 1
    signal1["maxPrice"] = 0.85
    signal1["confidenceScore"] = 0.90
    
    trade_res1 = await send_post_request_async(API_URL, data=signal1)
    print(f"    -> Respuesta Trade 1 (Aceptado): {trade_res1}")

    # Esperar 2 segundos y verificar que NO se ha ejecutado
    print("    -> Esperando procesamiento del motor de riesgo (2 segundos)...")
    await asyncio.sleep(2.0)

    print("\n[4] Consultando estado de la cartera (debe estar intacto)...")
    port1 = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera: USD={port1.get('usd_balance')}, Posiciones={port1.get('positions')}")
    assert port1.get("usd_balance") == 10000.0, "El saldo no debería variar mientras la orden esté retenida"

    # 4. Consultar cola de supervisión y extraer orderId
    print("\n[5] Consultando la cola de supervisión pendiente...")
    pending_list1 = await send_get_request_async(SUPERVISION_PENDING_URL)
    print(f"    -> Pendientes: {pending_list1}")
    assert pending_list1.get("count", 0) == 1, "Debería haber 1 orden en la cola de supervisión"
    
    order_id_1 = pending_list1.get("orders")[0].get("orderId")
    print(f"    -> ID de orden encontrada: {order_id_1}")

    # 5. Aprobar la orden y verificar ejecución
    print(f"\n[6] Aprobando la orden {order_id_1} desde la supervisión...")
    approve_res = await send_post_request_async(f"{SUPERVISION_APPROVE_URL}/{order_id_1}")
    print(f"    -> Resultado Aprobación: {approve_res}")

    # Esperar procesamiento y verificar que ahora sí se ejecutó
    print("    -> Esperando ejecución del trade aprobado (2 segundos)...")
    await asyncio.sleep(2.0)

    port_post_approve = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera Post-Aprobación: USD={port_post_approve.get('usd_balance')}, Posiciones={port_post_approve.get('positions')}")
    assert port_post_approve.get("usd_balance") < 10000.0, "La cartera debería haberse debitado tras la aprobación humana"

    # 6. Enviar señal de compra 2 (BUY) para rechazo
    print("\n[7] Enviando segunda señal de compra (BUY) de $100 USD...")
    signal2 = BASE_SIGNAL.copy()
    signal2["amountUsd"] = 100.0
    signal2["outcomeIndex"] = 1
    signal2["maxPrice"] = 0.85
    signal2["confidenceScore"] = 0.90
    
    trade_res2 = await send_post_request_async(API_URL, data=signal2)
    print(f"    -> Respuesta Trade 2 (Aceptado): {trade_res2}")

    await asyncio.sleep(2.0)

    # Buscar la segunda orden en pendientes
    pending_list2 = await send_get_request_async(SUPERVISION_PENDING_URL)
    assert pending_list2.get("count", 0) == 1, "Debería haber una orden nueva pendiente"
    order_id_2 = pending_list2.get("orders")[0].get("orderId")
    print(f"    -> Nueva orden pendiente: {order_id_2}")

    # 7. Rechazar la orden
    print(f"\n[8] Rechazando la orden {order_id_2} con motivo 'Estrategia duplicada'...")
    reject_res = await send_post_request_async(
        f"{SUPERVISION_REJECT_URL}/{order_id_2}",
        data={"reason": "Estrategia duplicada"}
    )
    print(f"    -> Resultado Rechazo: {reject_res}")

    await asyncio.sleep(2.0)

    # Verificar que la cola esté vacía y la cartera no haya cambiado
    pending_final = await send_get_request_async(SUPERVISION_PENDING_URL)
    print(f"    -> Cola Pendiente Final: {pending_final}")
    assert pending_final.get("count", 0) == 0, "La cola de supervisión debería estar vacía"

    # 8. Desactivar supervisión y verificar bypass
    print("\n[9] Desactivando supervisión humana global...")
    disable_res = await send_post_request_async(SUPERVISION_TOGGLE_URL, data={"enabled": False})
    print(f"    -> Estado de Supervisión: {disable_res}")

    print("\n[10] Enviando tercera señal (BUY) de $100 USD con supervisión desactivada...")
    signal3 = BASE_SIGNAL.copy()
    signal3["amountUsd"] = 100.0
    signal3["outcomeIndex"] = 2  # Cambiamos outcome para no tener problemas de loop
    signal3["maxPrice"] = 0.85
    signal3["confidenceScore"] = 0.90
    
    trade_res3 = await send_post_request_async(API_URL, data=signal3)
    print(f"    -> Respuesta Trade 3: {trade_res3}")

    print("    -> Esperando ejecución automática directa (2 segundos)...")
    await asyncio.sleep(2.0)

    # Verificar que se ejecutó sin colas pendientes
    pending_bypass = await send_get_request_async(SUPERVISION_PENDING_URL)
    print(f"    -> Cola Pendiente tras bypass: {pending_bypass}")
    assert pending_bypass.get("count", 0) == 0, "No debería haber órdenes pendientes"

    print("==================================================")
    print("SUITE DE FASE 6 COMPLETADA")
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
