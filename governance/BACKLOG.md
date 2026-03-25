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
* **HU 3.9: Signal Factory — Filtro de Activos via InstrumentManager** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA (Bloqueante — 924 señales/día descartadas)
    * **Descripción**: La SignalFactory usa `get_all_usr_assets_cfg()` (tabla con 5 activos stale) para filtrar símbolos habilitados. Inyectar `InstrumentManager` como dependencia opcional y reemplazar el filtro con `instrument_manager.get_enabled_symbols()` (18 símbolos correctos desde `sys_config`). Sin este fix, 15 de 18 símbolos son descartados silenciosamente y no se generan señales suficientes para que SHADOW acumule trades.
    * **Trace_ID**: PIPELINE-UNBLOCK-SIGNAL-FACTORY-2026-03-24

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

* **HU 7.3: Pipeline de Ciclo de Vida BACKTEST → SHADOW → LIVE** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA (Bloqueante para el flujo de inversión)
    * **Trace_IDs**: EXEC-V5-BACKTEST-SCENARIO-ENGINE · EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23
    * **Descripción**: Define el ciclo de vida completo de las estrategias. Toda estrategia parte en modo `BACKTEST` (Filtro 0), avanza a `SHADOW` si supera score ≥ 0.75 en los 3 Stress Clusters, y finalmente a `LIVE` si pasa los 3 Pilares de incubación SHADOW.
    * **Qué**:
        - **3 Modos de Vida**: `BACKTEST` | `SHADOW` | `LIVE` en `sys_strategies.mode`
        - **4 Scores por estrategia**:
            - `score_backtest`: AptitudeMatrix.overall_score del ScenarioBacktester
            - `score_shadow`: Desempeño 3 Pilares en incubación DEMO (normalizado)
            - `score_live`: Desempeño acumulado en cuenta REAL (EdgeTuner feedback)
            - `score`: Consolidado → `score_live×0.50 + score_shadow×0.30 + score_backtest×0.20`
        - **Motor Filtro 0**: `ScenarioBacktester` — inyector de Slices, no línea de tiempo
            - 3 Stress Clusters: `HIGH_VOLATILITY`, `STAGNANT_RANGE`, `INSTITUTIONAL_TREND`
            - Output: `AptitudeMatrix` JSON con PF + MaxDD por régimen detectado
            - Gate rule: `overall_score >= 0.75` para acceso a SHADOW
        - **EdgeTuner**: método `validate_suggestion_via_backtest()` como guardián del Filtro 0
        - **Migración DB** aplicada sin recrear tablas (backup: `aethelgard_BEFORE_STRATEGY_LIFECYCLE_20260323_205949.db`)
        - **6 estrategias existentes** migradas a `mode='BACKTEST'` sin pérdida de datos
        - Cada simulación genera `TRACE_BKT_VALIDATION_...` en `sys_shadow_promotion_log`
        - 36/36 tests PASSED
    * **Para qué**: Garantizar que solo estrategias con aptitud demostrada en condiciones de estrés entren al pool SHADOW, y solo estrategias probadas en SHADOW avancen a LIVE. Scoring por modo permite comparar estrategias objetivamente.
    * **🖥️ UI Representation**:
        - Panel "Strategy Lifecycle" con pipeline visual `BACKTEST → SHADOW → LIVE`
        - "Aptitude Matrix Viewer": tabla de scores por régimen con semáforo (verde ≥ 0.75 / amarillo 0.50–0.74 / rojo < 0.50)
        - Score consolidado visible por estrategia con desglose de ponderación
    * **Artefactos**:
        - `core_brain/scenario_backtester.py` (ScenarioBacktester, AptitudeMatrix, ScenarioSlice, RegimeResult, StressCluster)
        - `core_brain/edge_tuner.py` (+`validate_suggestion_via_backtest()`)
        - `data_vault/schema.py` (DDL + 2 migraciones: sys_shadow_instances + sys_strategies)
        - `docs/07_ADAPTIVE_LEARNING.md` (Secciones "Ciclo de Vida" y "Filtro 0" añadidas)
        - `tests/test_scenario_backtester.py` (36 tests, 100% PASSED)

