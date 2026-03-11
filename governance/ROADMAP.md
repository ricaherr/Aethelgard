# AETHELGARD: ESTRATEGIC ROADMAP

"ESTÁNDAR DE EDICIÓN: El Roadmap se organiza en Vectores de Valor (V1, V2...). Cada hito debe estar vinculado a uno de los 10 dominios del BACKLOG."

**Versión Log**: v4.2.0-beta.1 (V3: Dominio Sensorial - QUANTUM LEAP COMPLETADO)
**Última Actualización**: 4 de Marzo, 2026 (12:45 UTC)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Vectores de Valor)

### 🚀 V1 (Vector de Cimientos SaaS) — [x] CERRADO (Dominios 01 y 08)
**Status**: COMPLETADO ✅
**Trace_ID**: SAAS-GENESIS-2026-001  
**Objetivo**: Evolucionar el sistema de un solo usuario a una arquitectura multi-tenant con autenticación JWT y aislamiento de datos por tenant.

---

### 🐛️ AUDITORÍA & ESTANDARIZACIÓN — [x] COMPLETADA
**Objetivo**: Sincronización de la realidad técnica documentada.
**Estado Final**: ✅ COMPLETADO  
**Trace_ID**: DOC-SYNC-2026-003  
**Descripción**: Rectificación de BACKLOG, SPRINT y ROADMAP para reflejar estado real del v4.1.0-beta.3 con HUs 3.2, 3.4, 2.2, 4.4, 4.5 migradas a [DONE]. Sprint 2 cerrado, Sprint 3 activado. Vector V3 productivo.

---

### 🧰 V2 (Vector de Inteligencia & Supremacía de Ejecución) — [x] COMPLETADO (Dominio 04)
**Status**: ✅ ARCHIVADO
**Objetivo**: Establecer el control de riesgo avanzado y la optimización de Alpha.  
**Hitos Completados**:
- [x] **Multi-Scale Regime Vectorizer**: Base Vector V2 completada.
- [x] **Contextual Alpha Scoring**: Dashboard Alpha Radar operativo.
- [x] **Dynamic Alpha Thresholding**: Mecanismo de defensa proactiva integrado.
- [x] **Confidence Threshold Optimization**: Ajuste dinámico por desempeño.
- [x] **Safety Governor & Drawdown Monitor**: Gobernanza de riesgo operativa (Sprint 2).

> Historial completo migrado a SYSTEM_LEDGER.md (Registro: 2026-02-27)

---

### 👁️ V3 (Vector de Dominio Sensorial) — ACTIVO (Dominios 02, 03, 04, 06, 07, 10)
**Status**: 🚀 EN EJECUCIÓN  
**Trace_ID**: VECTOR-V3-SANITY-2026-001  
**Objetivo**: Establecer la supremacía analítica mediante detección de anomalías, meta-coherencia de modelos y auto-calibración adaptativa.
**Sprint Actual**: SPRINT 3 (Inicio: 1 de Marzo, 2026)

**Hitos en Desarrollo**:
- [x] **Multi-Scale Regime Vectorizer (HU 2.1)** — ✅ COMPLETADA
  - Unificación de temporalidades M15, H1, H4.
  - Motor RegimeService con Regla de Veto Fractal.
  - Widget "Fractal Context Manager" en UI.
  - Sincronización de Ledger (SSOT).
  - 15/15 Tests PASSED.

- [x] **Anomaly Sentinel (HU 4.6)** — ✅ COMPLETADA (1 de Marzo, 2026)
  - Detector de volatilidad extrema (Z-Score > 3.0) con rolling window
  - Detector de Flash Crashes (caída > -2% en 1 vela)
  - Protocolo Defensivo: Lockdown Preventivo + Cancel Orders + SL->Breakeven
  - Persistencia en DB (table anomaly_events) con Trace_ID
  - Broadcast de [ANOMALY_DETECTED] a UI vía WebSocket
  - Thought Console con sugerencias inteligentes
  - Integración con Health System (HU 10.1)
  - 21/21 Tests PASSED | validate_all.py: 100% OK
  - Trace_ID: BLACK-SWAN-SENTINEL-2026-001

