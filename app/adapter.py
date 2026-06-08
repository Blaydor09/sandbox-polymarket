import uuid
import datetime
import logging
import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
from app.event_bus import bus

logger = logging.getLogger("AgentAdapter")
router = APIRouter()

# Lista de WebSockets activos para notificaciones en tiempo real al agente
active_connections: List[WebSocket] = []

class ReasoningModel(BaseModel):
    llmModel: str = Field(..., description="Modelo de LLM utilizado")
    promptsUsed: List[str] = Field(default_factory=list, description="Lista de prompts empleados")
    marketAnalysisSummary: str = Field(..., description="Resumen de análisis cognitivo")
    technicalIndicators: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Indicadores técnicos opcionales")

class AgentSignal(BaseModel):
    agentId: str = Field(..., description="ID del agente emisor")
    marketAddress: str = Field(..., description="Dirección del contrato del mercado en Polymarket")
    outcomeIndex: int = Field(..., ge=0, description="Índice del outcome a apostar (ej. 0 o 1)")
    side: str = Field(..., description="BUY o SELL")
    amountUsd: float = Field(..., gt=0, description="Cantidad a operar en USD")
    maxPrice: float = Field(..., gt=0, le=1.0, description="Precio límite máximo a pagar por token (0-1.0)")
    confidenceScore: float = Field(..., ge=0.0, le=1.0, description="Umbral de confianza reportado por el agente (0-1.0)")
    strategyId: str = Field(..., description="ID de la estrategia operada")
    reasoning: ReasoningModel

    @field_validator('side')
    @classmethod
    def validate_side(cls, v: str) -> str:
        upper_v = v.upper()
        if upper_v not in ('BUY', 'SELL'):
            raise ValueError("El campo 'side' debe ser 'BUY' o 'SELL'")
        return upper_v

    @field_validator('marketAddress')
    @classmethod
    def validate_market_address(cls, v: str) -> str:
        # Validación básica de dirección Ethereum/Gnosis hexadecimal
        if not re.match(r"^0x[a-fA-F0-9]{40}$", v):
            raise ValueError("marketAddress debe ser una dirección hexadecimal válida de 20 bytes (0x...)")
        return v.lower()

def sanitize_text(text: str) -> str:
    """
    Sanitiza strings de entrada para mitigar ataques de Prompt Injection e inyección de caracteres.
    Remueve caracteres de control y escapa palabras clave sensibles del middleware.
    """
    # 1. Quitar caracteres de control ASCII no imprimibles
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # 2. Escapar palabras clave comunes de manipulación del sistema de simulación/riesgo
    suspicious_patterns = [
        r"(?i)ignore\s+previous\s+instructions",
        r"(?i)bypass\s+risk",
        r"(?i)circuit\s*breaker\s*override",
        r"(?i)set\s+drawdown\s+zero"
    ]
    for pattern in suspicious_patterns:
        sanitized = re.sub(pattern, "[SANITIZED_INPUT_BLOCK]", sanitized)
        
    return sanitized.strip()

@router.post("/api/v1/trade", status_code=202)
async def ingest_agent_signal(signal: AgentSignal):
    """
    Recibe la propuesta del agente, la valida, sanitiza y la inyecta de forma asincrónica al Event Bus.
    """
    correlation_id = f"corr_{uuid.uuid4()}"
    
    # Sanitización de variables de texto libre
    sanitized_summary = sanitize_text(signal.reasoning.marketAnalysisSummary)
    
    # Construcción de la señal normalizada
    event_payload = {
        "eventId": f"evt_{uuid.uuid4()}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "version": "1.0.0",
        "correlationId": correlation_id,
        "payload": {
            "agentId": signal.agentId,
            "marketAddress": signal.marketAddress,
            "outcomeIndex": signal.outcomeIndex,
            "side": signal.side,
            "amountUsd": signal.amountUsd,
            "maxPrice": signal.maxPrice,
            "confidenceScore": signal.confidenceScore,
            "strategyId": signal.strategyId,
            "reasoning": {
                "llmModel": signal.reasoning.llmModel,
                "promptsUsed": signal.reasoning.promptsUsed,
                "marketAnalysisSummary": sanitized_summary,
                "technicalIndicators": signal.reasoning.technicalIndicators
            }
        }
    }

    logger.info(f"Señal de Agente recibida exitosamente. correlationId={correlation_id}")
    
    # Publicar el evento en el Event Bus de manera asincrónica
    await bus.publish("agent.signal.received", event_payload)

    # Retorno inmediato de aceptación (202 Accepted)
    return {
        "correlationId": correlation_id,
        "status": "PENDING_VALIDATION",
        "message": "Señal recibida y enviada a pipeline de validación"
    }

@router.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket para que el agente reciba actualizaciones de ejecución y riesgo en tiempo real.
    """
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("Cliente de agente conectado al canal WebSocket de notificaciones.")
    try:
        while True:
            # Mantener conexión abierta, ignorar mensajes entrantes del agente por este canal
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info("Cliente de agente desconectado del canal WebSocket.")

async def broadcast_order_update(event_data: Dict[str, Any]):
    """
    Envía notificaciones asíncronas a todos los agentes conectados por WebSocket.
    """
    if not active_connections:
        return
        
    logger.debug(f"Haciendo broadcast de actualización de orden al agente: {event_data.get('correlationId')}")
    
    # Payload limpio para enviar al agente
    payload = {
        "correlationId": event_data.get("correlationId"),
        "timestamp": event_data.get("timestamp"),
        "payload": event_data.get("payload")
    }
    
    for connection in active_connections:
        try:
            await connection.send_json(payload)
        except Exception as e:
            logger.error(f"Error enviando actualización por WebSocket: {e}")
