# AETHELGARD: MASTER BACKLOG

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Catálogo oficial y único de todos los requerimientos del sistema.
> - **Estructura**: 10 dominios fijos. Toda HU numerada como `HU X.Y` (X = dominio, Y = secuencia correlativa).
> - **Nuevo requerimiento**: SIEMPRE registrar aquí primero, sin estado, bajo el dominio correcto.
> - **Estados únicos permitidos**: *(sin estado)* · `[TODO]` · `[DEV]` · `[DONE]`
> - **`[DONE]`** solo si `validate_all.py` ✅ 100%. HUs completadas NO se eliminan — permanecen como `[DONE]` y se archivan en SYSTEM_LEDGER.
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
> | `[DONE]` | Completada — prerequisito: `validate_all.py` ✅ 100% |
>
> **PROHIBIDO**: `[x]` · `[QA]` · `[IN_PROGRESS]` · `[COMPLETADA]` · `✅ DONE`

---

## 00_INFRA_SANEAMIENTO (Sprint Arquitectónico — 14-Mar-2026)
*Origen: Auditoría forense `docs/AUDITORIA_ESTADO_REAL.md`. Prerequisito bloqueante para todo el Canvas de Ideación.*

### Nivel 0 — Fundacional (✅ COMPLETADO — Trace_ID: ARCH-SSOT-NIVEL0-2026-03-14)
* **N0-5: Legacy DB Purge & SSOT Enforcement** `[DONE]`
    * Eliminar `data_vault/aethelgard.db` del disco. Corregir toda referencia hardcodeada a esa ruta en código de producción (`base_repo.py`, `health.py`, `strategy_loader.py`, `market.py`). Garantizar que el sistema solo use `data_vault/global/aethelgard.db` como BD global. Trace_ID: `DB-LEGACY-PURGE-2026-03-21`.
* **N0-1: sys_signal_ranking como DDL oficial** `[DONE]`
    * Eliminar `usr_performance` de `initialize_schema()`. Crear `sys_signal_ranking` con todos los campos. Actualizar `run_migrations()`. Impacto: CRÍTICO-1.
* **N0-2: Consolidación de DDL fragmentado** `[DONE]`
    * Mover `session_tokens` (de `session_manager.py`), `sys_execution_feedback` (de `execution_feedback.py`) y `position_metadata` (de `trades_db.py`) a `schema.py`. Impacto: CRÍTICO-2.
* **N0-3: FK huérfana corregida** `[DONE]`
    * `usr_strategy_logs`: `REFERENCES usr_strategies` → `REFERENCES sys_strategies`. Impacto: ALTO-1.
* **N0-4: Naming convention restaurada** `[DONE]`
    * `notifications` → `usr_notifications` en `schema.py` y `system_db.py`. Impacto: ALTO-4.

### Nivel 1 — Crítico: Stack de Conectividad FOREX (✅ COMPLETADO — 15-Mar-2026)

**Foco**: FOREX-first. cTrader como conector primario nativo async (WebSocket, sin DLL). MT5 estabilizado como alternativa. Otros mercados en Nivel 2.

* **N1-1: MT5 Single-Thread Executor** `[DONE]`
    * Crear `_MT5Task` dataclass + `_dll_executor_loop` + `_submit_to_executor` + `_submit_async` en `mt5_connector.py`. Elimina race condition entre `MT5-Background-Connector` thread (lines 223, 555), `_schedule_retry()` Timer thread y FastAPI caller thread. MT5 queda estable como alternativa. Archivos: `connectors/mt5_connector.py`. Impacto: CRÍTICO-3.
* **N1-2: cTrader Connector** `[DONE]`
    * Crear `connectors/ctrader_connector.py` (~200 líneas, hereda `BaseConnector`). WebSocket Spotware Open API para tick/OHLC streaming (M1 sin latencia, <100ms). REST para order execution. Reemplaza MT5 como conector primario FOREX. Requisito: cuenta IC Markets cTrader (free). Archivos: `connectors/ctrader_connector.py` (nuevo). Impacto: LIVE + M1 viable.
