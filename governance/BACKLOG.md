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

## 00_INFRA_SANEAMIENTO (Sprint Arquitectónico — 14-Mar-2026)
*Origen: Auditoría forense `docs/AUDITORIA_ESTADO_REAL.md`. Prerequisito bloqueante para todo el Canvas de Ideación.*

### Nivel 0 — Fundacional (✅ COMPLETADO — Trace_ID: ARCH-SSOT-NIVEL0-2026-03-14)
* **N0-1: sys_signal_ranking como DDL oficial** `[DONE]`
    * Eliminar `usr_performance` de `initialize_schema()`. Crear `sys_signal_ranking` con todos los campos. Actualizar `run_migrations()`. Impacto: CRÍTICO-1.
* **N0-2: Consolidación de DDL fragmentado** `[DONE]`
    * Mover `session_tokens` (de `session_manager.py`), `sys_execution_feedback` (de `execution_feedback.py`) y `position_metadata` (de `trades_db.py`) a `schema.py`. Impacto: CRÍTICO-2.
* **N0-3: FK huérfana corregida** `[DONE]`
    * `usr_strategy_logs`: `REFERENCES usr_strategies` → `REFERENCES sys_strategies`. Impacto: ALTO-1.
* **N0-4: Naming convention restaurada** `[DONE]`
    * `notifications` → `usr_notifications` en `schema.py` y `system_db.py`. Impacto: ALTO-4.

### Nivel 1 — Crítico: Stack de Conectividad FOREX (📋 BACKLOG)

**Foco**: FOREX-first. cTrader como conector primario nativo async (WebSocket, sin DLL). MT5 estabilizado como alternativa. Otros mercados en Nivel 2.

* **N1-1: MT5 Single-Thread Executor** `[TODO]`
    * Crear `_MT5Task` dataclass + `_dll_executor_loop` + `_submit_to_executor` + `_submit_async` en `mt5_connector.py`. Elimina race condition entre `MT5-Background-Connector` thread (lines 223, 555), `_schedule_retry()` Timer thread y FastAPI caller thread. MT5 queda estable como alternativa. Archivos: `connectors/mt5_connector.py`. Impacto: CRÍTICO-3.
* **N1-2: cTrader Connector** `[TODO]`
    * Crear `connectors/ctrader_connector.py` (~200 líneas, hereda `BaseConnector`). WebSocket Spotware Open API para tick/OHLC streaming (M1 sin latencia, <100ms). REST para order execution. Reemplaza MT5 como conector primario FOREX. Requisito: cuenta IC Markets cTrader (free). Archivos: `connectors/ctrader_connector.py` (nuevo). Impacto: LIVE + M1 viable.
* **N1-3: Data Stack FOREX default** `[TODO]`
    * Reordenar prioridades en `DataProviderManager`: cTrader=100, MT5=70, TwelveData=disabled, Yahoo=disabled. Desactivar M1 en `config/config.json` (`enabled: false` por defecto). Stocks y futuros deshabilitados hasta Nivel 2. Archivos: `core_brain/data_provider_manager.py`, `config/config.json`. Impacto: CRÍTICO-3 datos.
* **N1-4: Warning latencia M1** `[TODO]`
    * En `ScannerEngine._scan_one()`: detectar si provider activo no es local (cTrader o MT5) Y timeframe = M1 → emitir WARNING en log + insertar entrada en `usr_notifications` con `category: DATA_RISK`, `message: "M1 con provider no-local: riesgo de señal en precio stale"`. Archivos: `core_brain/scanner.py`. Impacto: Riesgo operacional.
* **N1-5: StrategyGatekeeper Integration** `[TODO]`
    * Instanciar `StrategyGatekeeper` en `MainOrchestrator` vía DI. Conectar al flujo de señales pre-ejecución. `strategy_gatekeeper.py` ya existe (290 líneas, 17/17 tests passing) — solo falta el wiring. Archivos: `core_brain/main_orchestrator.py`. Impacto: ALTO-2.

**Orden de ejecución**: N1-1 → N1-2 → N1-3 → N1-4 → N1-5

### Nivel 2 — Inteligencia (📋 BACKLOG)
* **N2-1: JSON_SCHEMA Interpreter** `[TODO]`
    * Implementar rama `JSON_SCHEMA` en `StrategyEngineFactory`. Permite que el Bucle de Generación (Canvas Punto 4.3) cree estrategias sin código Python. Archivos: `core_brain/services/strategy_engine_factory.py`. Impacto: MEDIO-6.
