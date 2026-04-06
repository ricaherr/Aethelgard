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

* **HU 3.4: Refactorización SignalFactory — Filtros Asimétricos Trifecta** `[DEV]`
    * **Trace_ID**: `EXEC-V7-DYNAMIC-AGGRESSION-ENGINE`
    * **Qué**: Desacoplar la Trifecta como requisito universal. Implementar flag `requires_trifecta` en metadata de señal para aplicar el análisis Oliver Velez solo a estrategias que lo requieran (Oliver Velez, Institutional Flow). Las estrategias de Ruptura y genéricas quedan exentas.
    * **Para qué**: Eliminar el veto global que bloqueaba señales válidas de estrategias no-Oliver en el pipeline de generación.
    * **Criterios**: Señal con `requires_trifecta=False` pasa el optimizador sin análisis. Señal con `strategy_id='oliver'` mantiene comportamiento original. Tests: `test_confluence_proportional.py::TestConfluenciaValidacionS9::test_confluence_asymmetry_non_oliver_bypasses_trifecta`.
    * **🖥️ UI**: Badge "Trifecta: N/A" en el feed de señales para estrategias de Ruptura.

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

* **HU 6.3: Coherence Drift Monitor** `[DONE]`
    * **Prioridad**: Media (E3)
    * **Descripción**: Algoritmo de detección de divergencia entre el comportamiento esperado del modelo y la ejecución en vivo. Completado en dos fases: v1.0 (Mar-01-2026) y v2.0 EDGE-IGNITION-PHASE-3 (Mar-30-2026) — `calculate_slippage_monitor()`, `calculate_profit_factor_drift()`, `check_coherence_veto()` + Gate 3 en `MainOrchestrator`.
    * **🖥️ UI Representation**: Medidor de "Coherencia de Modelo" con alertas visuales de deriva técnica.
    * **Trace_ID**: COHERENCE-DRIFT-2026-001 · EDGE-IGNITION-PHASE-3-COHERENCE-DRIFT

---

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
### ÉPICA E10 — Motor de Backtesting Inteligente (EDGE Evaluation Framework)
*Trace_ID: EDGE-BACKTEST-EVAL-FRAMEWORK-2026-03-24 | Sprint activo: 9+*

* **HU 7.5: DynamicThresholdController (DTC) — Motor de Exploración Activa** `[DEV]`
    * **Trace_ID**: `EXEC-V7-DYNAMIC-AGGRESSION-ENGINE`
    * **Qué**: Implementar `core_brain/adaptive/threshold_controller.py`. En modo SHADOW/BACKTEST, si una instancia no genera señales en 24h, el DTC reduce automáticamente el `dynamic_min_confidence` en 5% (piso 0.40). Feedback loop: si drawdown > 10% → recupera umbral conservador.
    * **Para qué**: Asegurar que el pool SHADOW nunca se "congele" por umbrales inalcanzables, forzando exploración activa y recolección de datos de mercado.
    * **Criterios**: Test sequía detecta correctamente 0 señales en 24h. Floor de 0.40 se respeta. Recuperación por drawdown funciona. Tests: `tests/test_dynamic_threshold_controller.py` (8 casos).
    * **🖥️ UI**: Widget "Umbral Dinámico" en dashboard Shadow mostrando el `dynamic_min_confidence` actual por instancia.

---

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)
* **HU 8.1: usr_broker_accounts — Separación Arquitectónica de Cuentas**
    * **Descripción**: Implementar tabla `usr_broker_accounts` en `schema.py` y `usr_template.db` para separar cuentas de usuario de cuentas del sistema. `sys_broker_accounts` queda exclusivamente para cuentas DEMO del sistema. `usr_broker_accounts` almacena cuentas REAL/DEMO por trader, aisladas por `user_id`. Crear `BrokerAccountsMixin` con métodos CRUD y script de migración idempotente.
    * **Referencia arquitectónica**: `docs/01_IDENTITY_SECURITY.md` Sección "Broker Account Management". Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5

---

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)

* **HU 9.4: Unified Telemetry Stream (The Synapse)** `[DEV]`
    * **Épica**: E5 | **Trace_ID**: UI-V3-FRACTAL-FUTURE-2026 / DISC-SIGNAL-REVIEW-WS-PUSH-2026-04-04 | **Sprint**: 25
    * **Qué**: Integrar eventos WebSocket de `SIGNAL_REVIEW_PENDING` en la capa UI para que la cola de revisión manual se actualice por push en tiempo real, eliminando dependencia de polling agresivo.
    * **Para qué**: Reducir latencia operativa en señales B/C y mejorar la respuesta del operador humano.
    * **Criterios de aceptación**:
        - Hook `useSignalReviews` escucha evento push y refresca estado automáticamente
        - Polling queda solo como fallback de baja frecuencia
        - Tests de contrato UI verifican bridge WS Context → Hook

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