- [x] **Global Liquidity Clock (HU 2.2)** — ✅ COMPLETADO (2 de Marzo, 2026)
  - **MarketSessionService**: Motor de sesiones globales (Sydney, Tokyo, London, NY)
  - Métodos: `is_session_active()`, `get_pre_market_range()`, `get_session_liquidity_metrics()`
  - Pre-market range detection: 30 minutos antes de apertura NY (18:00-18:30 UTC)
  - Cálculos UTC correctos con soporte para timezones múltiples
  - Persistencia en DB (SSOT) con Trace_ID: SESSION-XXXXXXXX
  - Integración: RiskManager consulta liquidez por sesión
  - 22/22 Tests PASSED | validate_all.py: 100% OK
  - Documentación: Payload de pre-market range incluido en BRK_OPEN_0001.json
  - Trace_ID: EXEC-STRAT-OPEN-001

- [x] **Detector de Ineficiencias (HU 3.3)** — ✅ COMPLETADO (2 de Marzo, 2026)
  - **ImbalanceDetector**: Detección asíncrona de FVGs en M5/M15
  - Métodos: `detect_fvg()`, `validate_institutional_footprint()`, `detect_imbalances_async()`, `generate_signal()`
  - Validación de volumen para confirmar huella institucional
  - Señales incluyen UUID v4 como Instance ID (SSOT Mnemonic)
  - Persistencia en DB con trace_id para auditoría
  - Integración: Signal Factory inyecta strategy_class_id + instance_id
  - 18/18 Tests PASSED | validate_all.py: 100% OK
  - Documentación: Signal payload structure en BRK_OPEN_0001.json
  - Trace_ID: EXEC-STRAT-OPEN-001

- [x] **Configuración de Estrategia S-0001 (HU 3.4)** — ✅ COMPLETADA (2 de Marzo, 2026)
  - **BRK_OPEN_0001.json**: Schema de estrategia "NY Strike" completo
  - Entry: 50% penetración del FVG, basado en ImbalanceDetector
  - Exit: Unidades R dinámicas (R2.0 TP, R1.0 SL)
  - Mnemonic: BRK_OPEN_NY_STRIKE
  - UUID v4 Instance ID generation mandatory (per trade)
  - Integración completa: MarketSessionService + ImbalanceDetector + LiquidityService + RegimeService
  - Persistencia: strategies table con clase_id = BRK_OPEN_0001
  - Trace_ID: EXEC-STRAT-OPEN-001

- [ ] **The Pulse (Advanced Feedback)**: Lazo de retroalimentación de infraestructura avanzado (HU 5.3 final).
- [x] **Coherence Drift Monitoring (HU 6.3)** — ✅ COMPLETADA (2 de Marzo, 2026)
  - Detector de divergencia Shadow vs Live execution (slippage + latencia)
  - CoherenceService: Cálculo de coherencia 0-100% con veto automático
  - Tests: 14/14 PASSED | Configuración desde BD (SSOT)
  - Documentación: 06_STRATEGY_COHERENCE.md completada
  - Integración: RiskManager respeta veto; ExecutionService loguea shadow
  - Trace_ID: COHERENCE-DRIFT-2026-001
- [x] **The Double Engine: Universal Strategy Runtime (HU 3.6 & HU 3.9)** — ✅ COMPLETADA (2 de Marzo, 2026)
  - **HU 3.6: UniversalStrategyEngine** (Trace_ID: STRATEGY-GENESIS-2026-001)
    - ✅ Intérprete de estrategias basado en Schema JSON (MODE_UNIVERSAL)
    - ✅ Mapeo dinámico de indicadores (RSI, MA, FVG, etc.) vía IndicatorFunctionMapper
    - ✅ Aislamiento total: fallos de lógica → STRATEGY_CRASH_VETO sin afectar sistema
    - ✅ Memory-resident, 320 líneas (< 450 líneas)
    - ✅ Validación de schema con StrategySchemaValidator
    - ✅ Evaluación segura de condiciones con namespace aislado (safe eval)
  - **HU 3.9: Hybrid Runtime Switch** (Trace_ID: STRATEGY-GENESIS-2026-001)
    - ✅ StrategyModeSelector: alternar MODE_LEGACY vs MODE_UNIVERSAL
    - ✅ Configuración por tenant en DB (SSOT: system_state) con strategy_runtime_mode
    - ✅ Hot-swap capabil: switch_mode() con graceful shutdown y auditoría
    - ✅ Forbid ambiguity: initialize() rechaza configs incompletas
    - ✅ Ledger auditing: cada cambio de modo registrado en SYSTEM_LEDGER con timestamp
  - **Componentes Integrados:**
    - ✅ LegacyStrategyExecutor: wrapper para Python-based strategies (oliver_velez, etc.)
    - ✅ UniversalStrategyExecutor: delegador de JSON schemas con discovery automático
    - ✅ StrategyModeAdapter: mantiene compatibilidad MainOrchestrator (generate_signals_batch)
    - ✅ StorageManager: métodos get_tenant_config(), update_tenant_config(), append_to_system_ledger()
  - **Migración Espejo:**
    - ✅ institutional_footprint.json: esquema universal completo con indicators, logic, risk management
    - ✅ core_brain/strategies/universal/: directorio para JSON schemas
  - **Validación:**
    - ✅ validate_all.py: 14/14 módulos PASSED (Architecture, QA Guard, Core Tests)
    - ✅ Line count: UniversalStrategyEngine = 320 líneas (< 450)
    - ✅ Dependency Injection: verificado en StrategyModeSelector constructor
    - ✅ SSOT database: tenant config y ledger en system_state (SQLite)
    - ✅ MainOrchestrator integración: dual-motor activo en startup

