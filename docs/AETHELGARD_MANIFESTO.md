# AETHELGARD MANIFESTO v2.1
## El Salto Cuántico: Archivo de Verdad para Arquitectura Basada en 4 Pilares de Validación

**Status**: 🚀 ACTIVO | **Version**: 2.1 | **TRACE_ID**: MANIFESTO-v2-SPRINT5 | **Fecha**: 2026-03-05

---

## I. Visión Transformada: De Estrategias Heredadas a Motor Universal Agnóstico

**Aethelgard v2.0** marca un cambio paradigmático: **abandona BaseStrategy inheritance** y **adopta un Motor Universal agnóstico** que interpreta **Firmas Operativas** como esquemas JSON, validados por un sistema de **4 Pilares de Validación**.

### El Cambio Fundamental

| Aspecto | v1.0 (OBSOLETO) | v2.0 (CUÁNTICO) |
|--------|----------------|-----------------| 
| **Modelo de Estrategia** | Clases Python heredadas (BaseStrategy) | Esquemas JSON + Interpretación dinámica |
| **Orquestación** | Manual + Hardcodeada | Dinámica vía StrategyRegistry |
| **Validación de Señales** | Rudimentaria (solo risk check) | 4 Pilares: Sensorial, Régimen, Multi-tenant, Coherencia |
| **Extensibilidad** | Requiere cambios código + redeploy | Agregar entrada en registry.json ✅ |
| **Agnosis** | Parcial (broker-aware) | Total (broker-agnostic core) |

### Principios Constitucionales v2.0

1. **Agnosis Absoluta**: El CoreBrain es ciego a broker/plataforma. Usa conectores modulares. Lógica inmutable.
2. **Interpretación Universal**: UniversalStrategyEngine traduce cualquier firma JSON a señal operativa.
3. **Validación Multinivel**: 4 Pilares validan cada señal (sensorial ✓ régimen ✓ multi-tenant ✓ coherencia ✓).
4. **Escalabilidad Radical**: Nueva estrategia = 1 entrada registry.json. Sin redeploy.
5. **Multi-tenant Nativo**: Aislamiento total de datos/ejecución por cliente.
6. **Trazabilidad Institucional**: TRACE_ID único por operación, cadena de custodia auditada.

---

## II. Componentes Centrales (Arquitectura v2.0)

### 2.1 UniversalStrategyEngine (core_brain/universal_strategy_engine.py)

**Responsabilidad**: Interpreta esquemas JSON de estrategias → Genera señales operativas.

**Entrada**:
```json
{
  "name": "BRK_OPEN_0001",
  "market": "Forex",
  "timeframe_primary": "H1",
  "inputs": {
    "lookback_minutes": 60,
    "fvg_sensitivity": 0.5
  },
  "regime_filter": ["TREND_UP", "EXPANSION"],
  "entry_logic": "AND(price_in_fvg, coherence >= 0.75)",
  "exit_logic": {
    "take_profit": "R2",
    "stop_loss": "0.5R",
    "trailing": "1.5R_partial"
  },
  "membership_required": "Premium"
}
```

**Salida**: OutputSignal
```python
{
  "symbol": "EUR/USD",
  "signal_type": "BUY",
  "entry_price": 1.0925,
  "stop_loss": 1.0910,
  "take_profit_1": 1.0945,
  "take_profit_2": 1.0970,
  "confidence": 0.92,
  "strategy": "BRK_OPEN_0001",
  "instance_id": "uuid-...",
  "trace_id": "SIGNAL-BRK_OPEN-2026-03-03T09:15:32Z",
  "metadata": { ... }
}
```

**Método Clave**:
```python
async def analyze(
    self,
    symbol: str,
    market_data: Dict,
    regime: RegimeType,
    user_tier: MembershipLevel
) -> Optional[OutputSignal]:
    """Interpreta schema → genera señal validando 4 pilares."""
```

---

### 2.2 StrategySignalValidator - Los 4 Pilares (core_brain/strategy_validator_quanter.py)

**Responsabilidad**: Valida cada señal de UniversalStrategyEngine contra 4 criterios constitucionales.

#### Pilar 1️⃣: SENSORIAL (Compatibilidad de Inputs)
- **Pregunta**: ¿Están disponibles TODOS los sensores requeridos?
- **Validación**: Verifica que cada indicador (RSI, MA, ATR, FVG, Imbalance) tenga datos frescos (no NULL, not stale).
- **Veto**: Si falta sensor → STRATEGY_INCOMPATIBLE_VETO
- **Implementación**: SensorialPillar.validate()

