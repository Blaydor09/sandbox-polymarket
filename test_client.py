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
    """Ejecuta la suite de verificación de Paper Trading Avanzado (Fase 4)."""
    print("\n==================================================")
    print("INICIANDO VERIFICACIÓN DE FASE 4: PAPER TRADING AVANZADO")
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

    # 2. Consultar estado inicial
    print("\n[2] Consultando estado inicial de la cartera...")
    port = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera Inicial: USD={port.get('usd_balance')}, NAV={port.get('net_asset_value')}, Posiciones={port.get('positions')}")

    # 3. Enviar señal de compra (BUY)
    print("\n[3] Enviando señal de compra (BUY) para Outcome 1...")
    signal = BASE_SIGNAL.copy()
    signal["amountUsd"] = 300.0
    signal["outcomeIndex"] = 1
    signal["maxPrice"] = 0.85
    signal["confidenceScore"] = 0.90
    
    trade_res = await send_post_request_async(API_URL, data=signal)
    print(f"    -> Respuesta Trade: {trade_res}")

    # Esperar a que se procese la orden en el bus de eventos y se ejecute por el broker
    print("    -> Esperando procesamiento del trade (3 segundos)...")
    await asyncio.sleep(3.0)

    # 4. Consultar estado de cartera post-compra
    print("\n[4] Consultando estado de la cartera después de la compra...")
    port_after_buy = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera Post-Compra: USD={port_after_buy.get('usd_balance')}, NAV={port_after_buy.get('net_asset_value')}, Posiciones={port_after_buy.get('positions')}")
    
    # 5. Liquidar mercado (Resolución Ganadora)
    print("\n[5] Simulando Resolución de Mercado Ganadora (Winning Outcome = 1)...")
    resolve_data = {
        "marketAddress": signal["marketAddress"],
        "winningOutcome": 1
    }
    resolve_res = await send_post_request_async(PORTFOLIO_RESOLVE_URL, data=resolve_data)
    print(f"    -> Respuesta Resolución: {resolve_res}")

    # Consultar estado post-resolución ganadora
    port_after_resolve = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera Post-Resolución Ganadora: USD={port_after_resolve.get('usd_balance')}, NAV={port_after_resolve.get('net_asset_value')}, Posiciones={port_after_resolve.get('positions')}")

    # 6. Escenario de Drawdown y Circuit Breaker
    print("\n[6] Iniciando prueba de Drawdown y Circuit Breaker...")
    # Reset de cartera para empezar limpio
    await send_post_request_async(PORTFOLIO_RESET_URL)
    await send_post_request_async(RESET_URL)

    # Enviar señal de compra grande para generar posiciones expuestas
    print("    -> Enviando compra de 500 USD...")
    signal_large = BASE_SIGNAL.copy()
    signal_large["amountUsd"] = 500.0
    signal_large["outcomeIndex"] = 1
    signal_large["maxPrice"] = 0.85
    signal_large["confidenceScore"] = 0.95
    await send_post_request_async(API_URL, data=signal_large)
    
    print("    -> Esperando procesamiento de compra grande (3 segundos)...")
    await asyncio.sleep(3.0)

    port_large_buy = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera pre-liquidación perdedora: USD={port_large_buy.get('usd_balance')}, NAV={port_large_buy.get('net_asset_value')}")

    # Liquidar mercado con outcome = 0 (losing outcome) -> Perder los 500 USD de posición
    print("\n[7] Simulando Resolución de Mercado Perdedora (Winning Outcome = 0)...")
    resolve_losing = {
        "marketAddress": signal_large["marketAddress"],
        "winningOutcome": 0
    }
    resolve_losing_res = await send_post_request_async(PORTFOLIO_RESOLVE_URL, data=resolve_losing)
    print(f"    -> Respuesta Resolución Perdedora: {resolve_losing_res}")

    port_after_loss = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera Post-Pérdida: USD={port_after_loss.get('usd_balance')}, NAV={port_after_loss.get('net_asset_value')}, Posiciones={port_after_loss.get('positions')}")

    # Enviar una nueva señal de compra para ver si el Risk Engine la rechaza por Drawdown excedido
    print("\n[8] Enviando nueva señal para verificar el Circuit Breaker de Drawdown...")
    signal_blocked = BASE_SIGNAL.copy()
    signal_blocked["amountUsd"] = 100.0
    signal_blocked["outcomeIndex"] = 1
    signal_blocked["maxPrice"] = 0.85
    signal_blocked["confidenceScore"] = 0.90
    
    blocked_res = await send_post_request_async(API_URL, data=signal_blocked)
    print(f"    -> Respuesta HTTP (debe ser aceptada a cola): {blocked_res}")
    
    print("    -> Esperando validación de riesgo (3 segundos)...")
    await asyncio.sleep(3.0)
    
    print("\n[9] Verificando estado de la cartera tras rechazo...")
    port_final = await send_get_request_async(PORTFOLIO_URL)
    print(f"    -> Cartera Final: USD={port_final.get('usd_balance')}, NAV={port_final.get('net_asset_value')}")
    print("==================================================")
    print("SUITE DE FASE 4 COMPLETADA")
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