- [x] **QUANTUM LEAP: Universal Strategy Engine Refactored (SALTO CUÁNTICO)** — ✅ COMPLETADA (4 de Marzo, 2026)
  - **Trace_ID**: DOC-STRATEGY-REANALYZE | EXEC-UNIVERSAL-ENGINE-REAL
  - **Misión**: Forzar el Salto Cuántico para eliminar hardcodeo de OliverVelezStrategy y hacer el engine verdaderamente agnóstico
  - **Cambios Arquitectónicos Críticos**:
    - ✅ **PASO 1: Saneamiento del Registry**
      - ✅ Actualización SYSTEM_LEDGER.md: Detección de Inconsistencia Crítica (OliverVelezStrategy hardcodeado vs no existe en Registry)
      - ✅ Clasificación de estrategias con campo `readiness`:
        - **READY_FOR_ENGINE** (3): MOM_BIAS_0001, LIQ_SWEEP_0001, STRUC_SHIFT_0001
        - **LOGIC_PENDING** (3): BRK_OPEN_0001, institutional_footprint, SESS_EXT_0001
      - ✅ Documentación: SYSTEM_LEDGER.md + governance/ROADMAP.md sincronizados
    - ✅ **PASO 2: Refactor del Engine Real**
      - ✅ **RegistryLoader**: Lee dinámicamente config/strategy_registry.json (zero hardcoding)
      - ✅ **StrategyReadinessValidator**: Valida `readiness` (READY_FOR_ENGINE vs LOGIC_PENDING)
      - ✅ **execute_from_registry()**: Nuevo método agnóstico
        - Paso 1: Cargar metadata del Registry
        - Paso 2: Validar readiness (bloquea LOGIC_PENDING)
        - Paso 3: Cargar schema
        - Paso 4: Ejecutar lógica
      - ✅ Mantiene compatibilidad hacia atrás con `execute(schema, ...)`
      - ✅ Nuevo ExecutionMode: READINESS_BLOCKED, NOT_FOUND
    - ✅ **PASO 3: Eliminación de Hardcode**
      - ✅ Removido: `from core_brain.strategies.oliver_velez import OliverVelezStrategy`
      - ✅ Removido: `ov_strategy = OliverVelezStrategy(...)` instantiation
      - ✅ Actualizado SignalFactory: `strategies=[]` (carga dinámica vía Registry)
      - ✅ Principio Zero Assumptions: Si no está en Registry → no existe
    - ✅ **PASO 4: Test de Validación**
      - ✅ 15/15 tests PASSED (test_universal_strategy_engine_quantum.py)
      - ✅ **TestRegistryLoader** (4 tests):
        - Carga estrategias del JSON
        - Cachea el Registry
        - Obtiene metadata
        - Retorna None para desconocidas
      - ✅ **TestStrategyReadinessValidator** (3 tests):
        - Valida READY_FOR_ENGINE
        - Bloquea LOGIC_PENDING
        - Maneja estados desconocidos
      - ✅ **TestUniversalStrategyEngineQuantum** (6 tests):
        - Inicialización correcta
        - Encuentra estrategia en Registry
        - BLOQUEA estrategias LOGIC_PENDING
        - Retorna NOT_FOUND para inexistentes
        - get_ready_strategies() retorna solo READY (3 estrategias)
        - RegistryLoader accesible desde engine
      - ✅ **TestNoOliverVelezHardcoding** (2 tests):
        - NO hay imports de OliverVelezStrategy en engine
        - Registry es Single Source of Truth
  - **Impacto Arquitectónico**:
    - ✅ Motor verdaderamente agnóstico: Lectura dinámica, sin imports hardcodeados
    - ✅ Escalabilidad garantizada: Nuevas estrategias = agregar al Registry (no modificar código)
    - ✅ Zero Assumptions: Motor no asume estrategias, las descubre
    - ✅ SSOT: Registry JSON es la única fuente de verdad
    - ✅ Seguridad: Bloquea estrategias en desarrollo (LOGIC_PENDING)
  - **Archivos Modificados**:
    - ✅ core_brain/universal_strategy_engine.py (650+ líneas refactorizadas)
    - ✅ config/strategy_registry.json (readiness + readiness_notes agregados a 6 estrategias)
    - ✅ start.py (imports de OliverVelez removidos, strategies=[] en SignalFactory)
    - ✅ docs/SYSTEM_LEDGER.md (DOC-STRATEGY-REANALYZE registrado)
  - **Tests Validación**: 15/15 PASSED ✅ | validate_all.py: 100% OK
  - **Status**: ✅ PRODUCTION-READY | Base para futuras integraciones agnósticas
  - **Siguiente Paso**: Implementar schemas JSON para estrategias READY_FOR_ENGINE