#### Pilar 2️⃣: RÉGIMEN (Contexto de Mercado)
- **Pregunta**: ¿Permite el régimen actual esta estrategia?
- **Validación**: Compara regime_actual con regime_filter de estrategia. Multi-escala (M15, H1, H4).
- **Veto**: Si incompatible → REGIME_VETO
- **Implementación**: RegimePillar.validate()

#### Pilar 3️⃣: MULTI-TENANT (Membresía)
- **Pregunta**: ¿Tiene el usuario nivel de membresía suficiente?
- **Validación**: Compara user_tier (Basic/Premium/Institutional) con membership_required.
- **Veto**: Si insuficiente → MEMBERSHIP_VETO
- **Implementación**: MultiTenantPillar.validate()

#### Pilar 4️⃣: COHERENCIA (Health Check)
- **Pregunta**: ¿Es coherente la señal? (Min 2 elementos confluencia, confidence >= 0.60, sin conflictos).
- **Validación**: Verifica coherence_score shadow vs live, número de confirmadores.
- **Veto**: Si score < threshold → COHERENCE_VETO
- **Implementación**: CoherencePillar.validate()

**Resultado de Validación**:
```python
class ValidationReport:
    overall_status: ValidStatus  # PASSED | FAILED | BLOCKED
    overall_confidence: float     # 0.0-1.0
    pillars: Dict[str, PillarValidationResult]
    trace_id: str
    timestamp: str
    
    def is_approved(self) -> bool:
        """Retorna TRUE solo si ALL pillars = PASSED y confidence >= 0.70"""
```

**Orquestación**:
```python
validator = StrategySignalValidator(
    storage=storage,
    regime_classifier=regime,
    conflict_resolver=resolver
)

report = await validator.validate(
    strategy_id="BRK_OPEN_0001",
    symbol="EUR/USD",
    signal_data={...},
    user_tier="Premium"
)

if report.is_approved():
    execute_signal()
else:
    log_rejection(report.pillars)
```

---

### 2.3 StrategyRegistry - SSOT Dinámica Implementation (COMPLETADA 4-Mar-2026)

**Status**: ✅ **IMPLEMENTADO** - Fase v2.0 Dynamic Loading completa (TRACE_ID: FACTORY-STRATEGY-ENGINES-COMPLETE-2026)

**Responsabilidad**: Single Source of Truth de todas las firmas operativas. Permite carga dinámica SIN hardcoding.

**Implementación Real**:

1. **StrategyEngineFactory** (`core_brain/services/strategy_engine_factory.py` - NUEVO)
   - Lee todas las estrategias desde BD tabla `strategies` (SSOT)
   - Valida readiness (READY_FOR_ENGINE vs LOGIC_PENDING)
   - Valida dependencias (sensores requeridos disponibles)
   - Instancia dinámicamente cada estrategia una sola vez
   - Retorna Dict[strategy_id: engine] en memoria para O(1) lookup
   - Graceful degradation: falta dependencia = skip, no bloquea otras

2. **MainOrchestrator** (`core_brain/main_orchestrator.py` - REFACTORIZADO)
   - Línea 1328-1330: Ya NO hardcodea `OliverVelezStrategy` solamente
   - Ahora: `factory = StrategyEngineFactory(...); active_engines = factory.instantiate_all_strategies()`
   - Resultado: 2-4+ estrategias en memoria, dinámicamente cargadas

