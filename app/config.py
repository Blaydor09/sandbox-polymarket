import os

# Configuración del entorno y directorios
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Crear directorio de datos si no existe
os.makedirs(DATA_DIR, exist_ok=True)

# Archivos de persistencia
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.jsonl")
RISK_STATE_FILE = os.path.join(DATA_DIR, "risk_state.json")
HISTORICAL_FEED_FILE = os.path.join(DATA_DIR, "historical_feed.jsonl")
PORTFOLIO_STATE_FILE = os.path.join(DATA_DIR, "portfolio_state.json")

# Configuración de Cartera (Paper Trading)
INITIAL_PORTFOLIO_USD = 10000.00

# Parámetros de Replay (Market Replay Engine)
TIME_DILATION_FACTOR = 1.0      # Multiplicador de velocidad de reproducción (ej. 1.0, 5.0)

# Parámetros del Live Market Reader (API en Vivo)
POLYMARKET_WS_URL = "wss://clob.polymarket.com/ws"
LIVE_READER_ENABLED = True
LIVE_MARKETS_TO_TRACK = ["0x4b7c2957b6b15efb1f7281fbf2a2c2b0d5c0b8de"]

# Límites de Riesgo (Risk Engine)
MAX_EXPOSURE_USD = 1000.00      # Exposición máxima permitida por orden/posición
MAX_DAILY_LOSS_USD = 200.00     # Drawdown diario máximo permitido
LOOP_TIME_WINDOW_SEC = 10       # Ventana de tiempo deslizante en segundos para evaluar bucles
LOOP_MAX_ORDERS = 3             # Número máximo de órdenes en la ventana antes de disparar CB

# Umbral de Estrategia
STRATEGY_MIN_CONFIDENCE = 0.75  # Nivel de confianza mínimo para operar una señal

# Configuración de Simulación de Matching y Broker (Fake Broker)
SLIPPAGE_K_FACTOR = 0.05             # Sensibilidad del slippage al volumen de la orden
SLIPPAGE_GAUSSIAN_NOISE_STD = 0.005  # Ruido probabilístico del slippage
Subprocess_delay = 50                # Latencia base
LATENCY_GAMMA_ALPHA = 2.0            # Parámetro de forma para la distribución Gamma de latencia
LATENCY_GAMMA_BETA = 50.0            # Escala en ms (media = alpha * beta = 100ms)

# Configuración de Micro Trading Real (Fase 5)
EXECUTION_MODE = "SANDBOX"  # "SANDBOX" o "REAL"
POLYMARKET_CLOB_API_URL = "https://clob.polymarket.com"
POLYMARKET_EXCHANGE_ADDRESS = "0x4b7c2957b6b15efb1f7281fbf2a2c2b0d5c0b8de"
GNOSIS_RPC_URL = "https://rpc.gnosischain.com"
POLYMARKET_API_KEY = ""
POLYMARKET_API_SECRET = ""
POLYMARKET_API_PASSPHRASE = ""
POLYMARKET_PRIVATE_KEY = ""