- [x] **Firma Operativa: Market Open Gap (Forex Edition) — ✅ COMPLETADA (2 de Marzo, 2026)**
  - **Mercado**: EUR/USD (Forex)
  - **Ventana de Operación**: 08:00 AM - 10:00 AM EST (Apertura NY)
  - **Protocolo Quanter**: Los 4 Pilares (Sensorial, Régimen, Coherencia, Multi-tenant) documentados en AETHELGARD_MANIFESTO.md Sección V
  - **Lógica de Entrada**:
    - ✅ Identificación del rango de 60 minutos pre-apertura
    - ✅ Detección de Gap de Ineficiencia (ruptura violenta)
    - ✅ Entrada en retroceso al 50% del FVG (Consecutive Encroachment)
    - ✅ Filtro de Régimen: Expansión o Tendencia en H1 (Context Intelligence HU 2.1)
  - **Gestión de Riesgo**:
    - ✅ Stop Loss: Encima/debajo de vela generadora del Gap
    - ✅ Take Profit: Niveles de liquidez institucional (Order Block previo)
    - ✅ Risk per Trade: 1% del capital (ajustado a 0.5% en volatilidad)
  - **Componentes Validados**:
    - ✅ Fair Value Gap (FVG) Detection: LiquidityService
    - ✅ Regime Filter: RegimeService Multi-Scale
    - ✅ Coherence Monitoring: CoherenceService (Shadow vs Live)
    - ✅ Schema JSON pesquisito en docs/03_ALPHA_ENGINE.md (Firmas Operativas Validadas)
  - **Trace_ID**: STRATEGY-MARKET-OPEN-GAP-2026-001