* **N1-3: Data Stack FOREX default** `[DONE]`
    * Reordenar prioridades en `DataProviderManager`: cTrader=100, MT5=70, TwelveData=disabled, Yahoo=disabled. Desactivar M1 en `config/config.json` (`enabled: false` por defecto). Stocks y futuros deshabilitados hasta Nivel 2. Archivos: `core_brain/data_provider_manager.py`, `config/config.json`. Impacto: CRÍTICO-3 datos.
* **N1-4: Warning latencia M1** `[DONE]`
    * En `ScannerEngine._scan_one()`: detectar si provider activo no es local (cTrader o MT5) Y timeframe = M1 → emitir WARNING en log + insertar entrada en `usr_notifications` con `category: DATA_RISK`, `message: "M1 con provider no-local: riesgo de señal en precio stale"`. Archivos: `core_brain/scanner.py`. Impacto: Riesgo operacional.
* **N1-5: StrategyGatekeeper Integration** `[DONE]`
    * Instanciar `StrategyGatekeeper` en `MainOrchestrator` vía DI. Conectar al flujo de señales pre-ejecución. `strategy_gatekeeper.py` ya existe (290 líneas, 17/17 tests passing) — solo falta el wiring. Archivos: `core_brain/main_orchestrator.py`. Impacto: ALTO-2.
* **N1-6: Provisión + Estabilización cTrader** `[DONE]`
    * (a) Bug fix `client_secret` hardcodeado en `ctrader_connector.py`; (b) seed placeholder `demo_broker_accounts.json` con cuenta IC Markets; (c) script `setup_ctrader_demo.py` con guía OAuth2 interactiva; (d) fix MT5 re-activation (`_sync_sys_broker_accounts_to_providers()` preserva estado `enabled`); (e) refactor `ConnectivityOrchestrator` a DB-driven: elimina `_CONNECTOR_REGISTRY` hardcodeado, columnas `connector_module`/`connector_class` en `sys_data_providers`; (f) `save_data_provider()` con `COALESCE` para no pisar datos existentes. Archivos: `connectors/ctrader_connector.py`, `core_brain/data_provider_manager.py`, `core_brain/connectivity_orchestrator.py`, `data_vault/schema.py`, `data_vault/system_db.py`, `data_vault/seed/data_providers.json`, `data_vault/seed/demo_broker_accounts.json`, `scripts/utilities/setup_ctrader_demo.py`. Impacto: OPERACIONAL + ARQUITECTURA.

* **N1-7: cTrader WebSocket Protocol — OHLC via Protobuf** `[DONE]`
    * **Contexto**: N1-2 implementó el conector con una capa REST para OHLC que apuntaba a una URL incorrecta (`demo.ctrader.com/ctrader/api/v3`). Verificación real contra la API de Spotware confirmó: (a) la API REST de Spotware **no expone endpoint de barras OHLC**; (b) la URL base correcta para REST es `api.spotware.com` con `oauth_token` como query param; (c) el `ctidTraderAccountId` es diferente al `accountNumber` visible en el broker.
    * **Implementado**:
      - `_fetch_bars_via_websocket()`: protocolo Spotware Open API sobre WebSocket binario. Flujo: `APP_AUTH_REQ → ACCOUNT_AUTH_REQ → SYMBOLS_LIST_REQ (cache) → GET_TRENDBARS_REQ → DataFrame`. Dependencia: `ctrader-open-api` (--no-deps, sin Twisted) + `protobuf`. Asyncio puro.
      - `_fetch_bars_via_rest()` → eliminado. Spotware no expone REST OHLC.
      - `execute_order`: `POST api.spotware.com/connect/tradingaccounts/{ctidTraderAccountId}/orders?oauth_token=...`
      - `get_positions`: corregir a `GET api.spotware.com/connect/tradingaccounts/{ctidTraderAccountId}/positions?oauth_token=...`
      - `_build_config`: aceptar y almacenar `ctidTraderAccountId` (ID interno Spotware, distinto a `account_number`).
      - `additional_config` en DB: agregar campo `ctid_trader_account_id`.
    * **Dependencias nuevas**: `ctrader-open-api`, `protobuf`
    * **Archivos**: `connectors/ctrader_connector.py`, `tests/test_ctrader_connector.py`, `docs/05_UNIVERSAL_EXECUTION.md`
    * **Trace_ID**: CTRADER-WS-PROTO-2026-03-21

