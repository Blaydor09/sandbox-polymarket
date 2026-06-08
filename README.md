# OpenClaw Polymarket Sandbox Middleware

Este proyecto provee toda la infraestructura externa de control, simulación, validación, observabilidad y seguridad para probar de manera segura al agente autónomo **OpenClaw** antes de operar con fondos reales en Polymarket.

El sistema actúa como un middleware desacoplado y reactivo entre el agente IA, el motor de riesgo determinista, el gestor de cartera en papel (Paper Trading), el servicio de ejecución real (Micro Trading) y el canal de supervisión humana.

---

## 🚀 Arquitectura General del Middleware

El sistema implementa una **Arquitectura Hexagonal (Puertos y Adaptadores)** y un diseño guiado por eventos (EDA) utilizando un **Event Bus asíncrono en memoria** mapeado a través de tópicos específicos.

```
                           +------------------------+
                           |  Agente IA (OpenClaw)  |
                           +------------+-----------+
                                        | (HTTP / WebSocket)
                                        v
                           +------------+-----------+
                           |     Agent Adapter      |
                           +------------+-----------+
                                        | (event: agent.signal.received)
                                        v
                           +------------+-----------+
                           |   Strategy Controller  |
                           +------------+-----------+
                                        | (event: strategy.order.validated)
                                        v
                           +------------+-----------+
                           |      Risk Engine       | <--- [Redis / Local State]
                           +------------+-----------+
                                        |
                 +----------------------+----------------------+
                 | (si supervisión habilitada)                  | (si supervisión desactivada)
                 v                                              v
      (event: risk.order.pending_approval)            (event: risk.order.approved)
                 |                                              |
      +----------+-----------+                                  |
      |  Supervision Manager | <--- [Aprobación Humana]         |
      +----------+-----------+                                  |
                 | (operator clicks approve)                    |
                 +----------------------+-----------------------+
                                        | (event: risk.order.approved)
                                        v
                        +---------------+---------------+
                        |                               |
                        v (Fase 1-4: SANDBOX)           v (Fase 5-6: REAL)
             +----------+-----------+         +---------+------------+
             |    Sandbox Broker    |         |  Execution Service   | <--- [Vault / Wallet]
             +----------+-----------+         +---------+------------+
                        |                               |
                        +---------------+---------------+
                                        | (event: broker.order.execution_report)
                                        v
                           +------------+-----------+
                           |    Portfolio Manager   | <--- [portfolio_state.json]
                           +------------+-----------+
                                        |
                                        v
                           +------------+-----------+
                           |  Audit & Observability | ---> [data/audit_log.jsonl]
                           +------------------------+
```

---

## 📁 Estructura del Proyecto

El monorepo modular está estructurado de la siguiente forma:

*   [main.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/main.py): Punto de entrada de la aplicación FastAPI. Inicializa y acopla los servicios, suscriptores del bus de eventos y endpoints REST.
*   [requirements.txt](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/requirements.txt): Declaración de dependencias del framework asíncrono y firmas blockchain.
*   [test_client.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/test_client.py): Suite de pruebas automatizada para validar de extremo a extremo los escenarios del Sandbox.
*   **`app/`**: Directorio de los módulos funcionales del middleware.
    *   [config.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/config.py): Umbrales de riesgo dinámicos, factores de slippage, parámetros Gamma para simulación de latencia y configuración de ejecución real/supervisión.
    *   [event_bus.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/event_bus.py): Bus de eventos asíncrono reactivo con soporte de suscripción/desuscripción en caliente.
    *   [adapter.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/adapter.py): Ingestión de señales, sanitización de ataques de inyección y streaming WebSocket.
    *   [strategy.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/strategy.py): Validador de umbrales mínimos de confianza de la IA y cálculo de tokens.
    *   [risk.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/risk.py): Gatekeeper stateful de límites de exposición, pérdidas de drawdown (NAV) y loops repetitivos.
    *   [broker.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/broker.py): Matching local de ordenes simulando spreads de orderbooks y deslizamientos.
    *   [replay.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/replay.py): Replay de ordenes y tickers históricos a velocidad variable.
    *   [live_reader.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/live_reader.py): Lector en vivo del WebSocket de Polymarket CLOB con fallback de contingencia.
    *   [portfolio.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/portfolio.py): Gestor de contabilidad, balance en USD, posiciones activas y valor neto (NAV).
    *   [execution.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/execution.py): Servicio de ejecución real para micro trading, firmas EIP-712 aisladas (tipo Vault) y gas bumping (RBF).
    *   [supervision.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/supervision.py): Gestor de supervisión de transacciones para colas de aprobación humana persistentes.
    *   [audit.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/audit.py): Consolidador de logs de auditoría en archivos locales.
    *   [observability.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/observability.py): Métricas JSON consolidando wins, losses, slippage promedio y latencias.

---

## 🛠️ Requisitos e Instalación

### Prerrequisitos
*   **Python 3.10 o superior** (Desarrollado y probado localmente en Python 3.14.3).

### Instalación de dependencias
1. Abre tu terminal en el directorio raíz del proyecto y ejecuta:
   ```bash
   pip install -r requirements.txt
   ```

---

## 💻 Instrucciones de Uso

### 1. Iniciar el Servidor de Sandbox
Levanta la aplicación FastAPI que hospeda los endpoints y el bus de eventos en segundo plano en el puerto `8000`:
```bash
python -m uvicorn main:app --reload --port 8000
```
La documentación interactiva OpenAPI (Swagger UI) estará disponible en: [http://localhost:8000/docs](http://localhost:8000/docs).

### 2. Ejecutar la Suite de Pruebas Automatizadas
En otra consola, corre el cliente automatizado para verificar el comportamiento del Sandbox:
```bash
python test_client.py
```
Este cliente prueba de forma secuencial los flujos críticos de la plataforma:
1.  **Fase 4 (Paper Trading Avanzado)**: Simulación de cartera con saldo disponible, cálculo de NAV dinámico y liquidación financiera al resolverse mercados.
2.  **Fase 5 (Micro Trading Real)**: Conexión con el servicio de ejecución real, firmas EIP-712 a través de un enclave aislado de claves (Vault) y ruteo dinámico de órdenes en modo `REAL`.
3.  **Fase 6 (Autonomía Parcial Supervisada)**: Retención en cola de órdenes pendientes para su aprobación o rechazo manual por parte de un operador humano antes de ser enviadas a ejecución.

---

## 📊 Registros Analíticos y Auditoría

Cada evento transaccionado genera un registro de auditoría JSON estructurado en el archivo local:
*   [data/audit_log.jsonl](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/data/audit_log.jsonl)

Cada entrada asocia la marca de tiempo, el **razonamiento cognitivo detallado de la IA (prompts y análisis)**, la decisión del motor de riesgo y los datos estocásticos de ejecución del broker bajo una misma clave de correlación (`correlationId`), facilitando la trazabilidad.
