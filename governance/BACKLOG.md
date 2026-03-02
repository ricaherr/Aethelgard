# AETHELGARD: MASTER BACKLOG

"ESTÁNDAR DE EDICIÓN: Este documento se rige por una jerarquía de 10 Dominios Críticos. Toda nueva tarea o Historia de Usuario (HU) debe ser numerada según su dominio (ej. Tarea 4.1 para Riesgo). No se permiten cambios en esta nomenclatura para garantizar la trazabilidad del sistema."

## 🛠️ ESTÁNDAR TÉCNICO DE CONSTRUCCIÓN
1. **Backend: La Fortaleza Asíncrona**
   * **Principio de Aislamiento (Multitenancy)**: El `tenant_id` es el átomo central. Ninguna función de base de datos o lógica de negocio puede ejecutarse sin la validación del contexto del usuario.
   * **Agnosticismo de Datos**: El Core Brain no debe conocer detalles del broker (MT5/FIX). Debe trabajar solo con Unidades R y estructuras normalizadas.
   * **Rigor de Tipado**: Uso estricto de Pydantic para esquemas y `Decimal` para cálculos financieros. Prohibido el uso de `float` en lógica de dinero.
   * **Feedback Inmediato**: Cada acción del backend debe emitir un evento vía WebSocket, incluso si es un fallo, para que la UI "sienta" el latido del sistema.

