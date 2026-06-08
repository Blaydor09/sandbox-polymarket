import os

# Configuración del entorno y directorios
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Crear directorio de datos si no existe
os.makedirs(DATA_DIR, exist_ok=True)

# Archivos de persistencia
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.jsonl")
RISK_STATE_FILE = os.path.join(DATA_DIR, "risk_state.json")

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
LATENCY_GAMMA_ALPHA = 2.0            # Parámetro de forma para la distribución Gamma de latencia
LATENCY_GAMMA_BETA = 50.0            # Escala en ms (media = alpha * beta = 100ms)
