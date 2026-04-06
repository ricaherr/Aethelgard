# AETHELGARD: MASTER BACKLOG

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Catálogo oficial y único de todos los requerimientos PENDIENTES del sistema.
> - **Estructura**: 10 dominios fijos. Toda HU numerada como `HU X.Y` (X = dominio, Y = secuencia correlativa).
> - **Nuevo requerimiento**: SIEMPRE registrar aquí primero, sin estado, bajo el dominio correcto.
> - **Estados únicos permitidos**: *(sin estado)* · `[TODO]` · `[DEV]` · `[DONE]`
> - **`[DONE]`** solo si `validate_all.py` ✅ 100%. HUs completadas se **ELIMINAN** de este BACKLOG y se archivan en `SYSTEM_LEDGER.md`. Este archivo contiene únicamente trabajo pendiente.
> - **PROHIBIDO**: `[x]`, `[QA]`, `[IN_PROGRESS]`, `[COMPLETADA]`, `✅ DONE`, `[ACTIVO]`
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

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
> **Estados de HU** *(ver header de este documento y `.ai_orchestration_protocol.md` Sección 4)*:
> | Estado | Significado |
> |---|---|
> | *(sin estado)* | Identificada, sin Sprint asignado |
> | `[TODO]` | En Sprint activo, no iniciada |
> | `[DEV]` | En desarrollo activo |
> | `[DONE]` | Completada → se archiva en SYSTEM_LEDGER y se elimina de este archivo |
>
> **PROHIBIDO**: `[x]` · `[QA]` · `[IN_PROGRESS]` · `[COMPLETADA]` · `✅ DONE`

---

## 01_IDENTITY_SECURITY (SaaS, Auth, Isolation)
* **HU 1.3: User Role & Membership Level** `[TODO]`
    * **Qué**: Definir jerarquías de acceso (Admin, Pro, Basic).
    * **Para qué**: Comercialización SaaS basada en niveles de membresía.
    * **🖥️ UI Representation**: Menú de perfil donde el usuario vea su rango actual y las funcionalidades bloqueadas/desbloqueadas según su plan.

---

## 02_CONTEXT_INTELLIGENCE (Regime, Multi-Scale)
* **HU 2.3: Contextual Memory Calibration**
    * **Prioridad**: Baja (E2)
    * **Descripción**: Lógica de lookback adaptativo para ajustar la profundidad del análisis según el ruido del mercado.
    * **🖥️ UI Representation**: Slider de "Profundidad Cognitiva" que muestra cuánta historia está procesando el cerebro en tiempo real.

---

## 03_ALPHA_GENERATION (Signal Factory, Indicators)
* **HU 3.1: Contextual Alpha Scoring System**
    * **Prioridad**: Alta (E2)
    * **Descripción**: Desarrollo del motor de puntuación dinámica ponderada por el Regime Classifier y métricas del Shadow Portfolio.
    * **🖥️ UI Representation**: Dashboard "Alpha Radar" con medidores de confianza (0-100%) y etiquetas de régimen activo.

* **HU 3.3: Multi-Market Alpha Correlator**
    * **Prioridad**: Baja (E3)
    * **Descripción**: Scanner de confluencia inter-mercado para validación cruzada de señales de alta fidelidad.
    * **🖥️ UI Representation**: Widget de "Correlación Sistémica" con indicadores de fuerza y dirección multi-activo.

* **HU 3.5: Dynamic Alpha Thresholding**
    * **Prioridad**: Alta (E2)
    * **Descripción**: Lógica de auto-ajuste de barreras de entrada basada en la equidad de la cuenta y el régimen de volatilidad.
    * **🖥️ UI Representation**: Dial de "Exigencia Algorítmica" en el header, mostrando el umbral de entrada activo.


---

## 04_RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)
*(Sin HUs pendientes — todas archivadas en SYSTEM_LEDGER)*

---

## 05_UNIVERSAL_EXECUTION (EMS, Conectores FIX)
*(Sin HUs pendientes — todas archivadas en SYSTEM_LEDGER)*

---

