# AETHELGARD: ESTRATEGIC ROADMAP

"ESTÁNDAR DE EDICIÓN: El Roadmap se organiza en Vectores de Valor (V1, V2...). Cada hito debe estar vinculado a uno de los 10 dominios del BACKLOG."

**Versión Log**: v4.1.0-beta.3 (V3: Dominio Sensorial - EVOLUCIÓN)
**Última Actualización**: 1 de Marzo, 2026 (08:45)

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

> [!NOTE]
> El historial completo de V1, V2 y Auditoría ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