**Orden de ejecución**: N1-1 → N1-2 → N1-3 → N1-4 → N1-5 → N1-6 → N1-7

### Nivel 2 — Inteligencia (📋 BACKLOG)
* **N2-1: JSON_SCHEMA Interpreter** `[DONE]`
    * Implementar rama `JSON_SCHEMA` en `StrategyEngineFactory`. Permite que el Bucle de Generación (Canvas Punto 4.3) cree estrategias sin código Python. Archivos: `core_brain/services/strategy_engine_factory.py`. Impacto: MEDIO-6.
* **N2-2: WebSocket Auth Standardization** `[DONE]`
    * Estandarizar `telemetry.py`, `shadow_ws.py`, `strategy_ws.py` para usar `Depends(get_ws_user)` en lugar de `_verify_token()` manual y fallback demo. Impacto: ALTO-6.

---

## 01_IDENTITY_SECURITY (SaaS, Auth, Isolation)
* **HU 1.3: User Role & Membership Level** `[TODO]`
    * **Qué**: Definir jerarquías de acceso (Admin, Pro, Basic).
    * **Para qué**: Comercialización SaaS basada en niveles de membresía.
    * **🖥️ UI Representation**: Menú de perfil donde el usuario vea su rango actual y las funcionalidades bloqueadas/desbloqueadas según su plan.

## 02_CONTEXT_INTELLIGENCE (Regime, Multi-Scale)
* **HU 2.1: Multi-Scale Regime Vectorizer** `[DONE]`
    * **Prioridad**: Alta (E3 - Dominio Sensorial)
    * **Descripción**: Motor de unificación temporal que lee regímenes en M15, H1, H4 con Regla de Veto Fractal (H4=BEAR + M15=BULL → RETRACEMENT_RISK).
    * **Estado**: Implementado en Sprint 3. RegimeService operativo (337 líneas, <500). 15/15 tests PASSED.
    * **🖥️ UI Representation**: Widget "Fractal Context Manager" con visualización de "Alineación de Engranajes".
    * **Artefactos**:
      - `core_brain/services/regime_service.py` (RegimeService, sincronización Ledger)
      - `models/signal.py` (FractalContext model)
      - `tests/test_regime_service.py` (15 tests, 100% coverage)
      - `ui/components/FractalContextManager.tsx` (Widget React)
* **HU 2.2: Inter-Market Divergence Scanner** `[DONE]`
    * **Prioridad**: Media (E3)
    * **Descripción**: Implementación del scanner de correlación inter-mercado para validación de fuerza de régimen.
    * **🖥️ UI Representation**: Matriz de correlación dinámica con alertas de divergencia "Alpha-Sync".
* **HU 2.3: Contextual Memory Calibration**
    * **Prioridad**: Baja (E2)
    * **Descripción**: Lógica de lookback adaptativo para ajustar la profundidad del análisis según el ruido del mercado.
    * **🖥️ UI Representation**: Slider de "Profundidad Cognitiva" que muestra cuánta historia está procesando el cerebro en tiempo real.

## 03_ALPHA_GENERATION (Signal Factory, Indicators)
* **HU 3.1: Contextual Alpha Scoring System**
    * **Prioridad**: Alta (E2)
    * **Descripción**: Desarrollo del motor de puntuación dinámica ponderada por el Regime Classifier y métricas del Shadow Portfolio.
    * **🖥️ UI Representation**: Dashboard "Alpha Radar" con medidores de confianza (0-100%) y etiquetas de régimen activo.
* **HU 3.2: Institutional Footprint Core** `[DONE]`
    * **Prioridad**: Media (E3)
    * **Descripción**: Lógica de detección de huella institucional basada en micro-estructura de precios y volumen.
    * **🖥️ UI Representation**: Superposición visual de "Liquidity Zones" y clústeres de volumen en el visor de estrategias.
