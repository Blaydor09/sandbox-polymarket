import logging
import os
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from app.adapter import router as adapter_router, broadcast_order_update
from app.event_bus import bus
from app import strategy, risk, broker, audit, observability, portfolio, execution

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
    execution.setup()
    
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

class ExecutionConfigRequest(BaseModel):
    executionMode: str
    apiClobUrl: Optional[str] = None
    exchangeAddress: Optional[str] = None
    gnosisRpcUrl: Optional[str] = None
    apiKey: Optional[str] = None
    apiSecret: Optional[str] = None
    apiPassphrase: Optional[str] = None
    privateKey: Optional[str] = None

@app.get("/api/v1/execution/config")
def get_execution_config():
    """Devuelve la configuración actual del Execution Service."""
    try:
        from app import config
        from app.execution import execution_service
        return {
            "status": "SUCCESS",
            "execution_mode": config.EXECUTION_MODE,
            "api_clob_url": config.POLYMARKET_CLOB_API_URL,
            "exchange_address": config.POLYMARKET_EXCHANGE_ADDRESS,
            "gnosis_rpc_url": config.GNOSIS_RPC_URL,
            "is_dry_run": execution_service.is_dry_run,
            "wallet_address": execution_service.signer.signer_address or "DUMMY_OR_NOT_CONFIGURED"
        }
    except Exception as e:
        logger.error(f"Error consultando config de ejecución: {e}")
        return {"status": "ERROR", "message": str(e)}

@app.post("/api/v1/execution/config")
def update_execution_config(req: ExecutionConfigRequest):
    """Actualiza dinámicamente la configuración del Execution Service en memoria."""
    try:
        from app import config
        from app.execution import execution_service
        from app.event_bus import bus
        
        mode = req.executionMode.upper()
        if mode not in ("SANDBOX", "REAL"):
            return {"status": "ERROR", "message": "El campo 'executionMode' debe ser 'SANDBOX' o 'REAL'"}
            
        config.EXECUTION_MODE = mode
        if req.apiClobUrl is not None:
            config.POLYMARKET_CLOB_API_URL = req.apiClobUrl
        if req.exchangeAddress is not None:
            config.POLYMARKET_EXCHANGE_ADDRESS = req.exchangeAddress
        if req.gnosisRpcUrl is not None:
            config.GNOSIS_RPC_URL = req.gnosisRpcUrl
        if req.apiKey is not None:
            config.POLYMARKET_API_KEY = req.apiKey
        if req.apiSecret is not None:
            config.POLYMARKET_API_SECRET = req.apiSecret
        if req.apiPassphrase is not None:
            config.POLYMARKET_API_PASSPHRASE = req.apiPassphrase
        if req.privateKey is not None:
            config.POLYMARKET_PRIVATE_KEY = req.privateKey
            
        # Re-inicializar dependencias de ejecución con las nuevas claves
        from app.execution import VaultSigner, GnosisTransactionManager
        execution_service.signer = VaultSigner(config.POLYMARKET_PRIVATE_KEY)
        execution_service.tx_manager = GnosisTransactionManager(config.GNOSIS_RPC_URL)
        execution_service.api_url = config.POLYMARKET_CLOB_API_URL
        execution_service.exchange_address = config.POLYMARKET_EXCHANGE_ADDRESS
        execution_service.is_dry_run = not (config.POLYMARKET_API_KEY and config.POLYMARKET_PRIVATE_KEY)
        
        # Suscribir o remover las subscripciones en base al nuevo modo
        bus.unsubscribe("risk.order.approved", execution_service.execute_real_order)
        from app.broker import broker
        bus.unsubscribe("risk.order.approved", broker.execute_order)
        
        if config.EXECUTION_MODE == "REAL":
            bus.subscribe("risk.order.approved", execution_service.execute_real_order)
            logger.info("Fase 5: Middleware migrado a modo REAL (Micro Trading en vivo).")
        else:
            bus.subscribe("risk.order.approved", broker.execute_order)
            logger.info("Fase 5: Middleware migrado a modo SANDBOX (Simulación Fake Broker).")
            
        return {
            "status": "SUCCESS",
            "message": f"Configuración de ejecución actualizada. Modo actual: {config.EXECUTION_MODE}",
            "is_dry_run": execution_service.is_dry_run
        }
    except Exception as e:
        logger.error(f"Error actualizando config de ejecución: {e}")
        return {"status": "ERROR", "message": str(e)}

@app.get("/api/v1/execution/balance")
def get_execution_balance(wallet_address: Optional[str] = None):
    """Consulta el balance de tokens en Gnosis Chain."""
    try:
        from app.execution import execution_service
        addr = wallet_address or execution_service.signer.signer_address or "0x8F929DeFA771f81d111CdACa936a29f8f413998b"
        balance = execution_service.tx_manager.get_token_balance(addr)
        return {
            "status": "SUCCESS",
            "wallet_address": addr,
            "usdc_balance": balance,
            "is_mocked": execution_service.tx_manager.is_mocked
        }
    except Exception as e:
        logger.error(f"Error consultando balance RPC: {e}")
        return {"status": "ERROR", "message": str(e)}