* **HU 7.4: BacktestOrchestrator — Pipeline BACKTEST → SHADOW con datos reales** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA
    * **Trace_ID**: EXEC-V5-BACKTEST-ORCHESTRATOR-2026-03-23
    * **Descripción**: Absorbió el alcance original de HU 7.4. Implementa el orquestador completo de backtesting usando datos reales del DataProviderManager (cTrader/Yahoo). Ningún dato sintético en producción.
    * **Qué implementado**:
        - `BacktestOrchestrator` en `core_brain/backtest_orchestrator.py`
        - Datos reales: `DataProviderManager.fetch_ohlc()` con fallback automático (cTrader → Yahoo)
        - Barras dinámicas: fetch inicial 500 bars + retry hasta 1000 si `trades/cluster < 15`
        - Split por régimen: ventanas deslizantes de 120 bars → RegimeClassifier → StressCluster
        - `_synthesise_cluster_window()`: fallback ATR-anchored si un cluster no aparece en los datos reales
        - Cooldown 24h por estrategia (bypass con `force=True`)
        - Promoción automática `BACKTEST → SHADOW` si `score_backtest ≥ 0.75`
        - Integrado en `MainOrchestrator`: ciclo diario en main loop (mismo patrón que ShadowManager)
        - `config/stress_scenarios.json`: catálogo de escenarios + tabla de bars por timeframe (CLT-derivado)
        - Variable sin uso `symbol` corregida en `main_orchestrator.py` línea 1014
    * **Artefactos**:
        - `core_brain/backtest_orchestrator.py` (BacktestOrchestrator)
        - `core_brain/main_orchestrator.py` (+init backtest_orchestrator, +`_check_and_run_daily_backtest()`)
        - `config/stress_scenarios.json` (catálogo con bars por timeframe derivados de CLT)
        - `tests/test_backtest_orchestrator.py`
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

* **HU 7.5: BacktestOrchestrator — Cooldown por last_backtest_at** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA (Bloqueante — backtesting permanentemente bloqueado)
    * **Descripción**: `_is_on_cooldown()` usa `updated_at` (campo de escritura general) en lugar de un campo dedicado `last_backtest_at`. Como `updated_at` fue seteado por migración/seed a '2026-03-24 04:50:50' para las 6 estrategias, el cooldown de 24h bloquea indefinidamente cualquier backtest. Fix: agregar columna `last_backtest_at TIMESTAMP DEFAULT NULL` a `sys_strategies` vía migración; actualizar `_is_on_cooldown()`, `_update_strategy_scores()` y `_load_backtest_strategies()` para usar este campo.
    * **Trace_ID**: PIPELINE-UNBLOCK-BACKTEST-COOLDOWN-2026-03-24

---
### ÉPICA E10 — Motor de Backtesting Inteligente (EDGE Evaluation Framework)
*Trace_ID épica: EDGE-BACKTEST-EVAL-FRAMEWORK-2026-03-24*

---

* **HU 7.6: Interfaz estándar de evaluación histórica en estrategias** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA (prerequisito bloqueante para HU 7.7)
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-76-STRATEGY-INTERFACE-2026-03-24
    * **Contexto**: `ScenarioBacktester._simulate_trades()` usa un modelo momentum genérico idéntico para todas las estrategias. Los scores actuales no reflejan la lógica real de ninguna estrategia — son el rendimiento de momentum sobre los datos de esa estrategia.
    * **Descripción**: Definir e implementar el contrato `evaluate_on_history(df: DataFrame, params: Dict) -> List[TradeResult]` en la clase base de estrategias. Adaptar las 6 estrategias existentes. Definir el modelo `TradeResult` con: `entry_price`, `exit_price`, `pnl`, `direction`, `bars_held`, `regime_at_entry`, `sl_distance`, `tp_distance`.
    * **Criterios de aceptación**:
        - Clase base `BaseStrategy` expone `evaluate_on_history()` con firma estándar
        - Las 6 estrategias implementan el método usando su lógica real de señales
        - `TradeResult` es un dataclass tipado con todos los campos requeridos
        - Tests unitarios por estrategia verifican que `evaluate_on_history()` produce trades distintos entre estrategias sobre los mismos datos
    * **Artefactos**: `core_brain/strategies/base_strategy.py`, `core_brain/strategies/*.py` (×6), `models/trade_result.py`

* **HU 7.7: Simulación real por estrategia — despacho a lógica propia** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-77-REAL-SIMULATION-2026-03-24
    * **Dependencia**: HU 7.6
    * **Contexto**: El motor momentum genérico en `_simulate_trades()` hace que todos los scores sean iguales independientemente de la estrategia. Los scores actuales (0.5543 para MOM_BIAS y SESS_EXT) son deterministas sobre datos parcialmente sintéticos, no evidencia real de aptitud.
    * **Descripción**: Reemplazar `ScenarioBacktester._simulate_trades()` por despacho a `strategy.evaluate_on_history()`. El backtester recibe `strategy_id`, resuelve la clase correspondiente via `StrategyEngineFactory`, y delega la simulación a la lógica real. Los `parameter_overrides` se pasan como `params` al método.
    * **Criterios de aceptación**:
        - `_simulate_trades()` elimina el modelo momentum hardcodeado
        - Cada estrategia produce un conjunto de trades distinto sobre los mismos datos
        - Los scores de las 6 estrategias difieren entre sí después del cambio
        - Tests verifican despacho correcto por `strategy_id`
    * **Artefactos**: `core_brain/scenario_backtester.py`