* **HU 10.10: OEM Production Integration** `[DONE]`
    * **Épica**: E13 | **Trace_ID**: EDGE-RELIABILITY-OEM-INTEGRATION-2026
    * **Qué**: Integrar `OperationalEdgeMonitor` en `start.py` como componente activo de producción. Inyectar `shadow_storage` (instancia de `ShadowStorageManager`) al constructor para que el check `shadow_sync` pueda evaluar instancias reales. Arrancar el thread daemon del OEM como parte de la secuencia de inicialización, después del `ShadowManager`.
    * **Para qué**: El OEM existe desde Sprint 7 con 27 tests pasando, pero nunca fue integrado en el flujo de arranque real. Sin esta integración, los 8 checks de invariantes de negocio nunca se ejecutan en producción.
    * **Criterios de aceptación**:
        - `start.py` instancia `OperationalEdgeMonitor` con `shadow_storage` inyectado
        - El thread del OEM arranca y logea su primer ciclo de checks dentro de los primeros 5 minutos
        - El check `shadow_sync` evalúa instancias reales (no devuelve `WARN: shadow_storage no inyectado`)
        - Test de integración verifica que el OEM se inicia con `shadow_storage != None`
        - Tests: `tests/test_oem_production_integration.py`

* **HU 10.11: OEM Loop Heartbeat Check** `[DONE]`
    * **Épica**: E13 | **Trace_ID**: EDGE-RELIABILITY-OEM-HEARTBEAT-2026
    * **Qué**: Añadir al `OperationalEdgeMonitor` un noveno check: `_check_orchestrator_heartbeat()`. Este check lee el último timestamp de heartbeat del orchestrator desde `sys_audit_logs` o `sys_config` y emite `FAIL` si han pasado más de `max_heartbeat_gap_minutes` (configurable, default 10 min) sin actualización.
    * **Para qué**: Actualmente el OEM no detecta si el loop principal está bloqueado. Un ciclo que se cuelga en `await fetch_ohlc()` no genera ningún log ni alerta. Este check convierte el heartbeat del orchestrator (ya actualizado en cada ciclo) en una señal de vida verificable externamente.
    * **Criterios de aceptación**:
        - Check `orchestrator_heartbeat` devuelve `OK` si heartbeat < 10 min, `WARN` si 10-20 min, `FAIL` si > 20 min
        - Umbrales configurables desde `sys_config`
        - Check aparece en `get_health_summary()` y contribuye al estado CRITICAL si falla
        - `get_health_summary()` eleva a `CRITICAL` con >= 2 checks fallidos (antes era 3 — ajuste porque heartbeat ausente es siempre crítico)
        - Tests: `tests/test_oem_heartbeat_check.py` (check OK/WARN/FAIL, integración con health_summary)

* **HU 10.12: Timeout Guards en run_single_cycle** `[DONE]`
    * **Épica**: E13 | **Trace_ID**: EDGE-RELIABILITY-TIMEOUT-GUARDS-2026
    * **Qué**: Envolver las fases críticas de `run_single_cycle()` en `asyncio.wait_for()` con timeouts configurables. Fases a proteger: (1) `_request_scan()` — timeout 120s, (2) `_check_and_run_daily_backtest()` — timeout 300s, (3) `position_manager.monitor_usr_positions()` — timeout 60s. En caso de timeout: loguear `[TIMEOUT] Fase X superó Ys — ciclo continúa`, actualizar heartbeat, y continuar con la siguiente fase (no abortar el ciclo completo).
    * **Para qué**: Confirmado en Sprint 21 que `_check_and_run_daily_backtest` sin timeout colgaba tests ~250s. En producción, un `fetch_ohlc()` bloqueado por red puede congelar el loop indefinidamente sin ninguna señal de alerta. Los timeouts convierten un bloqueo silencioso en un evento observable y recuperable.
    * **Criterios de aceptación**:
        - Fase de scan con timeout: si supera 120s → `TimeoutError` capturado, log `[TIMEOUT]`, ciclo continúa
        - Fase de backtest con timeout: si supera 300s → mismo patrón
        - Timeout de `evaluate_all_instances()` (síncrono en event loop): mover a `asyncio.to_thread()` con timeout 60s
        - Timeouts configurables desde `sys_config` (clave: `phase_timeout_scan_s`, `phase_timeout_backtest_s`)
        - Tests: `tests/test_orchestrator_timeout_guards.py` (mock que no retorna → verificar que ciclo continúa)