* **HU 3.3: Multi-Market Alpha Correlator**
    * **Prioridad**: Baja (E3)
    * **Descripción**: Scanner de confluencia inter-mercado para validación cruzada de señales de alta fidelidad.
    * **🖥️ UI Representation**: Widget de "Correlación Sistémica" con indicadores de fuerza y dirección multi-activo.
* **HU 3.4: Signal Post-Mortem Analytics** `[DONE]`
    * **Prioridad**: Media (E2)
    * **Descripción**: Motor de auditoría post-trade que vincula resultados con datos de micro-estructura para alimentar el Meta-Aprendizaje.
    * **🖥️ UI Representation**: Vista "Post-Mortem" con visualización de velas de tick y marcadores de anomalías detectadas.
* **HU 3.5: Dynamic Alpha Thresholding**
    * **Prioridad**: Alta (E2)
    * **Descripción**: Lógica de auto-ajuste de barreras de entrada basada en la equidad de la cuenta y el régimen de volatilidad.
    * **🖥️ UI Representation**: Dial de "Exigencia Algorítmica" en el header, mostrando el umbral de entrada activo.

* **HU 3.6: Signal Quality Scorer (Phase 4)** `[DONE]`
    * **Descripción**: Motor unificado de puntuación. Grados: A+ (85+), A (75+), B (65+), C (50+), F (<50). Fórmula: (Técnico × 0.6) + (Contextual × 0.4).
    * **Estado**: Sprint 4 (11 Marzo 2026). 13/13 tests PASSED. Trace_ID: PHASE4-INTELLIGENCE-SCORER-2026

* **HU 3.7: Consensus Engine (Phase 4)** `[DONE]`
    * **Descripción**: Detecta múltiples estrategias convergentes en mismo setup (5 min). STRONG consenso +20%, WEAK +10%.
    * **Estado**: Sprint 4 (11 Marzo 2026). 11/11 tests PASSED. Trace_ID: PHASE4-CONSENSUS-ENGINE-2026

* **HU 3.8: Failure Pattern Registry (Phase 4)** `[DONE]`
    * **Descripción**: Aprendizaje autónomo de patrones de fallo cada 4h. Severity weights mapean failure_reason a penalizaciones. Penalidad máxima 30%.
    * **Estado**: Sprint 4 (11 Marzo 2026). 6/6 tests PASSED. Trace_ID: PHASE4-FAILURE-LEARNING-2026

## 04_RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)
* **HU 4.4: Safety Governor & Sovereignty Gateway** `[DONE]`
    * **Prioridad**: Alta (E2)
    * **Descripción**: Gobernanza de riesgo basada en Unidades R con veto granular y auditoría de rechazos.
    * **Estado**: Implementado en Sprint 2. RiskManager + RejectionAudit + Endpoint /api/risk/validate.

* **HU 4.5: Exposure & Drawdown Monitor Multi-Tenant** `[DONE]`
    * **Prioridad**: Alta (E2)
    * **Descripción**: Monitoreo en tiempo real de picos de equidad y umbrales de Drawdown (Soft/Hard) por tenant.
    * **Estado**: Implementado en Sprint 2. DrawdownMonitor + Endpoint /api/risk/exposure.

* **HU 4.6: Anomaly Sentinel (Antifragility Engine)** `[DONE]`
    * **Prioridad**: Alta (E3 - Dominio Sensorial)
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