* **HU 7.8: Contexto estructural declarado en sys_strategies** `[DONE]`
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-78-STRUCTURAL-CONTEXT-2026-03-24
    * **Contexto**: `sys_strategies` no tiene campos para declarar el régimen de mercado requerido ni los timeframes válidos. El backtester asume H1 siempre (columna `default_timeframe` no existe) y no tiene forma de saber si una estrategia requiere TREND o funciona en cualquier régimen.
    * **Descripción**: DDL — agregar a `sys_strategies`:
        - `required_regime TEXT DEFAULT 'ANY'` — valores: `'TREND'`, `'RANGE'`, `'VOLATILE'`, `'ANY'`
        - `required_timeframes TEXT DEFAULT '[]'` — JSON array, ej: `["M5","M15"]`; vacío = descubrir empíricamente
        - `execution_params TEXT DEFAULT '{}'` — JSON con `confidence_threshold`, `risk_reward` (libera `affinity_scores` de ese rol)
        Migration automática idempotente. Poblar los 6 registros existentes con valores derivados de la lectura del código de cada estrategia (conocimiento estructural, no empírico).
    * **Criterios de aceptación**:
        - Migration aplicada sin recrear tablas ni perder datos existentes
        - 6 estrategias tienen `required_regime` y `required_timeframes` poblados
        - `execution_params` contiene `confidence_threshold` y `risk_reward` por estrategia
        - `affinity_scores` queda libre para uso exclusivo de evidencia empírica (HU 7.13)
        - Tests de migration verifican idempotencia
    * **Artefactos**: `data_vault/schema.py`

* **HU 7.9: Evaluación multi-timeframe con round-robin y pre-filtro**
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-79-MULTI-TF-ROUNDROBIN-2026-03-24
    * **Dependencia**: HU 7.8
    * **Contexto**: `_resolve_symbol_timeframe()` siempre usa H1 (columna inexistente → fallback). Las estrategias M5 se evalúan en H1 — incompatibilidad de contexto temporal. Evaluar todos los timeframes en un ciclo dispararía el costo x4.
    * **Descripción**: Implementar evaluación multi-timeframe con dos mecanismos de control de costo:
        1. **Si `required_timeframes` declarado** → evaluar solo esos timeframes (saber estructural)
        2. **Si `required_timeframes` vacío** → rotar un timeframe por ciclo en orden configurable desde `sys_config` (`["M5","M15","H1","H4"]` default). El estado del ciclo actual se persiste en `sys_strategy_pair_coverage` (HU 7.17).
        Pre-filtro antes de cualquier fetch: si `required_regime != 'ANY'` y el régimen actual del par no coincide → skip este ciclo, programar para el próximo.
    * **Criterios de aceptación**:
        - Estrategias con `required_timeframes` poblado se evalúan solo en esos timeframes
        - Round-robin avanza correctamente entre ciclos (estado persistido)
        - Pre-filtro de régimen elimina fetches innecesarios antes del I/O
        - Tests verifican que el round-robin no repite timeframe hasta completar el ciclo
    * **Artefactos**: `core_brain/backtest_orchestrator.py`, `data_vault/schema.py`

* **HU 7.10: RegimeClassifier real en pipeline de backtesting**
    * **Prioridad**: Media
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-710-REGIME-CLASSIFIER-2026-03-24
    * **Contexto**: `_split_into_cluster_slices()` usa `backtester._detect_regime()` — método simple basado en ATR ratio + slope. El sistema tiene `RegimeClassifier` (ADX + SMA200 + hysteresis + 4 regímenes) en `core_brain/regime.py` que NO se usa en backtesting. Dos clasificadores paralelos con calidad distinta.
    * **Descripción**: Reemplazar `backtester._detect_regime()` en `_split_into_cluster_slices()` por `RegimeClassifier` de `regime.py`. Instanciar el clasificador, llamar `load_ohlc(window)` y `classify()` por cada ventana deslizante. Mantener el mapeo `REGIME_TO_CLUSTER` existente. Un único clasificador de régimen en todo el sistema.
    * **Criterios de aceptación**:
        - `_split_into_cluster_slices()` usa `RegimeClassifier` con ADX real
        - `ScenarioBacktester._detect_regime()` queda solo para tests legacy o se elimina
        - La clasificación NORMAL/TREND/RANGE/CRASH mapea correctamente a `StressCluster`
        - Tests verifican que ventanas con ADX > 25 clasifican como INSTITUTIONAL_TREND
    * **Artefactos**: `core_brain/backtest_orchestrator.py`