* **N2-2: WebSocket Auth Standardization** `[TODO]`
    * Estandarizar `telemetry.py`, `shadow_ws.py`, `strategy_ws.py` para usar `Depends(get_current_active_user)` en lugar de `_verify_token()` manual. Impacto: ALTO-6.

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

* **HU 3.6: Signal Quality Scorer (Phase 4)** `[x] DONE`
    * **Descripción**: Motor unificado de puntuación. Grados: A+ (85+), A (75+), B (65+), C (50+), F (<50). Fórmula: (Técnico × 0.6) + (Contextual × 0.4).
    * **Estado**: Sprint 4 (11 Marzo 2026). 13/13 tests PASSED. Trace_ID: PHASE4-INTELLIGENCE-SCORER-2026

* **HU 3.7: Consensus Engine (Phase 4)** `[x] DONE`
    * **Descripción**: Detecta múltiples estrategias convergentes en mismo setup (5 min). STRONG consenso +20%, WEAK +10%.
    * **Estado**: Sprint 4 (11 Marzo 2026). 11/11 tests PASSED. Trace_ID: PHASE4-CONSENSUS-ENGINE-2026

* **HU 3.8: Failure Pattern Registry (Phase 4)** `[x] DONE`
    * **Descripción**: Aprendizaje autónomo de patrones de fallo cada 4h. Severity weights mapean failure_reason a penalizaciones. Penalidad máxima 30%.
    * **Estado**: Sprint 4 (11 Marzo 2026). 6/6 tests PASSED. Trace_ID: PHASE4-FAILURE-LEARNING-2026

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

* **HU 4.7: Economic Calendar Veto Filter (News-Based Trading Lockdown)** `[TODO]`
    * **Prioridad**: Alta (Vector V3 - Dominio Sensorial)
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
    * **Tareas Pendientes**:
      - [ ] Ejecutar migración DML: `030_economic_calendar.sql` (crear tabla en DB)
      - [ ] Implementar `get_trading_status()` en `EconomicIntegrationManager` (core_brain/economic_integration.py)
      - [ ] Agregar tests: `test_economic_veto_interface.py` (buffer timing, symbol mapping, latency, graceful degradation)
      - [ ] Integrar `EconomicIntegrationManager` en `MainOrchestrator.__init__()` (inyección de dependencias)
      - [ ] Agregar pre-trade check en `MainOrchestrator.run_single_cycle()` (llamar `get_trading_status()`)
      - [ ] Agregar position management logic para HIGH impact (Break-Even mover, cierre parcial notificación)
      - [ ] Validar con `validate_all.py` (sin regressions)
    * **🖥️ UI Representation**: Indicator de "Economic Risk Status" en el header mostrando próximo evento y restricción activa (🔴HIGH/🟡MEDIUM/🟢NORMAL). Notificaciones toast si evento inminente.
    * **Artefactos** (Post-Implementación):
      - `core_brain/economic_integration.py` (+method `get_trading_status()`, caching logic)
      - `tests/test_economic_veto_interface.py` (target: 20+ tests covering buffers, symbols, latency, degradation)
      - `core_brain/main_orchestrator.py` (línea ~_: agregar pre-trade check)
      - `core_brain/position_manager.py` (método `move_sl_to_breakeven()` si no existe)
      - `docs/INTERFACE_CONTRACTS.md` (Contract 2 - REFERENCE)
      - `docs/AETHELGARD_MANIFESTO.md` (Section VIII - REFERENCE)
    * **Trace_ID**: ECON-VETO-FILTER-2026-001
    * **Gobernanza**: Agnosis obligatoria (no imports de brokers), DI obligatorio, SSOT (DB única fuente), degradación graciosa, <100ms latencia, auditoría vía TRACE_ID.

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

* **HU 7.2: Asset Efficiency Score Gatekeeper** `[DONE]`
    * **Prioridad**: Alta (Vector V3 - Dominio Sensorial)
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

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.1: Autonomous Heartbeat & Self-Healing**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Sistema de monitoreo de signos vitales y auto-recuperación de servicios.
    * **🖥️ UI**: Widget de "Status Vital" con log de eventos técnicos.