2. **Frontend: La Terminal de Inteligencia**
   * **Estética "Intelligence Terminal"**: Prohibido el uso de componentes de librerías comunes (como MUI o Bootstrap estándar) sin ser personalizados al estilo Bloomberg-Dark (#050505, acentos cian/neón).
   * **Densidad de Información**: Diseñar para el experto. La UI debe mostrar datos de alta fidelidad sin saturar, usando transparencias y capas (Glassmorphism).
   * **Micro-animaciones Funcionales**: Los cambios de estado no son instantáneos; deben "pulsar" o "deslizarse". La UI debe parecer un organismo vivo, no una página web estática.
   * **Estado Centralizado en el Servidor**: El frontend es "tonto". Solo renderiza lo que el cerebro (Backend) le dice. La lógica de trading nunca reside en React.

> [!NOTE]
> **Convenciones de Estado de HU:**
> | Estado | Significado |
> |---|---|
> | *(vacío)* | HU no seleccionada para ningún Sprint |
> | `[TODO]` | Seleccionada para el Sprint activo |
> | `[DEV]` | En desarrollo activo |
> | `[QA]` | En fase de pruebas/validación |
> | `[DONE]` | Completada — eliminar del backlog y actualizar SPRINT |

---

## 01_IDENTITY_SECURITY (SaaS, Auth, Isolation)
* **HU 1.3: User Role & Membership Level** `[TODO]`
    * **Qué**: Definir jerarquías de acceso (Admin, Pro, Basic).
    * **Para qué**: Comercialización SaaS basada en niveles de membresía.
    * **🖥️ UI Representation**: Menú de perfil donde el usuario vea su rango actual y las funcionalidades bloqueadas/desbloqueadas según su plan.

## 02_CONTEXT_INTELLIGENCE (Regime, Multi-Scale)
* **HU 2.1: Multi-Scale Regime Vectorizer** `[DONE]`
    * **Prioridad**: Alta (Vector V3 - Dominio Sensorial)
    * **Descripción**: Motor de unificación temporal que lee regímenes en M15, H1, H4 con Regla de Veto Fractal (H4=BEAR + M15=BULL → RETRACEMENT_RISK).
    * **Estado**: Implementado en Sprint 3. RegimeService operativo (337 líneas, <500). 15/15 tests PASSED.
    * **🖥️ UI Representation**: Widget "Fractal Context Manager" con visualización de "Alineación de Engranajes".
    * **Artefactos**:
      - `core_brain/services/regime_service.py` (RegimeService, sincronización Ledger)
      - `models/signal.py` (FractalContext model)
      - `tests/test_regime_service.py` (15 tests, 100% coverage)
      - `ui/components/FractalContextManager.tsx` (Widget React)
* **HU 2.2: Inter-Market Divergence Scanner** `[DONE]`
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Implementación del scanner de correlación inter-mercado para validación de fuerza de régimen.
    * **🖥️ UI Representation**: Matriz de correlación dinámica con alertas de divergencia "Alpha-Sync".
* **HU 2.3: Contextual Memory Calibration**
    * **Prioridad**: Baja (Vector V2)
    * **Descripción**: Lógica de lookback adaptativo para ajustar la profundidad del análisis según el ruido del mercado.
    * **🖥️ UI Representation**: Slider de "Profundidad Cognitiva" que muestra cuánta historia está procesando el cerebro en tiempo real.

## 03_ALPHA_GENERATION (Signal Factory, Indicators)
* **HU 3.1: Contextual Alpha Scoring System**
    * **Prioridad**: Alta (Vector V2)
    * **Descripción**: Desarrollo del motor de puntuación dinámica ponderada por el Regime Classifier y métricas del Shadow Portfolio.
    * **🖥️ UI Representation**: Dashboard "Alpha Radar" con medidores de confianza (0-100%) y etiquetas de régimen activo.
* **HU 3.2: Institutional Footprint Core** `[DONE]`
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Lógica de detección de huella institucional basada en micro-estructura de precios y volumen.
    * **🖥️ UI Representation**: Superposición visual de "Liquidity Zones" y clústeres de volumen en el visor de estrategias.
* **HU 3.3: Multi-Market Alpha Correlator**
    * **Prioridad**: Baja (Vector V3)
    * **Descripción**: Scanner de confluencia inter-mercado para validación cruzada de señales de alta fidelidad.
    * **🖥️ UI Representation**: Widget de "Correlación Sistémica" con indicadores de fuerza y dirección multi-activo.
* **HU 3.4: Signal Post-Mortem Analytics** `[DONE]`
    * **Prioridad**: Media (Vector V2)
    * **Descripción**: Motor de auditoría post-trade que vincula resultados con datos de micro-estructura para alimentar el Meta-Aprendizaje.
    * **🖥️ UI Representation**: Vista "Post-Mortem" con visualización de velas de tick y marcadores de anomalías detectadas.
* **HU 3.5: Dynamic Alpha Thresholding**
    * **Prioridad**: Alta (Vector V2)
    * **Descripción**: Lógica de auto-ajuste de barreras de entrada basada en la equidad de la cuenta y el régimen de volatilidad.
    * **🖥️ UI Representation**: Dial de "Exigencia Algorítmica" en el header, mostrando el umbral de entrada activo.

## 04_RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)
* **HU 4.4: Safety Governor & Sovereignty Gateway** `[DONE]`
    * **Prioridad**: Alta (Vector V2)
    * **Descripción**: Gobernanza de riesgo basada en Unidades R con veto granular y auditoría de rechazos.
    * **Estado**: Implementado en Sprint 2. RiskManager + RejectionAudit + Endpoint /api/risk/validate.

* **HU 4.5: Exposure & Drawdown Monitor Multi-Tenant** `[DONE]`
    * **Prioridad**: Alta (Vector V2)
    * **Descripción**: Monitoreo en tiempo real de picos de equidad y umbrales de Drawdown (Soft/Hard) por tenant.
    * **Estado**: Implementado en Sprint 2. DrawdownMonitor + Endpoint /api/risk/exposure.

* **HU 4.6: Anomaly Sentinel (Antifragility Engine)** `[DONE]`
    * **Prioridad**: Alta (Vector V3 - Dominio Sensorial)
    * **Descripción**: Monitor de eventos de baja probabilidad y anomalías sistémicas (Cisnes Negros) para activar protocolos de defensa instantáneos.
    * **Estado**: Implementado en Sprint 3 (1 Marzo 2026). AnomalyService operativo (530 líneas, <500 chunks). 21/21 tests PASSED.
    * **🖥️ UI Representation**: Consola de "Thought" con tag [ANOMALY_DETECTED] y sugerencias proactivas de intervención basadas en severidad.
    * **Artefactos**:
      - `core_brain/services/anomaly_service.py` (AnomalyService - Z-Score, Flash Crash detection)
      - `data_vault/anomalies_db.py` (AnomaliesMixin - 6 métodos async para persistencia)
      - `core_brain/api/routers/anomalies.py` (6 endpoints - Thought Console, health, stats)
      - `tests/test_anomaly_service.py` (21 tests, 100% coverage + edge cases)
      - `data_vault/schema.py` (+table anomaly_events, 3 índices)
    * **Trace_ID**: BLACK-SWAN-SENTINEL-2026-001

## 05_UNIVERSAL_EXECUTION (EMS, Conectores FIX)
* **HU 5.1: High-Fidelity FIX Connector Core** `[DEV]`
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Desarrollo de la capa de transporte FIX basada en QuickFIX para conectividad directa con Prime Brokers.
    * **Estado**: Normalización de conectores completada. ExecutionService operativo. Integración FIX con Prime Brokers en progreso.
    * **🖥️ UI Representation**: Terminal de telemetría FIX con visualización de latencia ida y vuelta (RTT).
* **HU 5.2: Adaptive Slippage Controller**
    * **Prioridad**: Alta (Vector V3)
    * **Descripción**: Implementación del monitor de desviación de ejecución (Slippage) con integración en la lógica de riesgo.
    * **🖥️ UI Representation**: Badge de "Ejecución Eficiente %" en cada trade cerrado dentro del historial.
* **HU 5.3: Infrastructure Feedback Loop (The Pulse)**
    * **Prioridad**: Media (Vector V1 - Conexión básica / V3 - Feedback avanzado)
    * **Descripción**: Sistema de telemetría que informa al cerebro sobre el estado de los recursos y la red para decisiones de veto técnico.
    * **🖥️ UI Representation**: Widget de "System Vital Signs" con métricas de salud técnica y red.

## 06_PORTFOLIO_INTELLIGENCE (Shadow, Performance)
* **HU 6.1: Shadow Reality Engine (Penalty Injector)**
    * **Prioridad**: Alta (Vector V2 - Inteligencia)
    * **Descripción**: Desarrollo del motor de ajuste que inyecta latencia y slippage real en el rendimiento de estrategias Shadow (Lineamiento F-001).
    * **🖥️ UI Representation**: Gráfico de equity "Shadow vs Theory" con desglose de pips perdidos por ineficiencia.
* **HU 6.2: Multi-Tenant Strategy Ranker**
    * **Prioridad**: Media (Vector V1 - SaaS)
    * **Descripción**: Sistema de clasificación darwinista para organizar estrategias por rendimiento ajustado al riesgo para cada usuario.
    * **🖥️ UI Representation**: Dashboard "Strategy Darwinism" con rankings dinámicos y estados de cuarentena.
* **HU 6.3: Coherence Drift Monitor**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Algoritmo de detección de divergencia entre el comportamiento esperado del modelo y la ejecución en vivo.
    * **🖥️ UI Representation**: Medidor de "Coherencia de Modelo" con alertas visuales de deriva técnica.

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
* **HU 7.1: Confidence Threshold Optimizer**
    * **Prioridad**: Media (Vector V2)
    * **Descripción**: Optimización dinámica de umbrales de entrada basada en el desempeño histórico reciente.
    * **🖥️ UI**: Visualizador de "Curva de Exigencia Algorítmica".

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.1: Autonomous Heartbeat & Self-Healing**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Sistema de monitoreo de signos vitales y auto-recuperación de servicios.
    * **🖥️ UI**: Widget de "Status Vital" con log de eventos técnicos.