* **HU 7.11: Cadena de fallback multi-proveedor — eliminar síntesis en producción** `[DONE]`
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-711-MULTI-PROVIDER-NOSYNTHESIS-2026-03-24
    * **Contexto**: Cuando un cluster no aparece en los datos del proveedor primario, `_synthesise_cluster_window()` genera barras con ruido gaussiano (seed=42). El header del archivo declara "Real data only — no synthetic data in production", pero el código lo viola silenciosamente. Backtest sobre datos sintéticos produce scores no reproducibles en mercado real.
    * **Descripción**: Reemplazar la síntesis por una cadena de fallback con datos reales:
        1. Proveedor primario — ventana inicial (500 barras)
        2. Proveedor primario — ventana extendida hasta máximo configurable desde `sys_config` (default: 3000 barras)
        3. Proveedores secundarios — iterar `DataProviderManager` en orden de prioridad
        4. Si ningún proveedor tiene el cluster → marcar como `UNTESTED_CLUSTER` con `confidence_weight=0.0`
        Un cluster `UNTESTED` no bloquea la evaluación ni la promoción. Se registra en `AptitudeMatrix` como `untested_clusters: List[str]`. La síntesis (`_synthesise_cluster_window`) se elimina del path de producción; se mantiene únicamente en tests unitarios con flag explícito.
    * **Criterios de aceptación**:
        - `_synthesise_cluster_window()` no se llama en el path de producción
        - `AptitudeMatrix` incluye `untested_clusters: List[str]`
        - El score de un cluster `UNTESTED` no penaliza artificialmente el `overall_score`
        - Tests verifican el orden correcto de la cadena de fallback
        - Log emite WARNING cuando un cluster queda como UNTESTED
    * **Artefactos**: `core_brain/backtest_orchestrator.py`, `core_brain/scenario_backtester.py`

* **HU 7.12: Adaptive Backtest Scheduler — cooldown dinámico y queue de prioridad**
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-712-ADAPTIVE-SCHEDULER-2026-03-24
    * **Dependencia**: HU 10.7 (requiere `OperationalModeManager` para leer el contexto)
    * **Contexto**: El cooldown de 24h es rígido. En contexto `BACKTEST_ONLY` con recursos libres, el sistema desperdicia capacidad de cómputo esperando el siguiente ciclo. En contexto `LIVE_ACTIVE`, 24h puede ser demasiado frecuente.
    * **Descripción**: Reemplazar el cooldown fijo por un scheduler adaptativo:
        - **Cooldown dinámico por contexto operacional**:
            - `BACKTEST_ONLY` + recursos > 70% libres → 0h (ejecutar al siguiente slot disponible)
            - `BACKTEST_ONLY` + recursos 40–70% libres → 2h
            - `SHADOW_ACTIVE` → 12h
            - `LIVE_ACTIVE` → 24h (comportamiento original)
            - Floor absoluto: nunca re-evaluar el mismo par+tf en menos de 1h (protección rate limit del data provider)
        - **Queue de prioridad** para selección del siguiente backtest:
            - P1: Estrategias con `last_backtest_at = NULL`
            - P2: Combinaciones `PENDING` con régimen compatible actualmente
            - P3: Combinaciones con `UNTESTED_CLUSTER`
            - P4: Alta varianza entre ciclos (score inestable)
            - P5: `confidence` baja (pocos trades acumulados)
            - P6: Re-evaluación de rutina (detección de drift)
        - **Fetch incremental**: guardar `last_evaluated_at` por `(strategy_id, symbol, timeframe)`. En ciclos subsiguientes, solo fetchear barras nuevas desde esa fecha. Reduce I/O en >70% en steady state.
        - **Cooldown adaptativo por estabilidad**: si `effective_score` varió < 3% en últimos 3 ciclos → extender cooldown automáticamente a 7 días.
        - **Rate limiter por proveedor**: gap mínimo configurable entre requests al mismo proveedor (default: 30s).
    * **Criterios de aceptación**:
        - En contexto `BACKTEST_ONLY` con CPU < 30%, el scheduler ejecuta backtests consecutivos sin esperar 24h
        - El floor de 1h por par+tf se respeta en todos los contextos
        - El queue de prioridad selecciona correctamente P1 sobre P6
        - Fetch incremental solo trae barras nuevas en el segundo ciclo
        - Tests verifican cada nivel de prioridad del queue
    * **Artefactos**: `core_brain/backtest_orchestrator.py`, `data_vault/schema.py`