3. **SignalFactory** (`core_brain/signal_factory.py` - REFACTORIZADO FASE 2)
   - Parámetro constructor: `strategies: List` → `strategy_engines: Dict[str, Any]`
   - Itera sobre Dict en lugar de List: `for strategy_id, engine in self.strategy_engines.items()`
   - Benefit: O(1) lookup en lugar de O(n) iteración
   - **FASE 2 Refactorización** (5-Mar-2026): Fragmentación para cumplir Limit of Mass (<30KB, <500 líneas)
     - **Antes**: 37.94 KB, 782 líneas ❌ EXCEDE
     - **Después FASE 2**: **21.12 KB, 437 líneas** ✅ CUMPLE
     - Métodos extraídos a submódulos especializados:
   
   **Signal Processing Fragmentation (FASE 2) - COMPLETADA**:
   
   4a. **SignalDeduplicator** (`core_brain/signal_deduplicator.py` - NUEVO | 7.8 KB)
       - **Responsabilidad**: Detección y prevención de señales duplicadas
       - **Método público**: `is_duplicate(signal: Signal) -> bool`
       - **Algoritmos**:
         - Normalización de símbolos (Ej: "GBPUSD=X" → "GBPUSD")
         - Verificación de posiciones abiertas (temporal + real)
         - Reconciliación con MT5 (detección de ghost positions)
         - Limpieza automática de posiciones fantasma
       - **Integración**: Signal Factory lo inyecta en `__init__`, lo usa en `generate_signal()` línea 198
       - **Gobernanza**: ✅ DI obligatorio, ✅ SSOT (StorageManager), ✅ Type Hints 100%
   
   4b. **SignalConflictAnalyzer** (`core_brain/signal_conflict_analyzer.py` - NUEVO | 3.6 KB)
       - **Responsabilidad**: Análisis multi-timeframe de confluencia
       - **Método público**: `apply_confluence(signals, scan_results) -> List[Signal]`
       - **Lógica**:
         - Agrupa regímenes por símbolo (excluyendo timeframe primario)
         - Aplica bonus de confluencia si 2+ timeframes están en TREND
         - Formula: `new_score = original_score * (1 + confluence_bonus)`
       - **Integración**: Signal Factory lo inyecta en `__init__`, lo usa en `generate_signals_batch()` línea 395
       - **Gobernanza**: ✅ Lazy initialization, ✅ Error handling, ✅ Logging [CONFLUENCE]
   
   4c. **SignalTrifectaOptimizer** (`core_brain/signal_trifecta_optimizer.py` - NUEVO | 5.2 KB)
       - **Responsabilidad**: Filtrado Oliver Velez M2-M5-M15 multi-timeframe
       - **Método público**: `optimize(signals, scan_results) -> List[Signal]`
       - **Oliver Velez Logic**:
         - M2 (dirección): tendencia corta
         - M5 (confirmación): fuerza
         - M15 (macro contexto): validez setup
       - **Scoring**: `final_score = (original * 0.4) + (trifecta * 0.6)`, Filtro: >= 0.60
       - **DEGRADED MODE**: Si faltan timeframes, pasar signal sin trifecta
       - **Integración**: Signal Factory lo inyecta en `__init__`, lo usa en `generate_signals_batch()` línea 399
       - **Gobernanza**: ✅ Graceful degradation, ✅ Try-except en analyze(), ✅ TRACE_ID logging
   
   **Compliance Alcanzado**:
   - ✅ Limit of Mass: 21.12 KB < 30 KB, 437 líneas < 500 líneas
   - ✅ Type Hints 100%: Todos los parámetros y retornos tipados
   - ✅ DI Obligatorio: Todas las dependencias inyectadas en `__init__()`
   - ✅ SSOT: Delegan a StorageManager, no duplican lógica
   - ✅ Single Responsibility: Cada clase = una responsabilidad clara
   - ✅ Validación: 16/16 módulos PASSED en validate_all.py

**Estructura BD (SSOT)**:
```sql
CREATE TABLE strategies (
    class_id TEXT PRIMARY KEY,           -- BRK_OPEN_0001, MOM_BIAS_0001, etc.
    mnemonic TEXT NOT NULL,              -- NY_STRIKE_OPEN_GAP, MOMENTUM_STRIKE, etc.
    version TEXT DEFAULT '1.0',
    affinity_scores TEXT DEFAULT '{}',   -- JSON con scores
    market_whitelist TEXT DEFAULT '[]',  -- JSON con símbolos permitidos
    readiness TEXT,                      -- READY_FOR_ENGINE | LOGIC_PENDING
    readiness_notes TEXT,
    ...
)
```

**Carga Dinámica en Runtime**:
```python
# MainOrchestrator.__init__() línea 1328
factory = StrategyEngineFactory(storage=storage, config=dynamic_params)
active_engines = factory.instantiate_all_strategies()
# Result: {"BRK_OPEN_0001": engine1, "MOM_BIAS_0001": engine2, ...}

# SignalFactory recibe Dict, no List + inyecta submódulos FASE 2
signal_factory = SignalFactory(
    strategy_engines=active_engines,
    storage_manager=storage,
    confluence_analyzer=analyzer,
    mt5_connector=mt5
)
```

**Estructura BD (SSOT)**:
```sql
CREATE TABLE strategies (
    class_id TEXT PRIMARY KEY,           -- BRK_OPEN_0001, MOM_BIAS_0001, etc.
    mnemonic TEXT NOT NULL,              -- NY_STRIKE_OPEN_GAP, MOMENTUM_STRIKE, etc.
    version TEXT DEFAULT '1.0',
    affinity_scores TEXT DEFAULT '{}',   -- JSON con scores
    market_whitelist TEXT DEFAULT '[]',  -- JSON con símbolos permitidos
    readiness TEXT,                      -- READY_FOR_ENGINE | LOGIC_PENDING
    readiness_notes TEXT,
    ...
)
```

