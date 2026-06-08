# OpenClaw Polymarket Sandbox Middleware

Este proyecto provee toda la infraestructura externa de control, simulación, validación, observabilidad y seguridad para probar de manera segura al agente autónomo **OpenClaw** antes de operar con fondos reales en Polymarket.

El sistema actúa como un middleware desacoplado y reactivo entre el agente IA, el motor de riesgo determinista, el simulador de mercado y el canal analítico de auditoría inmutable.

---

## 🚀 Arquitectura General del Middleware

El sistema implementa una **Arquitectura Hexagonal (Puertos y Adaptadores)** y un diseño guiado por eventos (EDA) utilizando un **Event Bus asíncrono en memoria** (Fase 1) mapeado a través de tópicos específicos.

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
                                        | (event: risk.order.approved)
                                        v
                           +------------+-----------+
                           |     Sandbox Broker     |
                           +------------------------+
                                        | (event: broker.order.execution_report)
                                        v
                           +------------+-----------+
                           |  Audit & Observability | ---> [data/audit_log.jsonl]
                           +------------------------+
```

---

## 📁 Estructura del Proyecto

El monorepo modular está estructurado de la siguiente forma:

*   [main.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/main.py): Punto de entrada de la aplicación FastAPI. Inicializa y acopla los servicios y suscriptores del bus de eventos.
*   [requirements.txt](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/requirements.txt): Declaración de dependencias del framework asíncrono.
*   [test_client.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/test_client.py): Suite de pruebas automatizada para validar los escenarios del Sandbox.
*   **`app/`**: Directorio de los módulos funcionales del middleware.
    *   [config.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/config.py): Umbrales de riesgo dinámicos, factores de slippage y parámetros Gamma para simulación de latencia.
    *   [event_bus.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/event_bus.py): Bus de eventos asíncrono reactivo implementado sobre `asyncio`.
    *   [adapter.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/adapter.py): Ingestión de señales, sanitización de ataques de inyección y streaming WebSocket.
    *   [strategy.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/strategy.py): Validador de umbrales mínimos de confianza de la IA y cálculo de tokens.
    *   [risk.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/risk.py): Gatekeeper stateful de límites de exposición, pérdidas máximas y loops repetitivos.
    *   [broker.py](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/app/broker.py): Matching local de ordenes simulando spreads de orderbooks y deslizamientos.
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
En otra consola, corre el cliente automatizado para verificar el comportamiento de validación y simulación:
```bash
python test_client.py
```
Este cliente prueba de forma secuencial 5 escenarios críticos de negocio:
1.  **Señal Válida**: Simulación de compra exitosa con inyección estocástica de deslizamiento y delay de red de blockchain.
2.  **Confianza Baja**: Rechazo de señales cuya confianza de la IA es inferior a `0.75`.
3.  **Exposición Excesiva**: Rechazo de transacciones que exceden el límite de `1000.00 USD`.
4.  **Detección de Loops**: Identifica si el agente realiza más de 3 compras/ventas idénticas consecutivas en 10 segundos, rechazando la orden e iniciando la parada de emergencia.
5.  **Circuit Breaker Activo**: Bloqueo absoluto de cualquier petición entrante si el interruptor global de riesgo ha sido disparado.

---

## 📊 Registros Analíticos y Auditoría

Cada evento transaccionado genera un registro de auditoría JSON estructurado en el archivo local:
*   [data/audit_log.jsonl](file:///c:/Users/josef/OneDrive/Desktop/Proyectos%20Fernando/sambox%20polymarket/data/audit_log.jsonl)

Cada entrada asocia la marca de tiempo, el **razonamiento cognitivo detallado de la IA (prompts y análisis)**, la decisión del motor de riesgo y los datos estocásticos de ejecución del broker bajo una misma clave de correlación (`correlationId`), facilitando auditorías forenses posteriores.