* **HU 4.7: Economic Calendar Veto Filter (News-Based Trading Lockdown)** `[DONE]`
    * **Prioridad**: Alta (E3 - Dominio Sensorial)
    * **Descripción**: Implementación del filtro de veto por calendario económico. El sistema bloquea automáticamente nuevas posiciones durante eventos de alto impacto (NFP, decisiones de bancos centrales) basado en buffers pre/post evento (HIGH: 15m/10m, MEDIUM: 5m/3m, LOW: 0/0).
    * **Propósito**: Evitar pérdidas catastróficas por volatilidad extrema en eventos macroeconómicos sin intervención manual. Preservar agnosis: MainOrchestrator NO conoce proveedores de datos.
    * **Contrato**:
      - Método: `async get_trading_status(symbol: str, current_time: datetime) -> Dict`
      - Retorna: `{"is_tradeable": bool, "reason": str, "restriction_level": "BLOCK|CAUTION|NORMAL", ...}`
      - Latencia: < 100 ms
      - Degradación graciosa si calendar DB está down (fail-open)
    * **Mapeo de Eventos**:
      - NFP → USD (USD/JPY, EUR/USD, GBP/USD, AUD/USD)
      - ECB News → EUR (EUR/USD, GBP/EUR, EUR/JPY)
      - BOE News → GBP (GBP/USD, EUR/GBP, GBP/JPY)
      - RBA News → AUD (AUD/USD, EUR/AUD, AUD/JPY)
      - BOJ Policy → JPY (USD/JPY, EUR/JPY, GBP/JPY)
    * **Integración con RiskManager**:
      - Pilar 4.5 (Pre-RiskManager): EconomicVetoInterface bloquea ANTES de validación de riesgo
      - HIGH impact: `is_tradeable = False` (cierre de posiciones permitido)
      - MEDIUM impact: `is_tradeable = True` pero `reduction_level = "CAUTION"` (unit R escalado al 50%)
      - Position Management: Si HIGH impact, mover SL a Break-Even automáticamente
    * **Dependencias Ya Implementadas**:
      - ✅ `migrations/030_economic_calendar.sql` (schema tabla economic_calendar)
      - ✅ `connectors/economic_adapters.py` (InvestingAdapter, BloombergAdapter, ForexFactoryAdapter)
      - ✅ `connectors/economic_data_gateway.py` (factory pattern)
      - ✅ `core_brain/economic_scheduler.py` (EDGE scheduler, non-blocking)
      - ✅ `core_brain/economic_fetch_persist.py` (atomic pipeline)
      - ✅ `core_brain/economic_integration.py` (lifecycle manager)
      - ✅ `docs/INTERFACE_CONTRACTS.md` (Contract 2: EconomicVetoInterface)
      - ✅ `docs/AETHELGARD_MANIFESTO.md` (Section VIII: Veto por Calendario)
    * **Estado**: ✅ Completado Sprint N2 (16-Mar-2026). 20/20 tests PASSED. Trace_ID: ECON-VETO-FILTER-2026-001.
    * **Artefactos**:
      - `core_brain/economic_integration.py` (`get_trading_status()` implementado, caché 60s TTL)
      - `core_brain/main_orchestrator.py` (pre-trade check activo en líneas 1788, 1825, 1955)
      - `tests/test_economic_veto_interface.py` (20/20 tests PASSED)
    * **Gobernanza**: Agnosis obligatoria (no imports de brokers), DI obligatorio, SSOT (DB única fuente), degradación graciosa, <100ms latencia, auditoría vía TRACE_ID.

## 05_UNIVERSAL_EXECUTION (EMS, Conectores FIX)
* **HU 5.1: High-Fidelity FIX Connector Core** `[DONE]`
    * **Prioridad**: Media (E3)
    * **Descripción**: Desarrollo de la capa de transporte FIX basada en simplefix para conectividad directa con Prime Brokers. FIXConnector implementa BaseConnector (Logon/Logout/Heartbeat/New Order Single/Execution Report). Config SSOT desde DB, socket_factory injectable para tests. [Sprint N4]
    * **Estado**: FIXConnector completado. 14/14 tests TDD. 1466 passed · 0 failed. validate_all 25/25.
    * **🖥️ UI Representation**: Terminal de telemetría FIX con visualización de latencia ida y vuelta (RTT).
* **HU 5.2: Adaptive Slippage Controller** `[DONE]`
    * **Prioridad**: Alta (E3)
    * **Descripción**: Implementación del monitor de desviación de ejecución (Slippage) con integración en la lógica de riesgo.
    * **🖥️ UI Representation**: Badge de "Ejecución Eficiente %" en cada trade cerrado dentro del historial.