* **HU 7.13: Rediseño semántico de affinity_scores**
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-713-AFFINITY-REDESIGN-2026-03-24
    * **Dependencia**: HU 7.8 (libera el campo de `confidence_threshold`/`risk_reward`)
    * **Contexto**: `affinity_scores` almacena opiniones del desarrollador (`{"EUR/USD": 0.92}`) que el código nunca usa como scores — busca `confidence_threshold` y `risk_reward` que no existen, siempre cae a defaults. El campo está semánticamente roto: fue diseñado para un propósito y usado para otro.
    * **Descripción**: Redefinir `affinity_scores` como OUTPUT exclusivo del proceso de evaluación empírica. Estructura por par:
        ```json
        {
          "EURUSD": {
            "effective_score": 0.71,
            "raw_score": 0.84,
            "confidence": 0.83,
            "n_trades": 52,
            "profit_factor": 1.74,
            "max_drawdown": 0.11,
            "win_rate": 0.57,
            "optimal_timeframe": "M15",
            "regime_evaluated": "TREND",
            "status": "QUALIFIED",
            "cycles": 3,
            "last_updated": "2026-03-24T18:46:08Z"
          }
        }
        ```
        Los valores actuales hardcodeados (`{"EUR/USD": 0.92}`) se eliminan. El campo inicia vacío `{}` para todas las estrategias y se pobla únicamente por el proceso de backtesting.
    * **Criterios de aceptación**:
        - Migration limpia el contenido actual de `affinity_scores` en las 6 estrategias
        - `_extract_parameter_overrides()` lee `execution_params` (no `affinity_scores`)
        - `_update_strategy_scores()` escribe la estructura completa por par
        - Tests verifican que el score por par incluye todos los campos requeridos
    * **Artefactos**: `core_brain/backtest_orchestrator.py`, `data_vault/schema.py`

* **HU 7.14: Backtesting multi-par secuencial**
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-714-MULTI-PAIR-2026-03-24
    * **Dependencia**: HU 7.13
    * **Contexto**: `_resolve_symbol_timeframe()` toma `whitelist[0]` — solo el primer par. Una estrategia con 4 pares en el whitelist evalúa únicamente EURUSD. Toda la evaluación actual es single-pair.
    * **Descripción**: `_execute_backtest()` itera sobre todos los símbolos habilitados en `InstrumentManager`. Para cada par:
        - Aplica pre-filtro de régimen (HU 7.9)
        - Ejecuta `ScenarioBacktester` con la lógica real de la estrategia (HU 7.7)
        - Calcula `effective_score` con confianza estadística (HU 7.15)
        - Persiste resultado en `affinity_scores` por par (HU 7.13)
        Ejecución **secuencial** (no paralela) dentro del ciclo de la estrategia activa. El `AdaptiveBacktestScheduler` (HU 7.12) controla cuántos pares se procesan por ciclo según el budget de recursos disponible.
    * **Criterios de aceptación**:
        - `affinity_scores` contiene resultados para múltiples pares tras el primer ciclo completo
        - El `asyncio.gather()` actual se reemplaza por ejecución secuencial de estrategias
        - El Resource Guard (HU 10.7) se consulta entre cada par evaluado
        - Tests verifican que pares con régimen incompatible son skipped correctamente
    * **Artefactos**: `core_brain/backtest_orchestrator.py`

* **HU 7.15: Score con confianza estadística n/(n+k)**
    * **Prioridad**: Alta
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-715-CONFIDENCE-SCORING-2026-03-24
    * **Contexto**: El criterio actual de "mínimo 30 trades" es binario y arbitrario. Penaliza estrategias de baja frecuencia legítimas y trata igual a 29 trades (rechazado) y 31 (aceptado).
    * **Descripción**: Implementar función de confianza estadística continua:
        ```
        confidence(n, k) = n / (n + k)
        effective_score  = raw_score × confidence(n_trades, k)
        ```
        Donde `k` (prior de trades equivalentes) es configurable por tipo de estrategia desde `sys_config` (default: 20). Interpretación de `k`: número de trades para alcanzar 50% de confianza.
        Estados del par determinados por `effective_score`:
        - `effective_score >= 0.55` → `QUALIFIED` → incluir en whitelist
        - `effective_score < 0.20` AND `confidence >= 0.50` → `REJECTED` → excluir con evidencia
        - Otherwise → `PENDING` → continuar recolectando ciclos
        El `k` se puede configurar por estrategia en `execution_params` para estrategias de distinta frecuencia.
    * **Criterios de aceptación**:
        - `confidence(0, k) = 0.0` para cualquier `k`
        - `confidence(k, k) = 0.5` exacto
        - `confidence(200, 20) ≈ 0.91`
        - Estrategia con PF=2.5 y 5 trades recibe status `PENDING`, no `QUALIFIED`
        - `k` se lee de `execution_params` con fallback a `sys_config`
        - Tests parametrizados verifican la función para n=0,5,10,20,30,50,100
    * **Artefactos**: `core_brain/scenario_backtester.py`, `core_brain/backtest_orchestrator.py`