**Carga Dinámica en Runtime**:
```python
# MainOrchestrator.__init__() línea 1328
factory = StrategyEngineFactory(storage=storage, config=dynamic_params)
active_engines = factory.instantiate_all_strategies()
# Result: {"BRK_OPEN_0001": engine1, "MOM_BIAS_0001": engine2, ...}

# SignalFactory recibe Dict, no List
signal_factory = SignalFactory(strategy_engines=active_engines, ...)
```

**6 Firmas Operativas Registradas en BD**:

| class_id | mnemonic | type | readiness | affinity EUR/USD |
|----------|----------|------|-----------|-----------------|
| BRK_OPEN_0001 | NY_STRIKE_OPEN_GAP | JSON_SCHEMA | READY_FOR_ENGINE | 0.92 |
| institutional_footprint | INST_FOOTPRINT | JSON_SCHEMA | READY_FOR_ENGINE | 0.85 |
| MOM_BIAS_0001 | MOMENTUM_STRIKE | PYTHON_CLASS | READY_FOR_ENGINE | 0.82 |
| LIQ_SWEEP_0001 | LIQUIDITY_SWEEP_SCALPING | PYTHON_CLASS | READY_FOR_ENGINE | 0.92 |
| SESS_EXT_0001 | SESSION_EXTENSION | PYTHON_CLASS | LOGIC_PENDING | 0.89 |
| STRUC_SHIFT_0001 | STRUCTURE_SHIFT | PYTHON_CLASS | READY_FOR_ENGINE | 0.89 |

**Gobernanza**:
- ✅ SSOT = BD (data_vault/aethelgard.db tabla strategies)
- ✅ DEVELOPMENT_GUIDELINES 1.6 (Service Layer)
- ✅ DEVELOPMENT_GUIDELINES 1.4 (Explora antes de crear)

**Carga Dinámica**:
```python
# En MainOrchestrator.__init__()
registry = StrategyRegistry.load_from_json("config/strategy_registry.json")

for strategy_spec in registry.strategies:
    engine = UniversalStrategyEngine(strategy_spec)
    self.active_engines[strategy_spec.class_id] = engine
    logger.info(f"Loaded strategy {strategy_spec.class_id} (affinity: {strategy_spec.affinity_scores})")
```

---

### 2.4 StrategyGatekeeper - Guardia In-Memory (core_brain/strategy_gatekeeper.py)

**Responsabilidad**: Guard ultra-rápido que bloquea ejecución basado en Asset Affinity Scores.

**Lógica**:
```python
def can_execute_on_tick(
    self,
    symbol: str,
    strategy_id: str,
    min_affinity_threshold: float = 0.80
) -> bool:
    """¿Puede ejecutar esta estrategia en este activo?"""
    
    # 1. ¿Está el activo en whitelist?
    if symbol not in self.market_whitelist[strategy_id]:
        return False
    
    # 2. ¿Score >= threshold?
    score = self.affinity_scores[strategy_id].get(symbol, 0.0)
    return score >= min_affinity_threshold
```

**En MainOrchestrator**:
```python
for signal in active_signals:
    if not self.gatekeeper.can_execute_on_tick(
        signal.symbol,
        signal.strategy,
        min_threshold=0.80
    ):
        logger.debug(f"[VETO] {signal.strategy} bloqueado para {signal.symbol}")
        signals_to_execute.remove(signal)
        continue
    
    # Signal pasa a RiskManager
    signals_to_execute.append(signal)
```

---

## III. El Flujo Completo de Validación (Pipeline v2.0)