* **HU 5.4: RuntimeFix — Cooldown Storage + Provider kwargs Injection** `[DONE]`
    * **Descripción**: (a) Implementar 4 métodos de cooldown en `ExecutionMixin` sobre `sys_cooldown_tracker` (`get_active_cooldown`, `register_cooldown`, `clear_cooldown`, `count_active_cooldowns`). (b) Filtrar `kwargs` por introspección de firma (`inspect.signature`) en `_get_provider_instance` para que solo pasen los parámetros aceptados por el constructor del provider. Resuelve `errors=52/52` en runtime.
    * **Impacto**: CRÍTICO — bloquea 100% del pipeline de señales. Trace_ID: RUNTIME-FIX-COOLDOWN-KWARGS-2026-N5
* **HU 5.5: RuntimeFix — Orchestrator kwargs Injection** `[DONE]`
    * **Descripción**: Implementar introspección segura (`inspect.signature`) en `core_brain/connectivity_orchestrator.py` para instanciar correctament los proveedores de datos sin romper kwargs. Resuelve `AlphaVantageProvider.__init__() TypeError` en el orquestador principal.
* **HU 5.6: RuntimeFix — AlphaVantage Rate Limits Resilience** `[DONE]`
    * **Descripción**: Manejar el agotamiento del Free Tier en `AlphaVantageProvider` silenciosamente como `WARNING` y devolver `None` en lugar de saturar el disco con `ERROR` de No time series.

### HU 5.5: Connectivity Orchestrator (Inyección Extendida) - [DONE]
**Como** Analista / Tester
**Quiero** que el orquestador valide dependencias y omita argumentos que no son compatibles con el proveedor.
**Para** soportar diferentes arquitecturas sin romper el ciclo por `TypeError` (e.g., inyectar storage donde no va).

### HU 5.6: AlphaVantage Robust Connector - [DONE]
**Como** Trader Autónomo
**Quiero** que el AlphaVantage rechace silenciosamente o use Warnings cuando no existan datos
**Para** no ensuciar el log con excesivos ERRORS y evadir paros completos de sistema.

### HU 5.6b: Saneamiento Profundo de Alpha Vantage - [DONE]
**Como** Administrador del Sistema
**Quiero** que los errores de Rate Limit y "No time series data" en funciones de forex y crypto se reporten correctamente como WARNING/DEBUG y sin usar la palabra "stock"
**Para** mantener la telemetría limpia y la semántica correcta de los errores.

### HU 5.2.1: Refactorización Arquitectónica Multi-Usuario y Ejecución Agnóstica - [DONE]
**Como** Sistema Autónomo (SaaS)
**Quiero** que `start.py` dependa de `ConnectivityOrchestrator` de forma dinámica, leyendo proveedores de `sys_data_providers` y cuentas de ejecución separadas desde `usr_broker_accounts` **exclusivamente de las BD**
**Para** quebrar la inyección estática de `MT5Connector`, eliminar cualquier tipo de credencial o setting hardcodeado o en JSON, y permitir la escalabilidad hacia multi-tenant.

### HU 5.7: Saneamiento de Advertencias Normales - [DONE]
**Como** Administrador del Sistema
**Quiero** que los eventos esperados como el Timeout de WARMUP y el inicio de NotificationEngine vacío se emitan como INFO/DEBUG en lugar de WARNING
**Para** evitar ruido innecesario en los logs durante operaciones nominales.
* **HU 5.3: Infrastructure Feedback Loop (The Pulse)** `[DONE]`
    * **Prioridad**: Media (E1 - Conexión básica / V3 - Feedback avanzado)
    * **Descripción**: Sistema de telemetría que informa al cerebro sobre el estado de los recursos y la red para decisiones de veto técnico. `_get_system_heartbeat()` retorna CPU%/RAM real vía psutil; bloque veto en `run_single_cycle()` corta scan cuando CPU > `cpu_veto_threshold` (SSOT: dynamic_params). [Sprint N3]
    * **🖥️ UI Representation**: Widget de "System Vital Signs" con métricas de salud técnica y red.