* **HU 7.16: Filtro de compatibilidad de régimen pre-evaluación**
    * **Prioridad**: Media
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-716-REGIME-FILTER-2026-03-24
    * **Dependencia**: HU 7.8, HU 7.10
    * **Descripción**: Antes de fetchear datos para un par, verificar si el régimen actual de ese par (via `RegimeClassifier` en tiempo real) es compatible con `strategy.required_regime`. Si `required_regime = 'ANY'` → siempre evaluar. Si no coincide → estado `REGIME_INCOMPATIBLE` para este ciclo, programar para el próximo. No es un rechazo permanente del par — es aplazar la evaluación hasta que exista el contexto correcto. El sistema prioriza estos pares aplazados cuando el régimen compatibiliza (ver HU 7.18).
    * **Criterios de aceptación**:
        - Estrategia con `required_regime='TREND'` no fetchea datos de un par en RANGE
        - El par en RANGE queda marcado `REGIME_INCOMPATIBLE` con timestamp
        - El scheduler (HU 7.18) eleva prioridad del par cuando el régimen cambia a TREND
        - Estrategias con `required_regime='ANY'` no aplican el filtro
    * **Artefactos**: `core_brain/backtest_orchestrator.py`

* **HU 7.17: Tabla sys_strategy_pair_coverage**
    * **Prioridad**: Media
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-717-COVERAGE-TABLE-2026-03-24
    * **Descripción**: Nueva tabla DDL en `schema.py`:
        ```sql
        CREATE TABLE IF NOT EXISTS sys_strategy_pair_coverage (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id     TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            timeframe       TEXT NOT NULL,
            regime          TEXT NOT NULL,
            n_cycles        INTEGER DEFAULT 0,
            n_trades_total  INTEGER DEFAULT 0,
            effective_score REAL    DEFAULT 0.0,
            status          TEXT    DEFAULT 'PENDING',
            last_evaluated_at TIMESTAMP,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, symbol, timeframe, regime)
        );
        ```
        Esta tabla es la fuente de verdad para el scheduler inteligente (HU 7.18) y el fetch incremental (HU 7.12). Registra el estado de cobertura de cada combinación `(estrategia, par, timeframe, régimen)`.
    * **Criterios de aceptación**:
        - Migration idempotente crea la tabla sin afectar datos existentes
        - `UNIQUE(strategy_id, symbol, timeframe, regime)` previene duplicados
        - `BacktestOrchestrator` escribe en esta tabla al completar cada evaluación de par
        - Tests de migration verifican idempotencia
    * **Artefactos**: `data_vault/schema.py`

* **HU 7.18: Scheduler inteligente de backtests — prioritized queue**
    * **Prioridad**: Media
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-718-SMART-SCHEDULER-2026-03-24
    * **Dependencia**: HU 7.17, HU 10.7
    * **Descripción**: Componente `BacktestPriorityQueue` que determina qué combinación `(strategy_id, symbol, timeframe)` evaluar en cada slot disponible. Prioridad descendente:
        - P1: `last_backtest_at = NULL` (nunca evaluada)
        - P2: `status = PENDING` + régimen actualmente compatible
        - P3: `untested_clusters` pendientes
        - P4: Varianza alta entre ciclos (`effective_score` inestable)
        - P5: `confidence` baja + muchos ciclos sin mejora
        - P6: Re-evaluación rutinaria (detección de drift temporal)
        Integrado con `OperationalModeManager` (HU 10.7): si el modo cambia a `SHADOW_ACTIVE` o `LIVE_ACTIVE` durante la ejecución del queue, el scheduler reduce la agresividad inmediatamente.
    * **Criterios de aceptación**:
        - Combinaciones P1 se evalúan antes que P6 en todos los escenarios
        - Cambio de contexto a `LIVE_ACTIVE` reduce el budget del scheduler en el siguiente ciclo
        - Tests verifican ordenamiento correcto del queue con datos sintéticos de cobertura
    * **Artefactos**: `core_brain/backtest_orchestrator.py`