```
1. TICK LLEGA (market_data)
   ↓
2. UniversalStrategyEngine.analyze()
   - Interpreta schema JSON
   - Genera OutputSignal (candidata)
   ↓
3. StrategySignalValidator.validate() [4 PILARES]
   - Pilar 1: ¿Sensores disponibles? → SensorialPillar
   - Pilar 2: ¿Régimen permite? → RegimePillar
   - Pilar 3: ¿Membresía suficiente? → MultiTenantPillar
   - Pilar 4: ¿Coherencia validada? → CoherencePillar
   ↓ [ValidationReport: PASSED/FAILED/BLOCKED]
4. StrategyGatekeeper.can_execute_on_tick()
   - ¿activo en whitelist?
   - ¿score >= min_threshold?
   ↓
5. RiskManager.evaluate_signal()
   - Risk per trade
   - Máximo drawdown
   - Posiciones abiertas
   ↓
6. ConflictResolver.resolve_conflicts()
   - ¿Múltiples señales mismo activo?
   - Selecciona por Asset Affinity Score
   - Exclusión mutua: Una estrategia por activo
   ↓
7. Executor.execute_signal()
   - Abre posición
   - Registra TRACE_ID
   ↓
8. TradeClosureListener
   - Monitorea SL/TP
   - Calcula P&L
   - Actualiza affinity scores
   ↓
9. CoherenceService
   - Compara shadow vs live
   - Recalcula coherence_score
   - Ajusta dinámicamente
```

---

## IV. Single Source of Truth (SSOT) - Dónde Vive la Verdad

| Componente | Archivo/Tabla | Propósito |
|-----------|---------------|----------|
| **Estrategias** | db.strategies o strategy_registry.json | ✅ SSOT: Todas las firmas + affinity scores |
| **Coherencia** | db.strategies.coherence_score | ✅ SSOT: Health check validation |
| **Membresías** | db.users.membership_tier | ✅ SSOT: Niveles de acceso |
| **Configuración** | db.system_state | ✅ SSOT: Parámetros dinámicos |
| **Performance Histórica** | db.strategy_performance_logs | ✅ SSOT: Logs de trades para affinity |
| **Broker Accounts** | db.broker_accounts | ✅ SSOT: Cuentas DEMO y reales operativas |
| **Credenciales Encriptadas** | db.credentials (encrypted_data) | ✅ SSOT: Passwords encriptados con Fernet |
| **Data Providers** | db.data_providers | ✅ SSOT: Configuración de proveedores de datos |

### IV.A Gestión de Credenciales - Arquitectura de Seguridad

**Separación de Responsabilidades**:
- **broker_accounts**: METADATOS (account_id, broker_id, account_name, server, account_number, enabled, balance)
- **credentials**: DATOS SENSIBLES encriptados (encrypted_data = JSON encriptado con Fernet)
- **data_providers**: PROVEEDORES DE DATOS (config para MT5, Finnhub, CCXT, etc.)

**Flujo de Encriptación**:
1. Cliente ingresa password (UI o setup_mt5_demo.py)
2. StorageManager.save_broker_account() → crea en broker_accounts
3. Si password presente → StorageManager.update_credential() → encripta con get_encryptor() → guarda en credentials.encrypted_data
4. Lectura: get_credentials(account_id) → desencripta → retorna Dict

**Reglas de Seguridad**:
- ✅ Credenciales SOLO en DB encriptadas (Fernet symmetric encryption)
- ❌ NO almacenar passwords en .env, .json, o código
- ❌ NO loguear valores de credenciales (loguear solo "***")
- ✅ Clave de encriptación en .encryption_key (gitignored, 0o600 permisos)

### IV.B Seed Data - Inicialización Idempotente

**Ubicación**: `data_vault/seed/` (SSOT para bootstrapping)

**Archivos de Seed**:
1. **strategy_registry.json**: Estrategias del sistema (migracion ONE-TIME)
2. **demo_broker_accounts.json**: Cuentas DEMO para pruebas (NEW v2.1)
3. **data_providers.json**: Proveedores de datos por defecto (NEW v2.1)

**Reglas de Seed**:
- ✅ Permitido: Seedear METADATOS no sensibles (broker_id, account_name, server)
- ✅ Permitido: Seedear credenciales DEMO públicas (ej: login demo MT5 válido)
- ❌ PROHIBIDO: Credenciales operativas REALES o API keys hardjcodeadas
- ✅ Patrón: Usar { credential_password: "actualpassword" } en JSON, encriptarse al insertar
- Idempotencia: Script `seed_demo_data.py` verifica si existen antes de insertar

**Tablas Seedeadas en Startup**:
```
_bootstrap_from_json() {
  1. Seeds de estrategias (strategy_registry.json)
  2. Seeds de broker_accounts (demo_broker_accounts.json)
  3. Seeds de data_providers (data_providers.json)
  Flag: _json_bootstrap_done_v1 = true (solo corre 1 vez)
}
```

🚫 **PROHIBIDO**: Duplicar información en archivos .json, .env, o variables hardcodeadas. Única fuente = Base de datos + seeds idempotentes.

---