* **HU 10.13: Contract Tests — Bugs Conocidos** `[DONE]`
    * **Épica**: E13 | **Trace_ID**: EDGE-RELIABILITY-CONTRACT-TESTS-2026
    * **Qué**: Convertir cada bug identificado en la auditoría del 27-Mar-2026 en un test de contrato que falla hoy y pasa después del fix correspondiente. Estos tests actúan como red de seguridad permanente: si algún bug regresa, el test falla inmediatamente.
    * **Para qué**: Las auditorías manuales son ciclos sin fin. Un test de contrato es una auditoría automatizada que corre en cada `validate_all.py`. Si el test existe, el bug no puede regresar sin que el sistema lo detecte.
    * **Bugs a cubrir (mínimo)**:
        1. `pilar3_min_trades` dinámico ignorado en `evaluate_all_instances()` — instancia con 8 trades debe ser HEALTHY si DB dice `min_trades=5`
        2. `StrategyRanker._degrade_strategy()` huérfano — `_evaluate_live()` debe llamar `_degrade_strategy()` y transicionar a QUARANTINE según docstring, o el docstring debe corregirse con evidencia en test
        3. Métricas de promoción SHADOW hardcodeadas en 0 — el evento WebSocket `broadcast_shadow_update` debe contener `profit_factor` y `win_rate` reales, no 0
        4. `calculate_weighted_score` no invocado — si existe, debe integrarse en `evaluate_and_rank()`, o eliminarse (dead code)
    * **Criterios de aceptación**:
        - 4 tests de contrato creados en `tests/test_contracts_known_bugs.py`, cada uno con docstring que referencia el bug y la fecha de auditoría
        - Los tests están en RED antes del fix y GREEN después
        - Cada test verifica el CONTRATO (salida correcta dado input conocido), no la implementación
        - `validate_all.py` los incluye automáticamente

* **HU 10.6: AutonomousSystemOrchestrator — Diseño FASE4** `[TODO]`
    * **Prioridad**: Media (diseño y documentación, no implementación de código aún)
    * **Descripción**: Diseñar e documentar en `docs/` el `AutonomousSystemOrchestrator` que coordina los 13 componentes EDGE existentes (OperationalEdgeMonitor, EdgeTuner, DedupLearner, CoherenceMonitor, DrawdownMonitor, ExecutionFeedbackCollector, CircuitBreaker, PositionSizeMonitor, RegimeClassifier, ClosingMonitor, AutonomousHealthService, HealthManager, CoherenceService) como un sistema coherente de auto-diagnóstico y healing. Niveles de autonomía: OBSERVE | SUGGEST | HEAL.
    * **Trace_ID**: FASE4-AUTONOMOUS-ORCHESTRATOR-DESIGN-2026-03-24

* **HU 10.16: Self-Healing & Correlation Engine** `[DONE]`
    * **Épica**: E14 | **Trace_ID**: ARCH-RESILIENCE-ENGINE-V1-C | **Sprint**: 24
    * **Qué**: `CorrelationEngine` (ventana 5 min): ≥3 `L0:MUTE` → L3 automático; ≥2 `L1:QUARANTINE` en <5 min → DEGRADED. `SelfHealingPlaybook`: reintentos L2 hasta 3 veces antes de escalar.
    * **Para qué**: Dotar al sistema de recuperación autónoma y protección contra fallos en cascada.
    * **Criterios de aceptación**:
        - 3 activos muteados en 4 min → sistema transita a `STRESSED`
        - `L2:SELF_HEAL` reintenta 3 veces antes de escalar a `L3`
        - Tests: `tests/test_correlation_engine.py`

* **HU 10.18: Refactor MainOrchestrator — Descomposición por módulos** `[DONE]`
    * **Prioridad**: Alta (deuda técnica crítica — masa crítica §4)
    * **Trace_ID**: SRE-AUDIT-2026-04-01T08:36 / ETI-P3 / DISC-003-2026-04-05
    * **Contexto**: SRE Audit 2026-04-01 identificó `main_orchestrator.py` con 160 KB (~3 400 líneas). Viola la regla de masa crítica §4 (máx. 30 KB / 500 líneas). El archivo es el único punto de fallo de toda la lógica de orquestación — un error de edición puede romper el ciclo completo.
    * **Descripción**: Extraer los sub-sistemas actuales del orquestador en módulos independientes:
        - Extraída a `core_brain/orchestrators/` con módulos especializados para init, lifecycle, scan, ejecución, guards, background tasks y discovery.
        - `main_orchestrator.py` queda como coordinador ligero con wrappers de compatibilidad para tests legacy.
    * **Criterios de aceptación**:
        - `main_orchestrator.py` reducido drásticamente respecto al monolito original
        - Ningún módulo extraído supera 500 líneas
        - Suite total verde sin cambios en tests de lógica
        - `validate_all.py` 27/27 PASSED y `start.py` verificado

* **HU 10.17b: Veto Reasoner — Endpoint API + UI Component** `[DEV]`
    * **Épica**: E14 | **Trace_ID**: ARCH-RESILIENCE-VETO-REASONER-V1B | **Sprint**: 25 (post HU 10.15 ✅)
    * **Contexto**: `ResilienceManager.get_current_status_narrative()` y la persistencia de `recovery_plan` en `sys_audit_logs` ya implementados (Sprint 24). Esta HU cubre la capa de presentación.
    * **Qué**: Endpoint `GET /api/system/health/edge` devuelve `{"posture": "STRESSED", "cause": "L2_SELF_HEAL", "recovery_plan": "..."}`. `SystemHealthPanel.tsx` muestra texto narrativo debajo del badge de postura; si `recovery_plan` es vacío, el bloque no se renderiza.
    * **Criterios de aceptación**:
        - Endpoint `/api/system/health/edge` retorna `posture`, `cause` y `recovery_plan`
        - `SystemHealthPanel.tsx` render condicional del bloque narrativo
        - Tests: `tests/test_veto_reasoner.py` — serialización del endpoint, render condicional React