* **HU 7.19: Detector de overfitting por par**
    * **Prioridad**: Baja
    * **Épica**: E10 | **Dominio**: 07_ADAPTIVE_LEARNING
    * **Trace_ID**: EDGE-BKT-719-OVERFITTING-DETECTOR-2026-03-24
    * **Dependencia**: HU 7.14, HU 7.15
    * **Descripción**: Si una estrategia alcanza `effective_score >= 0.90` en más del 80% de los pares evaluados con `confidence >= 0.70`, es estadísticamente sospechoso — sugiere que la simulación está sobreajustada a los datos históricos disponibles. En ese caso, el sistema:
        1. Flag `overfitting_risk: true` en el `AptitudeMatrix`
        2. Requiere validación adicional: un periodo out-of-sample no incluido en los ciclos de evaluación anteriores
        3. No bloquea la promoción automáticamente, pero emite alerta en `sys_audit_logs` y en el broadcast WebSocket a la UI
    * **Criterios de aceptación**:
        - Flag se activa correctamente con >80% pares en score >= 0.90
        - Flag NO se activa si solo 3 de 18 pares tienen score >= 0.90
        - Alert registrado en `sys_audit_logs` con `trace_id`
        - Tests verifican el umbral de activación
    * **Artefactos**: `core_brain/scenario_backtester.py`, `core_brain/backtest_orchestrator.py`

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)
* **HU 8.1: usr_broker_accounts — Separación Arquitectónica de Cuentas** `[DONE]`
    * **Descripción**: Implementar tabla `usr_broker_accounts` en `schema.py` y `usr_template.db` para separar cuentas de usuario de cuentas del sistema. `sys_broker_accounts` queda exclusivamente para cuentas DEMO del sistema (data feeds, SHADOW mode sin usuario). `usr_broker_accounts` almacena cuentas REAL/DEMO por trader, aisladas por `user_id`. Crear `BrokerAccountsMixin` con métodos CRUD y script de migración idempotente.
    * **Referencia arquitectónica**: `docs/01_IDENTITY_SECURITY.md` Sección "Broker Account Management". Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.3: Proceso Singleton — PID Lockfile en start.py** `[DONE]`
    * **Prioridad**: Alta
    * **Descripción**: `start.py` no previene múltiples instancias. Se detectaron 2×start.py + 2×uvicorn corriendo simultáneamente (PIDs 31680, 32856). Fix: crear lockfile `data_vault/aethelgard.lock` con el PID del proceso al arrancar; verificar si el archivo existe y si el PID registrado está vivo (via `/proc/{pid}/status` o `psutil`); si está vivo, abortar con mensaje claro; si está muerto (stale), sobreescribir.
    * **Trace_ID**: PIPELINE-UNBLOCK-SINGLETON-2026-03-24

* **HU 10.4: Capital Dinámico desde sys_config (account_balance)** `[DONE]`
    * **Prioridad**: Alta
    * **Descripción**: `start.py` tiene `initial_capital=10000.0` hardcodeado. La DB tiene `account_balance: 8386.09` en `sys_config`. Fix: leer `account_balance` de `sys_config` antes de instanciar componentes; fallback a 10000.0 con WARNING si no existe.
    * **Trace_ID**: PIPELINE-UNBLOCK-CAPITAL-DB-2026-03-24

* **HU 10.5: EdgeMonitor Connector-Agnóstico** `[DONE]`
    * **Prioridad**: Media
    * **Descripción**: `EdgeMonitor.__init__` acepta `mt5_connector: Optional[Any]` hardcodeado. Refactor a `connectors: Dict[str, Any]` (mismo patrón que `OrderExecutor`). El monitor debe iterar todos los conectores disponibles sin conocer su tipo. La disponibilidad de un conector se detecta desde DB (`sys_data_providers.enabled`), no via flags hardcodeados. Métodos `_check_mt5_external_operations()` se refactorizan a `_check_connector_external_operations(connector_id, connector)` genérico.
    * **Trace_ID**: PIPELINE-UNBLOCK-EDGE-AGNOSTIC-2026-03-24