## V. Jerarquía de Validación: Qué se Ejecuta y Cuándo

### Nivel 1: FundamentalGuard Service (Máximum Veto)
- **Evento**: Comunicado banco central, dato macro crítico
- **Action**: BLOQUEA TODAS las estrategias (LOCKDOWN ±15 min)
- **Implementación**: `FundamentalGuardService.is_absolute_veto()`

### Nivel 2: RegimeClassifier (Veto Contextual)
- **Evento**: Régimen no coincide con regime_filter de estrategia
- **Action**: BLOQUEA estrategia para ese régimen
- **Implementación**: `RegimePillar.validate()`

### Nivel 3: Asset Affinity Score (Veto Estadístico)
- **Evento**: Histórico de strategy en activo < min_threshold
- **Action**: BLOQUEA ejecución en ese activo
- **Implementación**: `StrategyGatekeeper.can_execute_on_tick()`

### Nivel 4: Risk Management (Veto Financiero)
- **Evento**: % risk > límite daily, max consecutive losses alcanzado
- **Action**: BLOQUEA nuevas posiciones (permite cierre SL/TP)
- **Implementación**: `RiskManager.evaluate_signal()`

---

## VI. Protocolo TRACE_ID Obligatorio

Toda operación debe llevar un identificador único e inmutable para auditoría:

**Formato**:
```
{OPERATION_TYPE}-{STRATEGY_ID/CONTEXT}-{TIMESTAMP_ISO}-{UNIQUE_HASH}

Ejemplos:
- SIGNAL-BRK_OPEN_0001-20260303T091532Z-a4f7e2c1
- VALIDATION-S-0006-20260303T091545Z-b8d1f9c2
- EXEC-MOM_BIAS_0001-20260303T091600Z-c2e5a7d3
```

**Propagación**: Generada al crear señal → Persiste en DB trades → Visible en UI → Recuperable en auditoría.

---

## VII. Ciclo de Vida de Soberanía Estratégica

Para garantizar la excelencia institucional, una estrategia debe navegar un **sistema de doble aduana**. La coherencia entre el estado de desarrollo (Readiness) y el estado operativo (Execution) es **innegociable**.

### 7.1 Matriz de Estados de Doble Capa

| Capa | Estado (Key) | Descripción | Requisito de Salida |
|------|--------------|-------------|---------------------|
| **I. Readiness** (Desarrollo) | **LOGIC_PENDING** | Código incompleto, sensores no vinculados o firma JSON inválida | Estructura 100% conforme a guías de desarrollo |
| **I. Readiness** (Desarrollo) | **READY_FOR_ENGINE** | Código auditado y validado. Aprobada para carga en memoria | Superar `validate_all.py` (Integridad técnica) |
| **II. Execution** (Operación) | **SHADOW** (Default) | Operación espejo sin riesgo. Genera métricas de confianza | Alcanzar Score de Promoción (PF ≥ 1.5, WR ≥ 50%, 50+ Trades) |
| **II. Execution** (Operación) | **LIVE** | Ejecución real con capital institucional | Mantener métricas sobre umbral de salud |
| **II. Execution** (Operación) | **QUARANTINE** | Aislamiento por fallo métrico o anomalía (Circuit Break) | Enfriamiento (15 min) + Rectificación de métricas |

### 7.2 Matriz de Intersección (Lógica de Operatividad)

El sistema de control debe aplicar estas **reglas de combinación** para evitar estados inválidos:

| Readiness | Execution | Comportamiento del Sistema |
|-----------|-----------|---------------------------|
| **LOGIC_PENDING** | Cualquiera | **BLOQUEO TOTAL**: El motor no instancia la estrategia. No hay logs de ejecución. Es un ente inerte |
| **READY_FOR_ENGINE** | **SHADOW** | **ACTIVA (Testing)**: Carga en memoria, procesa señales, pero el conector es interceptado (Paper/Shadow log) |
| **READY_FOR_ENGINE** | **LIVE** | **ACTIVA (Real)**: Flujo completo de capital. El SovereignGovernor valida cada trade |
| **READY_FOR_ENGINE** | **QUARANTINE** | **SUSPENDIDA**: La estrategia procesa datos pero tiene el interruptor de envío de órdenes en OFF |

**📌 REGLA JERÁRQUICA CRÍTICA**: Si una estrategia está en estado **LOGIC_PENDING**, su **Execution Mode es irrelevante** y debe ser **ignorado por el Orquestador**. LOGIC_PENDING tiene prioridad absoluta: la estrategia **NO SE INSTANCIA**.

