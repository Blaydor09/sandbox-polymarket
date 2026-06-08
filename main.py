import logging
import os
from fastapi import FastAPI
from pydantic import BaseModel
from app.adapter import router as adapter_router, broadcast_order_update
from app.event_bus import bus
from app import strategy, risk, broker, audit, observability, portfolio

# Configuración básica de logs de consola
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("SandboxMain")

# Inicialización de FastAPI
app = FastAPI(
    title="OpenClaw Polymarket Sandbox Middleware",
    description="Infraestructura de control, simulación, validación y observabilidad para el agente OpenClaw.",
    version="1.0.0"
)

# Registrar rutas del Adaptador de Agente
app.include_router(adapter_router)

@app.on_event("startup")
async def startup_event():
    """
    Inicializa todos los servicios internos del modular monolith
    y suscribe los manejadores a sus respectivos tópicos.
    """
    logger.info("Iniciando componentes del Sandbox Polymarket...")
    
    # 1. Configurar suscriptores de módulos
    strategy.setup()
    risk.setup()
    broker.setup()
    audit.setup()
    observability.setup()
    portfolio.setup()
    
    # 2. Conectar el WebSocket del adaptador de agente al bus de eventos
    # Queremos que cualquier actualización final se envíe de vuelta al agente por WS
    bus.subscribe("risk.order.rejected", broadcast_order_update)
    bus.subscribe("broker.order.execution_report", broadcast_order_update)
    
    # 3. Autoiniciar lector en vivo si está habilitado
    from app.config import LIVE_READER_ENABLED
    if LIVE_READER_ENABLED:
        from app.live_reader import live_market_reader
        live_market_reader.start()
        
    logger.info("Sandbox inicializado correctamente y escuchando en bus de eventos.")

@app.get("/")
def read_root():
    return {
        "status": "ONLINE",
        "service": "Polymarket Sandbox Middleware",
        "version": "1.0.0",
        "documentation": "/docs"
    }

@app.post("/api/v1/reset-risk")
def reset_risk():
    """Endpoint administrativo para reiniciar el estado de riesgo en pruebas."""
    try:
        from app.risk import risk_engine
        risk_engine.global_circuit_breaker = False
        risk_engine.agent_daily_loss = {}
        risk_engine.agent_exposure = {}
        risk_engine.recent_orders = []
        risk_engine.save_state()
        logger.info("Estado de Risk Engine reiniciado manualmente por API.")
        return {"status": "SUCCESS", "message": "Circuit breaker e historial de pérdidas reiniciados."}
    except Exception as e:
        logger.error(f"Error reiniciando riesgo: {e}")
        return {"status": "ERROR", "message": str(e)}

@app.post("/api/v1/replay/start")
async def start_replay(speed: float = 1.0):
    """Inicia el motor de replay de datos históricos de Polymarket."""
    from app.replay import replay_engine
    success = replay_engine.start(speed=speed)
    if success:
        return {"status": "SUCCESS", "message": f"Replay histórico iniciado a {speed}x"}
    else:
        return {"status": "ERROR", "message": "No se pudo iniciar el replay. Verifique si ya se encuentra activo."}

@app.post("/api/v1/replay/stop")
async def stop_replay():
    """Detiene el motor de replay de datos históricos de Polymarket."""
    from app.replay import replay_engine
    success = replay_engine.stop()
    if success:
        return {"status": "SUCCESS", "message": "Replay histórico detenido con éxito."}
    else:
        return {"status": "ERROR", "message": "El motor de Replay no está activo."}

@app.post("/api/v1/live/start")
async def start_live():
    """Inicia el lector en tiempo real de Polymarket WebSocket."""
    from app.live_reader import live_market_reader
    success = live_market_reader.start()
    if success:
        return {"status": "SUCCESS", "message": "Lector en vivo de Polymarket iniciado."}
    else:
        return {"status": "ERROR", "message": "No se pudo iniciar el lector. Verifique si ya se encuentra activo."}

@app.post("/api/v1/live/stop")
async def stop_live():
    """Detiene el lector en tiempo real de Polymarket WebSocket."""
    from app.live_reader import live_market_reader
    success = live_market_reader.stop()
    if success:
        return {"status": "SUCCESS", "message": "Lector en vivo de Polymarket detenido."}
    else:
        return {"status": "ERROR", "message": "El lector en vivo no está activo."}

@app.get("/api/v1/live/status")
async def get_live_status():
    """Devuelve el estado de conexión del lector en vivo."""
    from app.live_reader import live_market_reader
    return {
        "status": live_market_reader.status,
        "is_active": live_market_reader.is_active,
        "monitored_markets": live_market_reader.markets
    }

class MarketResolutionRequest(BaseModel):
    marketAddress: str
    winningOutcome: int

@app.get("/api/v1/portfolio")
def get_portfolio():
    """Devuelve el estado de la cartera (balance, posiciones y NAV)."""
    try:
        from app.portfolio import portfolio_manager
        return {
            "status": "SUCCESS",
            "usd_balance": round(portfolio_manager.usd_balance, 2),
            "positions": portfolio_manager.positions,
            "net_asset_value": portfolio_manager.get_net_asset_value()
        }
    except Exception as e:
        logger.error(f"Error obteniendo cartera: {e}")
        return {"status": "ERROR", "message": str(e)}

@app.post("/api/v1/portfolio/reset")
def reset_portfolio():
    """Restablece la cartera al estado inicial."""
    try:
        from app.portfolio import portfolio_manager
        portfolio_manager.reset()
        return {
            "status": "SUCCESS",
            "message": "Cartera restablecida a valores iniciales ($10,000 USD y sin posiciones)."
        }
    except Exception as e:
        logger.error(f"Error restableciendo cartera: {e}")
        return {"status": "ERROR", "message": str(e)}

@app.post("/api/v1/portfolio/resolve-market")
def resolve_market(req: MarketResolutionRequest):
    """Liquida las posiciones de un mercado resuelto de Polymarket."""
    try:
        from app.portfolio import portfolio_manager
        res = portfolio_manager.resolve_market(req.marketAddress, req.winningOutcome)
        return res
    except Exception as e:
        logger.error(f"Error resolviendo mercado: {e}")
        return {"status": "ERROR", "message": str(e)}