- [x] **Filtrado de Eficiencia por Score de Activo (EXEC-EFFICIENCY-SCORE-001)** — ✅ COMPLETADA (2 de Marzo, 2026 — 19:30 UTC)
  - **Objetivo**: Capa de filtrado que valida la eficiencia de cada activo antes de ejecución de estrategia.
  - **Acción 1: Esquema de Datos Evolucionado** ✅
    - ✅ Tabla `strategies` con campos `class_id`, `mnemonic`, `version`, `affinity_scores` (JSON), `market_whitelist`
    - ✅ Tabla `strategy_performance_logs` para logging relacional de desempeño por activo (FOREIGN KEY → strategies)
    - ✅ Métodos de persistencia en `strategies_db.py`: StrategiesMixin con CRUD completo (460 líneas)
    - ✅ Métodos de cálculo: `calculate_asset_affinity_score()`, `get_performance_summary()`
    - ✅ Agregación dinámica: promedios ponderados de win_rate, profit_factor, momentum
  - **Acción 2: In-Memory Score Guard** ✅
    - ✅ Componente `StrategyGatekeeper` residente en memoria (core_brain/strategy_gatekeeper.py, 290 líneas)
    - ✅ Validación pre-tick: `can_execute_on_tick(asset, min_threshold, strategy_id)` → **< 1ms garantizado** ⚡
    - ✅ Abort execution en caso de score < threshold (veto instantáneo, no procesa el tick)
    - ✅ Market whitelist enforcement: lista de activos permitidos por estrategia
    - ✅ Logging de performance: `log_asset_performance()` → strategy_performance_logs DB
    - ✅ Refresh en memoria: `refresh_affinity_scores()` para pickear cambios de DB
  - **Integración Completa**:
    - ✅ StorageManager: StrategiesMixin inyectado en herencia múltiple
    - ✅ StrategyGatekeeper: Dependency Injection en MainOrchestrator
    - ✅ SSOT: Affinity scores origen único = strategy_performance_logs + strategies DB (cero hardcoding)
    - ✅ Learning system: Cada trade perfiles actualiza scores para siguiente sesión
  - **Documentación Técnica Completa** ✅
    - ✅ AETHELGARD_MANIFESTO.md (Sección VI - ~550 líneas, único documento oficial)
    - ✅ BACKLOG.md (HU 7.2 agregado bajo Dominio 07_ADAPTIVE_LEARNING)
    - ✅ SPRINT.md (Tarea marcada ✅ en SPRINT 3)
    - ✅ SYSTEM_LEDGER.md (Entrada cronológica con detalles, flujo operacional, gobernanza)
  - **Tests**: 17/17 PASSED ✅
    - ✅ Initialization, Asset Validation, Pre-Tick Filtering
    - ✅ Performance Logging, Score Updates, Market Whitelist
    - ✅ Integration con UniversalEngine
    - ✅ Latencia < 1ms en 1000 iteraciones
  - **Validación Completa**: validate_all.py 14/14 PASSED ✅ | start.py OK ✅
  - **Regla de Gobernanza**: Affinity scores NO hardcodeados (SSOT DB exclusive), inyección de dependencias, immutabilidad de thresholds
  - **Trace_ID**: EXEC-EFFICIENCY-SCORE-001 | **Status**: Production-Ready (auditable, multi-tenant, learning continuo)

- [ ] **Confidence Threshold Adaptive (HU 7.1)** — EN DESARROLLO
  - Optimizer que ajusta el umbral de confianza dinámicamente según desempeño histórico.
  - Detección de rachas de pérdidas → incrementa exigencia automáticamente.
  - Equity Curve Feedback Loop integrado.
  - Safety Governor con límites de suavizado (Max 5% delta por ciclo de aprendizaje).
  - Trace_ID: ADAPTIVE-THRESHOLD-2026-001
- [ ] **Autonomous Heartbeat & Self-Healing**: Monitoreo vital continuo y auto-recuperación (HU 10.1).

---

### 🌐 V4 (Vector de Expansión Institucional) — PLANIFICADO
**Objetivo**: Conexión directa con Prime Brokers vía FIX API para ejecución de ultra baja latencia.
**Dominios**: 05 (Ejecución Universal)

**Hitos Planificados**:
- [ ] **Capa Institutional (FIX API)**: Transporte QuickFIX para Prime Brokers.
- [ ] **Adaptive Slippage Controller**: Monitor de desviación y mitigación dinámica (HU 5.2).

---

### 🌐 V5 (Vector de Interfaz Fractal & Experiencia Futurista) — PLANIFICADO
**Objetivo**: Evolucionar la terminal a una consola de alta densidad de información con navegación fractal y elementos de manipulación directa.
**Trace_ID**: UI-V3-FRACTAL-FUTURE-2026
**Dominios**: 09 (Interfaz Institucional)

**Hitos Planificados**:
- [ ] **Unified Telemetry Stream (The Synapse)**: Endpoint unificado que centralice Scanner, Strategy, Signal y Position Managers en un solo flujo.
- [ ] **Fractal Zoom Engine**: Navegación por capas (Global → Motor → Atómico) sin recarga de página.
- [ ] **Direct Manipulation (Drag & Drop)**: 
    - Arrastrar señales a "Watchlists" o "Live Execution".
    - Reordenamiento dinámico de widgets de monitoreo.
- [ ] **Sci-Fi Component Library**: Implementación de HUDs (Heads-Up Display) para salud de satélites y scoring de señales.
- [ ] **Event Soldering**: Conexión de `ANOMALY_DETECTED` y `REASONING_EVENT` al frontend.

> [!NOTE]
> El historial completo de V1, V2 y Auditoría ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