* **HU 10.7: Adaptive Operational Mode Manager** `[DONE]`
    * **Prioridad**: 🔴 CRÍTICA (prerequisito para HU 7.12 y HU 7.18)
    * **Épica**: E10 | **Dominio**: 10_INFRASTRUCTURE_RESILIENCY
    * **Trace_ID**: EDGE-BKT-107-OPERATIONAL-MODE-MANAGER-2026-03-24
    * **Contexto**: El sistema ejecuta el Scanner, SignalFactory y ClosingMonitor con frecuencia máxima incluso cuando no hay estrategias en SHADOW ni LIVE — producen output que nadie consume. Ese cómputo podría redirigirse al backtesting. Adicionalmente, el `BacktestOrchestrator` usa cooldown fijo de 24h independientemente de los recursos disponibles, desperdiciando capacidad en contextos `BACKTEST_ONLY`.
    * **Descripción**: Implementar `OperationalModeManager` que:
        1. **Detecta el contexto operacional** cada ciclo:
            - `BACKTEST_ONLY`: todas las estrategias en BACKTEST (sin SHADOW ni LIVE)
            - `SHADOW_ACTIVE`: al menos 1 estrategia en SHADOW
            - `LIVE_ACTIVE`: al menos 1 estrategia en LIVE
        2. **Ajusta la frecuencia o suspende componentes** según contexto:

            | Componente | BACKTEST_ONLY | SHADOW_ACTIVE | LIVE_ACTIVE |
            |---|---|---|---|
            | Scanner | Frecuencia mínima (1/5min) | Normal | Normal |
            | SignalFactory | **Suspendido** | Normal | Normal |
            | ClosingMonitor | **Suspendido** | Normal | Normal |
            | EdgeMonitor | Frecuencia reducida | Normal | Normal |
            | OperationalEdgeMonitor | Frecuencia reducida | Normal | Normal |
            | BacktestOrchestrator | **Agresivo** (cooldown dinámico) | Moderado | Conservador |
            | ConnectivityOrchestrator | Normal (siempre) | Normal | Normal |
            | AutonomousHealthService | Normal (siempre) | Normal | Normal |

        3. **Resume componentes en < 2s** ante cambio de contexto (ej: estrategia promovida a SHADOW → restaurar Scanner y SignalFactory antes de que la instancia SHADOW opere)
        4. **Evalúa recursos del servidor** (psutil) antes de autorizar cada backtest:
            - CPU, RAM, disco desde `psutil`
            - Thresholds configurables desde `sys_config`
            - Si recursos insuficientes → `DEFER` (no cancelar) con timestamp de reintento
        5. **Expone `get_backtest_budget()`** al `AdaptiveBacktestScheduler` (HU 7.12): retorna el nivel de agresividad autorizado (`AGGRESSIVE` / `MODERATE` / `CONSERVATIVE` / `DEFERRED`)
        6. **Persiste transiciones de modo** en `sys_audit_logs` para auditoría completa
        **Nota de diseño**: Esta HU es el primer componente real del `AutonomousSystemOrchestrator` (HU 10.6). Implementa los principios de autonomía declarados en ese diseño sobre un caso concreto y de alto valor inmediato.
    * **Criterios de aceptación**:
        - Transición de contexto detectada correctamente en < 1 ciclo tras cambio de modo de estrategia
        - SignalFactory suspendida en `BACKTEST_ONLY` y restaurada en < 2s al detectar `SHADOW_ACTIVE`
        - `get_backtest_budget()` retorna `DEFERRED` cuando CPU > 80% independientemente del contexto
        - Todas las transiciones de modo registradas en `sys_audit_logs`
        - Tests verifican detección de los 3 contextos operacionales
        - Tests verifican resume correcto al cambiar de `BACKTEST_ONLY` a `SHADOW_ACTIVE`
    * **Artefactos**: `core_brain/operational_mode_manager.py` (nuevo), `core_brain/main_orchestrator.py` (wiring), `data_vault/schema.py` (si requiere tabla adicional)

* **HU 10.6: AutonomousSystemOrchestrator — Diseño FASE4** `[TODO]`
    * **Prioridad**: Media (diseño y documentación, no implementación de código aún)
    * **Descripción**: Diseñar e documentar en `docs/` el `AutonomousSystemOrchestrator` que coordina los 13 componentes EDGE existentes (OperationalEdgeMonitor, EdgeTuner, DedupLearner, CoherenceMonitor, DrawdownMonitor, ExecutionFeedbackCollector, CircuitBreaker, PositionSizeMonitor, RegimeClassifier, ClosingMonitor, AutonomousHealthService, HealthManager, CoherenceService) como un sistema coherente de auto-diagnóstico y healing. Niveles de autonomía: OBSERVE | SUGGEST | HEAL. Sub-componentes: DiagnosticsEngine (correlación síntoma→causa), BaselineTracker (aprende "normal" por sesión), HealingPlaybook (acciones correctivas seguras), ObservabilityLedger (tabla `sys_agent_events`), EscalationRouter (notificación con diagnóstico completo).
    * **Trace_ID**: FASE4-AUTONOMOUS-ORCHESTRATOR-DESIGN-2026-03-24

* **HU 10.1: Autonomous Heartbeat & Self-Healing**
    * **Prioridad**: Media (E3)
    * **Descripción**: Sistema de monitoreo de signos vitales y auto-recuperación de servicios.
    * **🖥️ UI**: Widget de "Status Vital" con log de eventos técnicos.