### 7.3 Casos de Retroceso (Downgrade de Readiness)

Una estrategia puede volver de **READY_FOR_ENGINE** a **LOGIC_PENDING** en los siguientes escenarios:

1. **Modificación de Firma**: Si el archivo JSON de configuración cambia sus parámetros base, el estado vuelve a LOGIC_PENDING hasta que el Auditor valide la nueva coherencia.

2. **Falla de Inyección**: Si un Sensor dependiente es eliminado o renombrado, el sistema degrada la estrategia automáticamente para proteger la integridad.

3. **Refactorización Obligatoria**: Si el Guardián de Arquitectura detecta que el archivo superó los límites de complejidad (>30KB) o introdujo "hardcodeo", revoca el estado READY.

### 7.4 Protocolos de Movimiento

**Promoción Automática** (`SHADOW ➔ LIVE`):
- Ejecutada por el **StrategyRanker** al cumplir:
  - ≥ 50 trades completados
  - Profit Factor (PF) ≥ 1.5
  - Win Rate (WR) ≥ 50%

**Degradación Automática** (`LIVE ➔ QUARANTINE`):
- Ejecutada por el **CircuitBreaker** si:
  - Max Drawdown > 3%
  - ≥ 3 pérdidas consecutivas

### 7.5 Vinculación con Dominio 05 (Ejecución Universal)

Esta sección representa el **corazón operativo** del Backlog Dominio 05 (EXECUTION_UNIVERSAL):
- **Readiness**: Valida coherencia lógica (responsabilidad de Desarrollo)
- **Execution**: Orquesta los modos operativos (responsabilidad de Operaciones)
- **Ciclo de Vida**: Define transiciones automáticas y manual overrides

---

## VIII. Integración en MainOrchestrator

**Cambios Requeridos**:

1. **__init__()**: Inyectar StrategyRegistry, StrategySignalValidator, StrategyGatekeeper, ConflictResolver
2. **run_single_cycle()**: Llamar validate() en 4 Pilares antes de RiskManager
3. **Bucle principal**: Iterar sobre dynamic strategies cargadas desde registry.json
4. **Cierre**: Actualizar base de datos con affinity scores aprendidos

**Pseudocódigo**:
```python
# MainOrchestrator.run_single_cycle()

# 1. Cargar estrategias dinámicamente
active_strategies = self.registry.get_active_strategies()

# 2. Generar señales
signals = []
for strategy in active_strategies:
    signal = await strategy.engine.analyze(...)
    if signal:
        signals.append(signal)

# 3. Validar con 4 Pilares
validated = []
for signal in signals:
    report = await self.validator.validate(signal)
    if report.is_approved():
        validated.append(signal)
    else:
        logger.warning(f"Signal rejected: {report.overall_status}")

# 4. Gatekeeper check
gated = []
for signal in validated:
    if self.gatekeeper.can_execute_on_tick(signal.symbol, signal.strategy):
        gated.append(signal)

# 5. Resolver conflictos (exclusión mutua)
approved, pending = self.conflict_resolver.resolve_conflicts(gated)

# 6. Ejecutar
for signal in approved:
    success = await self.executor.execute_signal(signal)
    if success:
        logger.info(f"Signal executed: {signal.trace_id}")
        # Actualizar gatekeeper con resultado
        self.gatekeeper.log_asset_performance(...)
```

---

## IX. Reglas Constitucionales Inmutables

1. ✅ **Agnosis Absoluta**: Cero imports de broker en core_brain. Solo en connectors/.
2. ✅ **DI Obligatorio**: Todas las clases reciben dependencias en __init__, no las crean.
3. ✅ **SSOT Única**: Base de datos = fuente de verdad. Files JSON = cache legible.
4. ✅ **Validación Multinivel**: 4 Pilares validan ANTES de RiskManager, no después.
5. ✅ **Trazabilidad**: Todo tiene TRACE_ID. Auditable 100%.
6. ✅ **Multi-tenant**: Aislamiento total por user_tier y tenant_id.
7. ✅ **Test Inmutables**: Si un test falla, corregir producción. Nunca relajar SL governor.
8. ✅ **Exclusión Mutua**: Una estrategia por activo simultáneamente.
9. ✅ **Escalabilidad**: Nueva estrategia = entrada registry. Sin redeploy.
10. ✅ **Type Hints 100% (OBLIGATORIO)**: Cobertura total de tipos en TODO el código Python.
    - ✅ **SÍ**: Parámetros de función, retornos, variables locales complejas.
    - ✅ **SÍ**: Usar enums (`SignalType`, `MarketRegime`, etc.) en lugar de strings.
    - ❌ **PROHIBIDO**: `signal_type="BUY"` → ✅ **USAR**: `signal_type=SignalType.BUY`
    - ❌ **PROHIBIDO**: Funciones sin tipo de retorno `def func():` → ✅ **USAR**: `def func() -> ReturnType:`
    - **Razón**: Captura errores en tiempo de análisis estático, mejora legibilidad, facilita refactorización.
    - **Validación**: `mypy --strict` se ejecuta en `scripts/code_quality_analyzer.py` como parte de `validate_all.py`
    - **Configuración**: `mypy.ini` con patrones moderados (permite migración gradual)
    - **Baseline**: 968 issues detectados (target: 0 en nuevo código, migración progresiva en legacy)
