Actúa como arquitecto senior de sistemas autónomos, ingeniero de trading algorítmico, especialista en sandboxing, backend engineer y diseñador de infraestructura resiliente.

Tu tarea es diseñar COMPLETAMENTE un sistema externo de sandbox y simulación para un agente autónomo OpenClaw orientado a operar en Polymarket.

El objetivo NO es crear el agente IA.
El objetivo es crear TODA la infraestructura externa de control, simulación, validación, observabilidad y seguridad que permita probar al agente de manera segura antes de operar dinero real.

El sistema debe estar diseñado con enfoque profesional, escalable, desacoplado, modular y fault-tolerant.

# CONTEXTO DEL PROYECTO

Existe un agente OpenClaw capaz de:
- analizar mercados,
- razonar,
- tomar decisiones,
- generar señales de trading,
- decidir compra/venta,
- interactuar mediante herramientas.

Pero NO debe conectarse directamente a Polymarket.

El sistema que debes diseñar será un middleware completo entre:
- el agente OpenClaw,
- el motor de simulación,
- el sistema de riesgo,
- y eventualmente la API real de Polymarket.

El objetivo inicial es:
- pruebas sandbox,
- validación conductual,
- simulación realista,
- análisis de estabilidad,
- prevención de loops,
- control de riesgo,
- replay de mercado,
- observabilidad total.

# REQUISITOS PRINCIPALES

El sistema debe permitir:

1. Simular trading completo sin dinero real.
2. Ejecutar replay de mercados históricos.
3. Leer datos live read-only desde Polymarket.
4. Simular fills, slippage y rechazos.
5. Detectar comportamiento anómalo del agente.
6. Aplicar reglas de riesgo duras.
7. Registrar TODAS las decisiones.
8. Tener kill-switches automáticos.
9. Ser modular y extensible.
10. Poder migrar luego a trading real.

# OBJETIVO DEL RESULTADO

Debes diseñar:
- arquitectura completa,
- módulos internos,
- flujo operativo,
- contratos entre servicios,
- estructura de datos,
- sistema de eventos,
- colas,
- observabilidad,
- persistencia,
- seguridad,
- circuit breakers,
- simulador,
- validadores,
- risk engine,
- broker sandbox,
- replay engine,
- auditoría,
- y plan de escalabilidad.

NO des respuestas genéricas.
NO simplifiques.
NO hagas explicaciones superficiales.

Diseña el sistema como si fuera a entrar en producción profesional.

# EL RESULTADO DEBE INCLUIR

## 1. Arquitectura general completa

Debes generar:
- arquitectura macro,
- separación por capas,
- bounded contexts,
- responsabilidades por servicio,
- comunicación entre módulos,
- flujo de eventos,
- arquitectura lógica,
- arquitectura física,
- diseño distribuido.

Incluir:
- diagramas Mermaid,
- flujo detallado,
- dependencias.

---

## 2. Diseño de módulos

Diseña detalladamente:

### Agent Adapter
Responsable de:
- recibir output del agente,
- normalizar señales,
- validar payloads,
- transformar acciones IA en órdenes estructuradas.

Debe incluir:
- schema validation,
- normalización,
- control de versiones,
- sanitización.

---

### Strategy Controller
Responsable de:
- validar señales,
- aplicar reglas determinísticas,
- confirmar condiciones de mercado,
- filtrar señales IA.

Debe incluir:
- validadores,
- pipelines,
- filtros,
- confidence thresholds,
- validación contextual.

---

### Risk Engine
Diseñar:
- límites de exposición,
- pérdida máxima,
- control de frecuencia,
- detección de loops,
- control de drawdown,
- circuit breakers,
- emergency stop,
- reglas dinámicas.

Debe incluir:
- arquitectura interna,
- flujo de validación,
- pseudocódigo,
- reglas configurables,
- estado global.

---

### Fake Broker / Sandbox Broker
Debe:
- simular mercado,
- fills,
- rechazos,
- slippage,
- latencia,
- parcial fills,
- liquidez limitada.

Diseñar:
- motor interno,
- matching logic,
- simulación de orderbook,
- simulación probabilística,
- manejo de órdenes.

Explicar:
- cómo se comporta,
- cómo responde al agente,
- cómo mantener realismo.

---