## 06_PORTFOLIO_INTELLIGENCE (Shadow, Performance)
* **HU 6.1: Shadow Reality Engine (Penalty Injector)**
    * **Prioridad**: Alta (E2 - Inteligencia)
    * **Descripción**: Desarrollo del motor de ajuste que inyecta latencia y slippage real en el rendimiento de estrategias Shadow (Lineamiento F-001).
    * **🖥️ UI Representation**: Gráfico de equity "Shadow vs Theory" con desglose de pips perdidos por ineficiencia.
* **HU 6.2: Multi-Tenant Strategy Ranker**
    * **Prioridad**: Media (E1 - SaaS)
    * **Descripción**: Sistema de clasificación darwinista para organizar estrategias por rendimiento ajustado al riesgo para cada usuario.
    * **🖥️ UI Representation**: Dashboard "Strategy Darwinism" con rankings dinámicos y estados de cuarentena.
* **HU 6.3: Coherence Drift Monitor**
    * **Prioridad**: Media (E3)
    * **Descripción**: Algoritmo de detección de divergencia entre el comportamiento esperado del modelo y la ejecución en vivo.
    * **🖥️ UI Representation**: Medidor de "Coherencia de Modelo" con alertas visuales de deriva técnica.

* **HU 6.4: SHADOW Activation — Bucle de Evaluación Darwiniana** `[DONE]`
    * **Prioridad**: Alta (E8 — Autonomía)
    * **Sprint**: 6 | **Trace_ID**: SHADOW-ACTIVATION-2026-03-23
    * **Descripción**: Implementar el cuerpo real de `ShadowManager.evaluate_all_instances()`, actualmente un STUB que retorna dict vacío. La infraestructura (3 Pilares, CRUD, DDL) está completa. Falta el puente de orquestación que conecta la evaluación con la persistencia y la clasificación.
    * **Contexto técnico (evidencia del STUB)**:
        - `core_brain/shadow_manager.py:365-391`: `evaluate_all_instances()` retorna `{"promotions":[], ...}` vacío. Cuerpo real comentado en línea 385 como TODO.
        - `data_vault/shadow_db.py:188`: `record_performance_snapshot()` con INSERT real — **nunca invocado** (cero llamadas en codebase).
        - `sys_shadow_performance_history`: DDL e índices creados en `schema.py`. Tabla vacía en producción.
    * **Análisis financiero**: La promoción automática a LIVE NO es el scope de esta HU por prudencia. El objetivo es registrar evidencia estadística y notificar para revisión humana. Los thresholds de los 3 Pilares son institucionales y correctos (PF≥1.5, WR≥60%, DD≤12%, CL≤3, trades≥15, CV≤0.40).
    * **Tareas**:
        - [ ] Implementar cuerpo real de `evaluate_all_instances()`: `storage.list_shadow_instances(INCUBATING)` → iterar → `evaluate_single_instance()` → `record_performance_snapshot()`
        - [ ] Actualizar estado en `sys_shadow_instances` según resultado (DEAD / QUARANTINED / HEALTHY / PROMOTABLE)
        - [ ] Log en `sys_shadow_promotion_log` para instancias que alcanzan estado PROMOTABLE
        - [ ] Emitir `usr_notification` con `category: SHADOW_READY` (revisión humana — no auto-promover a capital real)
        - [ ] Tests ≥ 10: loop de evaluación, persistencia, clasificación por pilar, notificación
    * **Artefactos**:
        - `core_brain/shadow_manager.py` (implement `evaluate_all_instances`)
        - `data_vault/shadow_db.py` (usar `record_performance_snapshot`, ya implementado)
        - `tests/test_shadow_activation.py` (nuevo)
    * **🖥️ UI Representation**: Dashboard "Strategy Darwinism" (HU 6.2) con estados INCUBATING/HEALTHY/QUARANTINED/DEAD/PROMOTABLE actualizados en tiempo real.

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
* **HU 7.1: Confidence Threshold Optimizer** `[DONE]`
    * **Estado**: Implementado. `ThresholdOptimizer` (370 líneas), 21/21 tests PASSED. Wired en `MainOrchestrator` vía `TradeClosureListener`. Trace_ID: ADAPTIVE-THRESHOLD-2026-001.
    * **Prioridad**: Media (E2)
    * **Descripción**: Optimización dinámica de umbrales de entrada basada en el desempeño histórico reciente.
    * **🖥️ UI**: Visualizador de "Curva de Exigencia Algorítmica".