11. ✅ **Documentación Única**: AQUÍ (MANIFESTO) = fuente de verdad técnica. No READMEs dispersos.

---

## X. Próximas Tareas (Sprint 5: SALTO CUÁNTICO)

- [ ] ✅ Crear strategy_validator_quanter.py (4 Pilares) — **COMPLETADO**
- [ ] ✅ Crear strategy_registry.json (6 firmas) — **COMPLETADO**
- [ ] ✅ Crear check_engine_integrity.py (Test harness) — **COMPLETADO**
- [ ] Integrar validator en MainOrchestrator.run_single_cycle()
- [ ] Ejecutar check_engine_integrity.py y validar 4 Pilares en vivo
- [ ] Ejecutar validate_all.py (arquit validation)
- [ ] Ejecutar start.py (bootstrap sin errores)
- [ ] Actualizar ROADMAP.md (marcar completadas)

---

## XI. Referencia: Los 4 Pilares En Detalle

### Pilar Sensorial - PillarStatus: PASSED | FAILED | BLOCKED

```python
class SensorialPillar(ValidationPillar):
    """¿Están TODOS los sensores listos con datos frescos?"""
    
    async def validate(self, signal: OutputSignal) -> PillarValidationResult:
        """
        Verifica que cada sensor requerido esté disponible.
        
        Returns:
            PillarValidationResult(
                pillar_name="SENSORIAL",
                status=PillarStatus.PASSED,
                confidence=1.0,
                reason="All 5 sensors ready: FVG✓ MA20✓ MA50✓ ATR✓ Imbalance✓"
            )
        """
```

### Pilar Régimen

```python
class RegimePillar(ValidationPillar):
    """¿Permite el régimen actual esta estrategia?"""
    
    async def validate(self, signal: OutputSignal) -> PillarValidationResult:
        """
        Compara regime_actual vs regime_filter de estrategia.
        
        Returns:
            PillarValidationResult(
                pillar_name="REGIME",
                status=PillarStatus.PASSED,
                confidence=0.95,
                reason="Regime TREND_UP matches requirement"
            )
        OR
            PillarValidationResult(
                pillar_name="REGIME",
                status=PillarStatus.FAILED,
                confidence=0.0,
                reason="Regime RANGE but strategy requires TREND"
            )
        """
```

### Pilar Multi-Tenant

```python
class MultiTenantPillar(ValidationPillar):
    """¿Usuario tiene membresía suficiente?"""
    
    async def validate(self, signal: OutputSignal, user_tier: str) -> PillarValidationResult:
        """
        Verifica user_tier >= membership_required.
        
        Returns:
            PillarValidationResult(
                pillar_name="MULTI_TENANT",
                status=PillarStatus.BLOCKED,
                confidence=0.0,
                reason="Strategy requires Premium, user is Basic"
            )
        """
```

### Pilar Coherencia

```python
class CoherencePillar(ValidationPillar):
    """¿Es coherente la señal? (Confluencia, confidence, sin conflictos)"""
    
    async def validate(self, signal: OutputSignal) -> PillarValidationResult:
        """
        Verifica coherence_score >= 0.60, min 2 confirmadores.
        
        Returns:
            PillarValidationResult(
                pillar_name="COHERENCE",
                status=PillarStatus.PASSED,
                confidence=0.92,
                reason="Confluence: 3/4 elements (FVG+MA+Imbalance), shadow/live match 92%"
            )
        """
```

---

**Fecha de Creación**: 2026-03-03  
**Versión**: 2.1  
**Última Actualización**: 2026-03-05  
**Status**: 🚀 ACTIVO — CICLO DE VIDA DE SOBERANÍA ESTRATÉGICA IMPLEMENTADO
