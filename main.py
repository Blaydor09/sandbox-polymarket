import logging
import os
from fastapi import FastAPI
from app.adapter import router as adapter_router, broadcast_order_update
from app.event_bus import bus
from app import strategy, risk, broker, audit, observability

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
    
    # 2. Conectar el WebSocket del adaptador de agente al bus de eventos
    # Queremos que cualquier actualización final se envíe de vuelta al agente por WS
    bus.subscribe("risk.order.rejected", broadcast_order_update)
    bus.subscribe("broker.order.execution_report", broadcast_order_update)
    
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
