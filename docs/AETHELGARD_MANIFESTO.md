# AETHELGARD MANIFESTO v2.0
## El Salto Cuántico: Archivo de Verdad para Arquitectura Basada en 4 Pilares de Validación

**Status**: 🚀 ACTIVO | **Version**: 2.0 | **TRACE_ID**: MANIFESTO-v2-SPRINT5 | **Fecha**: 2026-03-03

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

### 2.3 StrategyRegistry - SSOT Dinámica (config/strategy_registry.json)

**Responsabilidad**: Single Source of Truth de todas las firmas operativas. Permite carga dinámica.

**Estructura**:
```json
{
  "version": "1.0",
  "last_updated": "2026-03-03T15:00:00.000Z",
  "strategies": [
    {
      "strategy_id": "S-0001",
      "class_id": "BRK_OPEN_0001",
      "mnemonic": "NY_STRIKE_OPEN_GAP",
      "type": "JSON_SCHEMA",
      "affinity_scores": {
        "EUR/USD": 0.92,
        "GBP/USD": 0.88,
        "USD/JPY": 0.60
      },
      "regime_requirements": ["TREND_UP", "EXPANSION"],
      "membership_tier": "Premium",
      "required_sensors": [
        "FVGDetector",
        "MovingAverageSensor",
        "ImbalanceDetector",
        "RegimeClassifier"
      ],
      "status": "OPERATIVE",
      "schema_version": "1.0"
    },
    ... (5 más: S-0002 a S-0006)
  ]
}
```

**6 Firmas Operativas Registradas**:

| ID | Nombre | Tipo | Tier | Affinity EUR/USD | Status |
|----|--------|------|------|------------------|--------|
| S-0001 | BRK_OPEN_0001 | JSON | Premium | 0.92 | ✅ OPERATIVE |
| S-0002 | institutional_footprint | JSON | Premium | 0.85 | ✅ OPERATIVE |
| S-0003 | MOM_BIAS_0001 | Python | Standard | 0.82 | ✅ OPERATIVE |
| S-0004 | LIQ_SWEEP_0001 | Python | Premium | 0.92 | 📋 SHADOW |
| S-0005 | SESS_EXT_0001 | Python | Premium | 0.89 | 📋 SHADOW |
| S-0006 | STRUC_SHIFT_0001 | Python | Free | 0.89 | 📋 SHADOW |

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
| **Estrategias** | config/strategy_registry.json | ✅ SSOT: Todas las firmas + affinity scores |
| **Coherencia** | db.strategies.coherence_score | ✅ SSOT: Health check validation |
| **Membresías** | db.users.membership_tier | ✅ SSOT: Niveles de acceso |
| **Configuración** | db.config | ✅ SSOT: Parámetros dinámicos |
| **Performance Histórica** | db.strategy_performance_logs | ✅ SSOT: Logs de trades para affinity |

🚫 **PROHIBIDO**: Duplicar información en archivos .json, .env, o variables hardcodeadas. Única fuente = Base de datos o strategy_registry.json para descubrimiento dinámico.

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

## VII. Integración en MainOrchestrator

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

## VIII. Reglas Constitucionales Inmutables

1. ✅ **Agnosis Absoluta**: Cero imports de broker en core_brain. Solo en connectors/.
2. ✅ **DI Obligatorio**: Todas las clases reciben dependencias en __init__, no las crean.
3. ✅ **SSOT Única**: Base de datos = fuente de verdad. Files JSON = cache legible.
4. ✅ **Validación Multinivel**: 4 Pilares validan ANTES de RiskManager, no después.
5. ✅ **Trazabilidad**: Todo tiene TRACE_ID. Auditable 100%.
6. ✅ **Multi-tenant**: Aislamiento total por user_tier y tenant_id.
7. ✅ **Test Inmutables**: Si un test falla, corregir producción. Nunca relajar SL governor.
8. ✅ **Exclusión Mutua**: Una estrategia por activo simultáneamente.
9. ✅ **Escalabilidad**: Nueva estrategia = entrada registry. Sin redeploy.
10. ✅ **Docuentación Única**: AQUÍ (MANIFESTO) = fuente de verdad técnica. No READMEs dispersos.

---

## IX. Próximas Tareas (Sprint 5: SALTO CUÁNTICO)

- [ ] ✅ Crear strategy_validator_quanter.py (4 Pilares) — **COMPLETADO**
- [ ] ✅ Crear strategy_registry.json (6 firmas) — **COMPLETADO**
- [ ] ✅ Crear check_engine_integrity.py (Test harness) — **COMPLETADO**
- [ ] Integrar validator en MainOrchestrator.run_single_cycle()
- [ ] Ejecutar check_engine_integrity.py y validar 4 Pilares en vivo
- [ ] Ejecutar validate_all.py (arquit validation)
- [ ] Ejecutar start.py (bootstrap sin errores)
- [ ] Actualizar ROADMAP.md (marcar completadas)

---

## X. Referencia: Los 4 Pilares En Detalle

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
**Versión**: 2.0  
**Última Actualización**: 2026-03-03  
**Status**: 🚀 ACTIVO — SPRINT 5: SALTO CUÁNTICO EN EJECUCIÓN