### Market Replay Engine
Debe:
- reproducir mercados históricos,
- soportar velocidad variable,
- inyectar eventos,
- reproducir orderbooks,
- reproducir volatilidad.

Diseñar:
- formato de datasets,
- sincronización temporal,
- control de tiempo virtual,
- arquitectura del replay.

---

### Live Market Reader
Debe:
- leer Polymarket live,
- modo read-only,
- normalización,
- streaming,
- snapshots,
- resiliencia.

---

### Event Bus
Diseñar:
- sistema de eventos,
- arquitectura async,
- topics,
- queues,
- retry strategy,
- dead letter queue,
- delivery guarantees.

Explicar:
- Kafka vs Redis Streams vs NATS,
- recomendación técnica,
- ventajas y tradeoffs.

---

### Logging & Audit System
Diseñar:
- auditoría completa,
- almacenamiento de reasoning,
- decisiones,
- inputs,
- outputs,
- métricas,
- trazabilidad completa.

Incluir:
- event sourcing,
- append-only logs,
- correlación de eventos.

---

### Observability Stack
Diseñar:
- métricas,
- tracing,
- alertas,
- dashboards,
- monitoreo del agente.

Incluir:
- Prometheus,
- Grafana,
- OpenTelemetry,
- logs estructurados.

---

### Wallet Isolation Layer
Diseñar:
- aislamiento de wallets,
- firma segura,
- separación de privilegios,
- control de llaves.

Aunque inicialmente sea sandbox, preparar arquitectura futura para producción.

---

### Execution Service (futuro producción)
Diseñar:
- cómo migrar luego a trading real,
- integración Polymarket,
- firma,
- validación final,
- seguridad operacional.

---

## 3. Diseño de datos

Debes crear:

- schemas,
- modelos,
- contratos JSON,
- estructuras de eventos,
- payloads,
- estados de órdenes,
- estructura de logs.

Incluir ejemplos reales.

---

## 4. Diseño del flujo completo

Explicar detalladamente:

- desde que el agente genera una señal,
- hasta que el sandbox responde.

Incluir:
- validaciones,
- eventos,
- respuestas,
- persistencia,
- manejo de errores.

---

## 5. Seguridad y contención

Diseñar:
- sandboxing,
- aislamiento,
- control de herramientas,
- limitación de permisos,
- detección de runaway agents,
- protección contra loops,
- memory leaks,
- storms de eventos.

---

## 6. Simulación avanzada

Diseñar:
- escenarios extremos,
- fallos de red,
- API caídas,
- datos corruptos,
- eventos inesperados,
- flash crashes,
- mercados ilíquidos.

Explicar:
- cómo el sistema debe reaccionar.

---

## 7. Escalabilidad

Diseñar:
- horizontal scaling,
- múltiples agentes,
- múltiples mercados,
- multi-tenant,
- sharding,
- distribución de carga.

---

## 8. Stack tecnológico recomendado

Debes justificar:
- lenguaje backend,
- mensajería,
- base de datos,
- observabilidad,
- caching,
- simulación,
- infraestructura.

Comparar:
- Python vs Go vs Node.js,
- PostgreSQL vs ClickHouse,
- Redis vs Kafka,
- monolito modular vs microservicios.

---

## 9. Roadmap técnico

Diseñar roadmap por fases:

### Fase 1
Sandbox mínimo funcional.

### Fase 2
Replay histórico.

### Fase 3
Live read-only.

### Fase 4
Paper trading avanzado.

### Fase 5
Micro trading real.

### Fase 6
Autonomía parcial supervisada.

### Fase 7
Autonomía completa.

---

## 10. Entregables obligatorios

El resultado debe contener:

- Diagramas Mermaid.
- Arquitectura completa.
- Contratos JSON.
- Diseño técnico profundo.
- Flujo operativo.
- Riesgos técnicos.
- Tradeoffs.
- Pseudocódigo.
- Estructura de servicios.
- Estructura de carpetas.
- Diseño de eventos.
- Estrategia de testing.
- Estrategia de resiliencia.
- Estrategia de recovery.
- Estrategia de observabilidad.

NO omitas detalles.
NO resumas.
NO simplifiques.
Diseña el sistema como un entorno profesional para pruebas de agentes autónomos financieros de alto riesgo.