## 06_PORTFOLIO_INTELLIGENCE (Shadow, Performance)
* **HU 6.1: Shadow Reality Engine (Penalty Injector)**
    * **Prioridad**: Alta (E2)
    * **Descripción**: Desarrollo del motor de ajuste que inyecta latencia y slippage real en el rendimiento de estrategias Shadow (Lineamiento F-001).
    * **🖥️ UI Representation**: Gráfico de equity "Shadow vs Theory" con desglose de pips perdidos por ineficiencia.

* **HU 6.2: Multi-Tenant Strategy Ranker**
    * **Prioridad**: Media (E1)
    * **Descripción**: Sistema de clasificación darwinista para organizar estrategias por rendimiento ajustado al riesgo para cada usuario.
    * **🖥️ UI Representation**: Dashboard "Strategy Darwinism" con rankings dinámicos y estados de cuarentena.


---

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
### ÉPICA E10 — Motor de Backtesting Inteligente (EDGE Evaluation Framework)
*Trace_ID: EDGE-BACKTEST-EVAL-FRAMEWORK-2026-03-24 | Sprint activo: 9+*


---

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)
* **HU 8.1: usr_broker_accounts — Separación Arquitectónica de Cuentas**
    * **Descripción**: Implementar tabla `usr_broker_accounts` en `schema.py` y `usr_template.db` para separar cuentas de usuario de cuentas del sistema. `sys_broker_accounts` queda exclusivamente para cuentas DEMO del sistema. `usr_broker_accounts` almacena cuentas REAL/DEMO por trader, aisladas por `user_id`. Crear `BrokerAccountsMixin` con métodos CRUD y script de migración idempotente.
    * **Referencia arquitectónica**: `docs/01_IDENTITY_SECURITY.md` Sección "Broker Account Management". Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5

---

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)


---

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.1: Autonomous Heartbeat & Self-Healing**
    * **Prioridad**: Media (E3)
    * **Descripción**: Sistema de monitoreo de signos vitales y auto-recuperación de servicios.
    * **🖥️ UI**: Widget de "Status Vital" con log de eventos técnicos.

* **HU 10.9: Stagnation Intelligence — Shadow con 0 operaciones**
    * **Prioridad**: Alta
    * **Trace_ID**: SHADOW-STAGNATION-INTEL-2026-03-25
    * **Contexto**: Estrategias en SHADOW con `mode='SHADOW'` acumulan 0 trades en sesiones donde las condiciones de mercado no coinciden con las ventanas de activación (ej. SESS_EXT sólo 13:00-16:00 UTC). El sistema no distingue entre "sin señal = correcto" y "sin señal = bug silencioso".
    * **Descripción**: Implementar en `OperationalEdgeMonitor` un check de estancamiento que detecte instancias SHADOW con 0 trades en las últimas N horas y emita evento diagnóstico con causa probable (fuera de ventana horaria, régimen incompatible, símbolo no habilitado). No bloquea ni promueve — sólo alerta y registra en `sys_audit_logs`.
    * **Criterios de aceptación**:
        - Instancia SHADOW con 0 trades en 24h emite evento `SHADOW_STAGNATION_ALERT`
        - Causa probable incluida: `OUTSIDE_SESSION_WINDOW` · `REGIME_MISMATCH` · `SYMBOL_NOT_WHITELISTED` · `UNKNOWN`
        - Check idempotente — no genera múltiples alertas por la misma instancia en el mismo día
        - Tests verifican detección y clasificación de causa

* **HU 10.6: AutonomousSystemOrchestrator — Diseño FASE4** `[TODO]`
    * **Prioridad**: Media (diseño y documentación, no implementación de código aún)
    * **Descripción**: Diseñar e documentar en `docs/` el `AutonomousSystemOrchestrator` que coordina los 13 componentes EDGE existentes (OperationalEdgeMonitor, EdgeTuner, DedupLearner, CoherenceMonitor, DrawdownMonitor, ExecutionFeedbackCollector, CircuitBreaker, PositionSizeMonitor, RegimeClassifier, ClosingMonitor, AutonomousHealthService, HealthManager, CoherenceService) como un sistema coherente de auto-diagnóstico y healing. Niveles de autonomía: OBSERVE | SUGGEST | HEAL.
    * **Trace_ID**: FASE4-AUTONOMOUS-ORCHESTRATOR-DESIGN-2026-03-24