* **HU 7.2: Asset Efficiency Score Gatekeeper** `[DONE]`
    * **Prioridad**: Alta (E3 - Dominio Sensorial)
    * **Estado**: Implementado en Sprint 3 (2 Marzo 2026). StrategyGatekeeper operativo. 17/17 tests PASSED.
    * **Descripción**: Sistema de filtrado de eficiencia de activos que valida la performance histórica antes de cada ejecución de estrategia mediante scores en memoria (< 1ms latencia).
    * **Componentes**:
      - `data_vault/strategies_db.py` (StrategiesMixin - crear, actualizar, calcular affinity scores)
      - `core_brain/strategy_gatekeeper.py` (StrategyGatekeeper - validación ultra-rápida en memoria)
      - `data_vault/schema.py` (tablas `strategies` y `strategy_performance_logs`)
    * **Arquitectura SSOT**: 
      - Fuente única: `strategy_performance_logs` (logs de performance histórica)
      - Cálculo dinámico: `calculate_asset_affinity_score()` (basado en últimas N operaciones)
      - Cache en-memory: StrategyGatekeeper carga scores al inicializar (refresh periódico)
      - Validación pre-tick: `can_execute_on_tick()` aborta ejecución si score < min_threshold
    * **Métodos Clave**:
      - `create_strategy()`: Crear estrategia con mnemonic, affinity_scores, market_whitelist
      - `calculate_asset_affinity_score()`: Score = (win_rate * 0.5) + (pf_score * 0.3) + (momentum * 0.2)
      - `save_strategy_performance_log()`: Registrar resultado de trades para aprendizaje
      - `can_execute_on_tick()`: Validación < 1ms (100% en-memory, no DB queries)
      - `set_market_whitelist()`: Control de activos permitidos por estrategia
      - `refresh_affinity_scores()`: Recargar cache desde DB (entre sesiones)
    * **Requerimientos de Desempeño**: ✅ < 1ms latencia por validación (1000 iteraciones verificadas)
    * **🖥️ UI Representation**: Widget de "Asset Efficiency Score" en Signal Generator mostrando score actual vs threshold.
    * **Artefactos**:
      - `data_vault/strategies_db.py` (StrategiesMixin - 460 líneas)
      - `core_brain/strategy_gatekeeper.py` (StrategyGatekeeper - 290 líneas)
      - `data_vault/schema.py` (DDL para `strategies` y `strategy_performance_logs`)
      - `tests/test_strategy_gatekeeper.py` (17 tests - initialization, validation, latency, whitelist, integration)
      - `docs/AETHELGARD_MANIFESTO.md` (Sección VI - Capa de Filtrado de Eficiencia)
    * **Validación**: 17/17 tests PASSED | validate_all.py: 14/14 modules PASSED | start.py: OK
    * **Gobernanza**: Inyección de dependencias (StorageManager), SSOT en DB, immutabilidad de thresholds
    * **Trace_ID**: EXEC-EFFICIENCY-SCORE-001

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)
* **HU 8.1: usr_broker_accounts — Separación Arquitectónica de Cuentas** `[DONE]`
    * **Descripción**: Implementar tabla `usr_broker_accounts` en `schema.py` y `usr_template.db` para separar cuentas de usuario de cuentas del sistema. `sys_broker_accounts` queda exclusivamente para cuentas DEMO del sistema (data feeds, SHADOW mode sin usuario). `usr_broker_accounts` almacena cuentas REAL/DEMO por trader, aisladas por `user_id`. Crear `BrokerAccountsMixin` con métodos CRUD y script de migración idempotente.
    * **Referencia arquitectónica**: `docs/01_IDENTITY_SECURITY.md` Sección "Broker Account Management". Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.1: Autonomous Heartbeat & Self-Healing**
    * **Prioridad**: Media (E3)
    * **Descripción**: Sistema de monitoreo de signos vitales y auto-recuperación de servicios.
    * **🖥️ UI**: Widget de "Status Vital" con log de eventos técnicos.
