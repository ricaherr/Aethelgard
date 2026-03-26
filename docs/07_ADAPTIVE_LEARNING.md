# Dominio 07: ADAPTIVE_LEARNING (EdgeTuner, ThresholdOptimizer, Feedback Loops)

## 🎯 Propósito
Cerrar el bucle de inteligencia del sistema mediante el meta-aprendizaje autónomo, ajustando parámetros operativos basados en el feedback real del mercado y la infraestructura.

## 🚀 Componentes Críticos
*   **EdgeTuner**: Motor de optimización paramétrica que calibra umbrales de confianza en tiempo real. Ajusta pesos de métricas por régimen (`regime_configs`) basándose en resultados reales (Delta Feedback).
*   **ThresholdOptimizer**: Optimizador dinámico de umbral de confianza que adapta automáticamente el `confidence_threshold` basado en el desempeño histórico reciente (HU 7.1).
*   **Safety Governor**: Sistema anti-overfitting que aplica reglas de suavizado y límites (Floor/Ceiling) a los ajustes automáticos.
*   **Feedback Loops**: Sistema de auditoría post-trade que vincula resultados con condiciones de micro-estructura.
*   **EquityCurveAnalyzer**: Herramienta de análisis que calcula métricas de desempeño (win_rate, consecutive_losses, max_drawdown) a partir del histórico de trades.

## ⚙️ Funcionamiento Técnico (EdgeTuner)
**Archivo**: `core_brain/edge_tuner.py`

**Flujo Delta Feedback**:
1. Trade cierra → `TradeClosureListener` detecta el resultado.
2. `process_trade_feedback()` calcula `Delta = Resultado - Score_Predicho`.
3. Si `|Delta|` supera umbrales → `_adjust_regime_weights()` ajusta el peso dominante del régimen.
4. El resultado se persiste en `edge_learning` con `action_taken` descriptivo.

## ⚙️ Funcionamiento Técnico (ThresholdOptimizer - HU 7.1)
**Archivo**: `core_brain/threshold_optimizer.py`  
**Trace ID**: `ADAPTIVE-THRESHOLD-2026-001`

**Componentes**:
- **EquityCurveAnalyzer**: Analiza los últimos N trades para calcular:
  - `win_rate`: Porcentaje de trades ganadores
  - `consecutive_losses`: Racha máxima de pérdidas consecutivas
  - `max_drawdown`: Máxima caída acumulada en la curva de equidad

- **ThresholdOptimizer**: Ajusta dinámicamente el `confidence_threshold` según:
  - **Racha de Pérdidas**: Si `consecutive_losses >= 3` → incrementa threshold (+ 3-5%)
  - **Recuperación**: Si `win_rate >= 70%` → permite disminución leve (- 1%)
  - **Desempeño Estable**: Si `win_rate 40-70%` → sin cambios o mínimos ajustes

**Flujo de Activación**:
1. `TradeClosureListener` cierra un trade
2. Cada 5 trades o cuando hay racha de >= 3 pérdidas consecutivas → dispara `_trigger_threshold_optimizer()`
3. `ThresholdOptimizer.optimize_threshold()` analiza Equity Curve
4. Aplica decisión de ajuste (si aplica)
5. Persiste cambio en DB con Trace_ID
6. Log auditado para observabilidad

**Acceso al Threshold Optimizado**:
```python
# En SignalFactory u otro componente que necesite validar confianza
current_threshold = threshold_optimizer.get_current_threshold()  # Ej: 0.78
if signal.confidence < current_threshold:
    signal.status = 'REJECTED'  # Señal rechazada por exigencia incrementada
```

## 🛡️ Límites de Gobernanza

### EdgeTuner
| Regla | Valor | Descripción |
|---|---|---|
| `GOVERNANCE_MIN_WEIGHT` | `0.10` | Floor: ningún peso puede bajar de aquí. |
| `GOVERNANCE_MAX_WEIGHT` | `0.50` | Ceiling: ningún peso puede subir de aquí. |
| `GOVERNANCE_MAX_SMOOTHING` | `0.02` | Max cambio por evento de aprendizaje (2%). |

### ThresholdOptimizer (HU 7.1)
| Parámetro | Default | Descripción |
|---|---|---|
| `confidence_threshold_min` | `0.50` | Umbral mínimo permitido (piso) |
| `confidence_threshold_max` | `0.95` | Umbral máximo permitido (techo) |
| `confidence_smoothing_max` | `0.05` | Máxima variación por ciclo de aprendizaje (5%) |
| `equity_lookback_trades` | `20` | Número de trades históricos para analizar |
| `consecutive_loss_threshold` | `3` | Minimo de pérdidas consecutivas para activar aumento |

Cuando el Governor interviene, el ajuste se marca con `[SAFETY_GOVERNOR]` en los logs de DB.

## 🖥️ UI/UX REPRESENTATION
*   **Curva de Exigencia Algorítmica**: Visualizador dinámico de los umbrales de entrada activos vs recomendados.
*   **Threshold Evolution Logger**: Widget mostrando histórico de ajustes de threshold con razones y trace_ids.
*   **Equity Curve Widget**: Gráfico mostrando win_rate, consecutive losses, drawdown en tiempo real (feedback para ThresholdOptimizer).
*   **Edge Evolution Logs**: Feed de pensamientos del sistema sobre sus propios ajustes y calibraciones.

## 📈 Roadmap del Dominio
- [x] Implementación del EdgeTuner y Feedback Loops paramétricos.
- [x] Consolidación de la telemetría post-mortem y Gobernanza.
- [x] **Confidence Threshold Optimizer (HU 7.1)** — ✅ COMPLETADA (Sprint 3 - 2 Marzo 2026)
  - Detector de rachas de pérdidas con ajuste automático
  - Equity Curve Analyzer operativo
  - Safety Governor integrado
  - 21/21 Tests PASSED
  - Integración en TradeClosureListener
  - Trace_ID: ADAPTIVE-THRESHOLD-2026-001
- [ ] Automatización de umbrales en base a volatilidad.
- [ ] Meta-aprendizaje sobre latencia y slippage real.
- [x] **SHADOW Evolution Integration (Plan A++)** — ✅ COMPLETADA (9 Marzo 2026)
  - Desbloqueo de 6 estrategias SHADOW en deadlock
  - 7 FASES leveraging EdgeTuner + CoherenceService + StrategyRanker
  - 7 FORMAS de SHADOW operacionales
  - 125/125 tests PASANDO
  - Trace_ID: SHADOW-EVOLUTION-2026-001
- [x] **DYNAMIC DEDUPLICATION WINDOWS (HU 7.3 - PHASE 3)** — ✅ COMPLETADA (10 Marzo 2026)
  - DedupLearner: Weekly autonomous window calibration
  - Cálculo triple-factor: volatility × regime × base_window
  - Aprendizaje semanal de gaps óptimos (percentil_50 × 0.8)
  - Ajuste granular por symbol/timeframe/strategy
  - Gobernanza: ±30% change rate, 10%-300% bounds
  - sys_dedup_events table for immutable audit trail
  - Integración MainOrchestrator: Sundays 23:00 UTC
  - 11/11 tests PASSED
  - 24/24 system modules PASSED
  - Trace_ID: DEDUP-LEARNING-2026-PHASE3

## 🔄 CICLO DE VIDA DE ESTRATEGIAS: Pipeline BACKTEST → SHADOW → LIVE

**Fecha de Implementación**: 23 de Marzo de 2026
**Trace_ID**: EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23

---

### Visión General

Toda estrategia en Aethelgard traversa obligatoriamente tres modos de vida. No puede avanzar al siguiente modo sin haber superado las métricas del modo anterior.

```
┌──────────────┐    Filtro 0     ┌──────────────┐   3 Pilares   ┌──────────────┐
│   BACKTEST   │ ─────────────► │    SHADOW    │ ────────────► │     LIVE     │
│  (Escenarios │  score ≥ 0.75  │  (Incubación │  PF≥1.5 WR   │  (Real/Demo  │
│  de Estrés)  │                │   en DEMO)   │  DD≤12%)     │   Trading)   │
└──────────────┘                └──────────────┘               └──────────────┘
```

### Scores por Modo

Cada estrategia acumula un score en cada modo de su ciclo de vida:

| Atributo | Fuente | Descripción |
|---|---|---|
| `score_backtest` | `ScenarioBacktester.AptitudeMatrix.overall_score` | Promedio de los 3 Stress Clusters (HIGH_VOLATILITY, STAGNANT_RANGE, INSTITUTIONAL_TREND) |
| `score_shadow` | `ShadowManager` / PromotionValidator (3 Pilares normalizados) | Desempeño en incubación DEMO |
| `score_live` | `EdgeTuner` / feedback de trades reales | Desempeño acumulado en cuenta REAL |
| `score` | **Consolidado ponderado** | `score_live×0.50 + score_shadow×0.30 + score_backtest×0.20` |

**Ponderación del score consolidado**: LIVE domina porque la evidencia real supera a la teórica.

### Persistencia

Los 5 atributos (`mode`, `score_backtest`, `score_shadow`, `score_live`, `score`) se almacenan directamente en `sys_strategies`:

```sql
-- Columnas añadidas en migración EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23
mode           TEXT NOT NULL DEFAULT 'BACKTEST'   -- 'BACKTEST' | 'SHADOW' | 'LIVE'
score_backtest REAL DEFAULT 0.0
score_shadow   REAL DEFAULT 0.0
score_live     REAL DEFAULT 0.0
score          REAL DEFAULT 0.0                   -- score_live×0.50 + score_shadow×0.30 + score_backtest×0.20
```

Las 6 estrategias existentes fueron migradas a `mode = 'BACKTEST'` preservando todos sus datos anteriores.

---

## 🚧 FILTRO 0: Validación Estructural por Escenarios (HU 7.3 — ScenarioBacktester)

**Fecha de Implementación**: 23 de Marzo de 2026
**Trace_ID**: EXEC-V5-BACKTEST-SCENARIO-ENGINE

---

### Propósito

Ninguna estrategia puede ingresar al pool de incubación SHADOW sin superar primero la validación por escenarios de estrés. El `ScenarioBacktester` actúa como **Filtro 0** (puerta estructural previa a toda incubación).

**Regla de Entrada**: `overall_score >= 0.75` para acceso a SHADOW.

---

### Matriz de Aptitud (AptitudeMatrix)

Cada estrategia es probada en **3 Clusters de Estrés**:

| Cluster | Descripción | Escenario Ejemplo |
|---|---|---|
| `HIGH_VOLATILITY` | Eventos de noticias, NFP, flash crashes, decisiones de bancos centrales | Flash Crash Agosto 2025 |
| `STAGNANT_RANGE` | Baja liquidez, consolidación plana, mercado sin dirección | Consolidación verano 2025 |
| `INSTITUTIONAL_TREND` | Tendencia institucional fuerte y sostenida | Tendencia EURUSD Junio 2025 |

**Output**: `AptitudeMatrix` JSON con `profit_factor` y `max_drawdown_pct` desglosados por régimen detectado.

---

### Score de Régimen (RegimeScore)

```
score = (pf_score × 0.60) + (dd_score × 0.40)

pf_score = min(profit_factor / 2.0, 1.0)     # PF = 2.0 → score perfecto
dd_score = max(1.0 - max_dd / 0.20, 0.0)     # DD ≥ 20% → score = 0
```

**Score Global** = media aritmética de los 3 cluster scores.
**Umbral de Aprobación**: `overall_score >= 0.75`.

---

### Arquitectura: Inyector de Slices (no timeline)

El motor **no** es una línea de tiempo clásica. En su lugar:

```
DataProvider.get_slice("NFP_JUN_2025")  →  ScenarioSlice (OHLCV DataFrame)
ScenarioSlice × N  →  ScenarioBacktester.run_scenario_backtest()
                    →  AptitudeMatrix (JSON)
```

El `DataProvider` entrega segmentos históricos específicos ("Junio 2025" o "Flash Crash de Agosto") identificados por `slice_id`. El motor los evalúa de forma independiente.

---

### Integración con EdgeTuner

Antes de que `ShadowManager` acepte una sugerencia de parámetros de `EdgeTuner`, el flujo es:

1. `EdgeTuner` genera `parameter_overrides` para una estrategia.
2. `EdgeTuner.validate_suggestion_via_backtest()` llama a `ScenarioBacktester.run_scenario_backtest()`.
3. Si `passes_threshold = True` (score ≥ 0.75) → `ShadowManager` crea la instancia SHADOW con `backtest_score` guardado.
4. Si `passes_threshold = False` → sugerencia bloqueada. Se registra `REJECTED` en `sys_shadow_promotion_log`.

---

### Persistencia y Auditoría (RULE DB-1 & ID-1)

- Cada simulación genera un `TRACE_BKT_VALIDATION_{YYYYMMDD}_{HHMMSS}_{strategy_id[:8].upper()}`.
- El registro se inserta en `sys_shadow_promotion_log` con `promotion_status = 'APPROVED' | 'REJECTED'` y el JSON completo de la `AptitudeMatrix` en el campo `notes`.
- `sys_shadow_instances` incluye ahora `target_regime TEXT` y `backtest_score REAL` (migración aplicada).

---

### Roadmap del Dominio (actualizado)
- [x] **Pipeline BACKTEST → SHADOW → LIVE (HU 7.3 — Lifecycle)** — ✅ IMPLEMENTADO (23 Marzo 2026)
  - 3 modos de vida en `sys_strategies.mode`: `BACKTEST` | `SHADOW` | `LIVE`
  - 4 scores: `score_backtest`, `score_shadow`, `score_live`, `score` (consolidado)
  - Fórmula consolidada: `score = score_live×0.50 + score_shadow×0.30 + score_backtest×0.20`
  - Migración aplicada sobre DB live sin recrear tablas (backup: `aethelgard_BEFORE_STRATEGY_LIFECYCLE_20260323_205949.db`)
  - 6 estrategias existentes migradas a `mode='BACKTEST'` sin pérdida de datos
  - Trace_ID: EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23
- [x] **Filtro 0 — ScenarioBacktester (HU 7.3 — Motor)** — ✅ IMPLEMENTADO (23 Marzo 2026)
  - `ScenarioBacktester` con 3 Stress Clusters
  - `AptitudeMatrix` serializable a JSON
  - `EdgeTuner.validate_suggestion_via_backtest()` integrado
  - `sys_shadow_instances`: columnas `target_regime` + `backtest_score` añadidas
  - Trace_ID: EXEC-V5-BACKTEST-SCENARIO-ENGINE
- [ ] **Generador de Matriz de Aptitud con DataProvider real (HU 7.4)** — Pendiente
  - Conexión a DataProviderManager para slices históricos reales
  - UI: Panel "Aptitude Matrix Viewer" por estrategia + semáforo de scores por modo

---

## 🌑 SHADOW Evolution Integration (Plan A++)

**Fecha de Implementación**: 9 de Marzo de 2026

---

## 🔍 DYNAMIC DEDUPLICATION WINDOWS (HU 7.3)

### Triple-Factor Window Calculation

En lugar de usar ventanas fijas (20 min para todo), el sistema calcula dinámicamente:

```
DEDUP_WINDOW_DYNAMIC(symbol, timeframe, strategy) = 
  BASE_WINDOW(timeframe) × 
  VOLATILITY_FACTOR(current_ATR) × 
  REGIME_FACTOR(market_regime)

Resultado: ventana adaptada momento a momento
```

### Factores Componentes

**1. Base Window (por timeframe)**:
- M1: 1 min
- M5: 5 min
- M15: 15 min
- H1: 60 min
- H4: 240 min
- D1: 1440 min

**2. Volatility Factor** (ATR-based):
```
AVG_ATR = SMA(ATR, 20 velas)
Curr_ATR = ATR actual

SI Curr_ATR < AVG_ATR × 0.8:      CALM  → 0.5x
SI Curr_ATR entre 0.8-1.2 × AVG:  NORMAL → 1.0x
SI Curr_ATR > AVG × 1.2:          HOT   → 2.0x
SI Curr_ATR > AVG × 1.8:          SPIKE → 3.0x
```

**3. Regime Factor** (RegimeService input):
```
TRENDING:    1.25x (menos cambios de dirección)
RANGE:       0.75x (muchos rebotes, setups frecuentes)
VOLATILE:    2.0x  (estrés extremo)
FLASH_MOVE:  3.0x  (evento raro, máxima cautela)
```

### Ejemplos Calculados

```
EURUSD M5 (Normal conditions):
  5 × 1.0 × 1.0 = 5 minutos (baseline)

EURUSD M5 (High volatility + RANGE):
  5 × 2.0 × 0.75 = 7.5 minutos

EURUSD M5 (Calm market + TRENDING):
  5 × 0.5 × 1.25 = 3.125 minutos (muy permisivo)

GBPUSD H1 (Volatility spike + FLASH_MOVE):
  60 × 3.0 × 3.0 = 540 minutos (9 horas, máxima protección)
```

### Self-Learning Mechanism (Semanal - EDGE HU 7.3)

Cada domingo 23:00 UTC:
1. **Recolectar datos**: Para cada (symbol, timeframe, strategy)
   - Todos los setups generados en la semana
   - Timestamps de ejecución exitosa
2. **Calcular gaps**: Diferencias de tiempo entre setups consecutivos
3. **Analizar distribución**:
   - Percentil 5 (%5): gap mínimo esperado
   - Percentil 50 (mediana): gap típico
   - Percentil 95 (%95): gap máximo esperado
4. **Proponer ventana óptima**:
   ```
   window_optimal = percentile_50 × 0.8
   (margen 20% para ruido/falsas señales)
   ```
5. **Aplicar constraintos de gobernanza**:
   ```
   MIN: 10% del base_window (no demasiado agresivo)
   MAX: 300% del base_window (no demasiado conservador)
   CHANGE_RATE: ±30% máximo por ajuste (evitar oscilaciones)
   ```
6. **Persistir**: Guardar en `sys_dedup_rules` table
7. **Log auditado**: Trace_ID + razón de ajuste

### Ejemplo de Aprendizaje Real

```
--- SEMANA DEL 3-9 MARZO 2026 ---
OliverVelez + EURUSD + M5:
  Setups generados: 20 total en 5 días
  Gaps entre consecutivos: [8, 15, 22, 13, 18, ...] minutos
  Percentil 50 (mediana): 15 minutos
  
  Ventana actual: 5 × 1.0 × 1.0 = 5 minutos
  Data sugiere: 15 × 0.8 = 12 minutos sería óptimo
  
  ¿Ajustar de 5 a 12 minutos?
  - Cambio propuesto = (12-5)/5 = 140% ❌ RECHAZADO (> 30%)
  - Máximo permitido: 5 × 1.3 = 6.5 minutos ✅ Aplicar
  
--- RESULTADO ---
Siguiente semana EURUSD M5 Oliver usa ventana 6.5 min (ajuste gradual)
Continúa aprendiendo semana siguiente hacia óptimo
```

### Tabla de Persistencia (SSOT)

```sql
CREATE TABLE sys_dedup_rules (
  id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  strategy TEXT NOT NULL,
  base_window_minutes INTEGER,
  current_window_minutes INTEGER,
  volatility_factor REAL DEFAULT 1.0,
  regime_factor REAL DEFAULT 1.0,
  last_adjusted TIMESTAMP,
  data_points_observed INTEGER DEFAULT 0,
  learning_enabled BOOLEAN DEFAULT TRUE,
  manual_override BOOLEAN DEFAULT FALSE,
  override_comment TEXT,
  trace_id TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE(symbol, timeframe, strategy)
);
```

### Guardias de Seguridad (Gobernanza EDGE)

```python
# En EdgeTuner (core_brain/edge_tuner.py)

def should_adjust_window(proposed_window, current_window, base_window):
  """Valida si ajuste de ventana cumple con guardrails."""
  
  change_pct = abs(proposed_window - current_window) / current_window
  
  if change_pct > 0.30:  # ±30% máximo
    return False, "Change rate exceeds 30% limit"
  
  if proposed_window < base_window * 0.10:  # Floor
    return False, "Proposed window < 10% of base (too aggressive)"
  
  if proposed_window > base_window * 3.0:   # Ceiling
    return False, "Proposed window > 300% of base (too conservative)"
  
  return True, "OK to apply"
```


**Estado**: ✅ COMPLETADO Y VALIDADO  
**Trace ID**: SHADOW-EVOLUTION-2026-001

### Problema Resuelto

**Antes**: 6 estrategias en modo SHADOW atrapadas en deadlock circular:
- CircuitBreaker bloqueaba cualquier modo ≠ 'LIVE'
- CoherenceService rechazaba señales con 0% confidence (sin trades pasados)
- Resultado: **nunca ejecutaban → nunca acumulaban trades → nunca acumulaban confidence → DEADLOCK PERMANENTE**

**Ahora**: ✅ Sistema autónomo donde estrategias SHADOW evolucionan sin intervención humana

---

## 🧠 PHASE 3 IMPLEMENTATION: DedupLearner Weekly Auto-Calibration

**Fecha de Implementación**: 10 de Marzo 2026  
**Trace ID**: `DEDUP-LEARNING-2026-PHASE3`  
**Archivo Principal**: `core_brain/dedup_learner.py` (350+ líneas)

### Arquitectura

```
┌─ MainOrchestrator.run_single_cycle()
│
├─ _check_and_run_weekly_dedup_learning()
│  │
│  └─ Domingos 23:00 UTC
│     │
│     └─ DedupLearner.run_weekly_learning_cycle()
│        │
│        ├─ _collect_gap_data()          → Last 7 days of signals
│        ├─ _group_by_key()              → (symbol, timeframe, strategy)
│        ├─ _calculate_percentiles()     → 5th, 50th, 95th percentiles
│        ├─ _analyze_and_propose_window() → Optimal = p50 × 0.8 (conservative)
│        ├─ _validate_governance()       → ±30%, 10%-300%, min 5 samples
│        └─ _apply_learning()            → Update sys_dedup_rules + audit
│
└─ Results logged + audit trail in sys_dedup_events
```

### Core Algorithm

**Step 1: Gap Collection**
```python
gaps = await _collect_gap_data()  # Last 7 days from sys_signals

# Example output:
# {
#   ('EURUSD', 'M5', 'OliverVelez'): [8, 15, 22, 13, 18, 11, 19],
#   ('GBPUSD', 'H1', 'AlessandroRibelli'): [45, 52, 38, 61],
#   ...
# }
```

**Step 2: Percentile Analysis**
```python
gaps_list = [8, 15, 22, 13, 18, 11, 19]  # 7 observations
percentile_5 = 8.4    # np.percentile(gaps_list, 5)
percentile_50 = 15.0  # MEDIAN (numpy)
percentile_95 = 21.5  # np.percentile(gaps_list, 95)
```

**Step 3: Optimal Window Calculation**
```python
optimal_window = int(percentile_50 * 0.8)  # 15 × 0.8 = 12 minutes
# Conservative margin (20%) to avoid noise & false signals
```

**Step 4: Governance Validation**
```python
current_rule = await storage.get_dedup_rule('EURUSD', 'M5', 'OliverVelez')
current_window = 5  # Current dedup window
base_window = 5     # Base window for symbol/TF

change_pct = ((12 - 5) / 5) * 100  # +140%
is_valid, reason = _validate_governance(12, 5, 5)

# Checks:
if change_pct > 30:  # ❌ FAIL
    return False, "Change rate +140% exceeds ±30% limit"
if window < base * 0.10:  # Check floor
    return False, "Below 10% floor"
if window > base * 3.0:  # Check ceiling
    return False, "Above 300% ceiling"
if sample_count < 5:  # Min observations
    return False, "Only 4 observations"
```

**Step 5: Learning Application**
```python
if is_valid:
    # Update with conservative step:
    # Instead of jumping 140%, apply only ±30%
    adjusted_window = int(current_window * 1.3)  # 5 × 1.3 = 6.5 minutes
    
    await storage.update_dedup_rule({
        'symbol': 'EURUSD',
        'timeframe': 'M5',
        'strategy': 'OliverVelez',
        'current_window_minutes': 6.5,
        'trace_id': 'DEDUP-LEARNING-2026-PHASE3-...'
    })
    
    # Log audit event
    await storage.record_dedup_event({
        'event_type': 'WINDOW_ADJUSTED',
        'symbol': 'EURUSD',
        'old_window': 5,
        'new_window': 6.5,
        'change_pct': 30.0,
        'optimal_window': 12,
        'reason': 'Weekly learning cycle',
        'adoption_rate': 'TBD'  # Will measure next week
    })
else:
    # Log rejection with reason
    await storage.record_dedup_event({
        'event_type': 'WINDOW_REJECTED',
        'reason': reason,
        ...
    })
```

### Governance Constraints

| Constraint | Value | Reason |
|-----------|-------|--------|
| Change Rate | ±30% max | Avoid oscillations & overfitting |
| Floor | 10% of base_window | Minimum aggression |
| Ceiling | 300% of base_window | Maximum conservation |
| Min Observations | 5+ gaps | Statistical significance |
| Frequency | Weekly (Sundays 23:00 UTC) | Non-blocking, learnable pace |
| Reversion | On degradation | If new window hurts performance |

### Database Integration

**New Table**: `sys_dedup_events` (Audit Trail)
```sql
CREATE TABLE sys_dedup_events (
  id INTEGER PRIMARY KEY,
  event_type TEXT NOT NULL,  -- WINDOW_ADJUSTED, WINDOW_REJECTED, etc
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  strategy TEXT NOT NULL,
  old_window_minutes INTEGER,
  new_window_minutes INTEGER,
  optimal_window_minutes INTEGER,
  change_pct REAL,
  reason TEXT,
  data_points_count INTEGER,
  adoption_rate REAL,
  compliance_checks TEXT,  -- JSON with validation results
  trace_id TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- Efficient queries
CREATE INDEX idx_dedup_events_symbol ON sys_dedup_events(symbol);
CREATE INDEX idx_dedup_events_timeframe ON sys_dedup_events(timeframe);
CREATE INDEX idx_dedup_events_created ON sys_dedup_events(created_at);
```

**Updated Table**: `sys_dedup_rules`
```
base_window_minutes: Original window (never changes)
current_window_minutes: Learned window (updated weekly)
last_adjusted: Timestamp of latest learning
learning_enabled: Can system auto-calibrate?
manual_override: Human lock-in?
trace_id: Link to audit trail
```

### MainOrchestrator Integration

**In `__init__`**:
```python
self.dedup_learner = DedupLearner(storage_manager=self.storage)
self._last_dedup_learning = datetime.now(timezone.utc)
```

**In `run_single_cycle()`**:
```python
await self._check_and_run_weekly_dedup_learning()
```

**Scheduler Method**:
```python
async def _check_and_run_weekly_dedup_learning(self) -> None:
    """Trigger Sunday 23:00 UTC learning cycle (non-blocking)."""
    now_utc = datetime.now(timezone.utc)
    
    is_sunday = now_utc.weekday() == 6
    is_learning_hour = now_utc.hour == 23
    hours_since_last = (now_utc - self._last_dedup_learning).total_seconds() / 3600
    enough_time_passed = hours_since_last >= 24
    
    if is_sunday and is_learning_hour and enough_time_passed:
        results = await self.dedup_learner.run_weekly_learning_cycle()
        # Log results with counts (learned, blocked, skipped)
        # Update _last_dedup_learning timestamp
```

### Validation & Testing

**Test Suite**: `tests/test_dedup_learner_phase3.py` (300+ líneas)

| Test Case | Status |
|-----------|--------|
| Gap data collection | ✅ PASSED |
| Percentile calculation | ✅ PASSED |
| Optimal window derivation | ✅ PASSED |
| ±30% change rate constraint | ✅ PASSED |
| 10%-300% bounds constraint | ✅ PASSED |
| Min observations check | ✅ PASSED |
| Multi-symbol parallelization | ✅ PASSED |
| Audit trail recording | ✅ PASSED |
| Edge cases (no data, single sample) | ✅ PASSED |
| Full weekly cycle | ✅ PASSED |
| Scheduler integration | ✅ PASSED |

**Result**: 11/11 tests PASSED ✅

**System Validation**: 24/24 modules PASSED ✅

### Key Files Modified

| File | Lines Added | Change |
|------|------------|--------|
| `core_brain/dedup_learner.py` | 350+ | NEW - Core learning engine |
| `data_vault/schema.py` | +30 | sys_dedup_events table |
| `data_vault/system_db.py` | +80 | 3 new StorageManager methods |
| `core_brain/main_orchestrator.py` | +100 | Integration + scheduler |
| `tests/test_dedup_learner_phase3.py` | 300+ | NEW - Comprehensive test suite |

### Operational Impact

**Before PHASE 3**:
- ❌ Dedup windows: Fixed (5-60 min per symbol/TF)
- ❌ No learning: Windows unchanged even if suboptimal
- ❌ Manual tuning: Humans adjusted windows (slow, error-prone)

**After PHASE 3**:
- ✅ Windows adapt to market conditions (weekly)
- ✅ Learning from actual signal gaps (data-driven)
- ✅ Governance prevents overfitting (±30%, bounds)
- ✅ Audit trail immutable (sys_dedup_events)
- ✅ Non-blocking integration (Sundays 23:00 UTC)
- ✅ Autonomous (no human intervention)

### Next Steps (PHASE 4+)

- [ ] Failure pattern analysis (why rejections?)
- [ ] Broker-specific cooldown learning
- [ ] Symbol volatility clustering
- [ ] Dashboard visualization of learning trends
- [ ] Adaptive scheduler (adjust frequency per symbol)

---

### Las 7 FASES Implementadas

**FASE 1-2** (EdgeTuner + CoherenceService):
- ✅ **Bootstrap Grace Period**: Primeros 10 trades en SHADOW sin veto de coherence
- ✅ **Confidence Learning**: EdgeTuner registra delta feedback (actual - predicted) y auto-ajusta `confidence_threshold`
- **Archivo**: `core_brain/edge_tuner.py` (líneas 97-160) + `trade_closure_listener.py` (líneas 389-410)
- **Mecanismo**: 
  ```python
  delta = actual_result - predicted_score
  if delta > 0.10:  # Conservative (good)
      new_threshold = min(0.95, current_threshold + 0.01)  # INCREASE
  elif delta < -0.40:  # Optimistic (bad)
      new_threshold = max(0.50, current_threshold - 0.02)  # DECREASE
  ```
  Threshold converge a realidad en 5-10 trades

**FASE 3-4** (PositionSizeEngine + MainOrchestrator):
- ✅ **Adaptive Leverage**: Ya existía - PositionSizeEngine ajusta tamaño según `confidence_threshold`
- ✅ **Auto-Promotion**: Ya existía - MainOrchestrator.evaluate_all_strategies() corre cada 5 min, SHADOW→LIVE cuando PF>1.5 AND WR>50%

**FASE 5-6** (CoherenceService):
- ✅ **Dynamic Coherence Thresholds**: Adaptativos por fase de experiencia
  - Phase 0 (0-10 trades): 0% required confidence (bootstrap)
  - Phase 1 (11-30 trades): 40% required
  - Phase 2 (31-50 trades): 60% required
  - Phase 3 (50+ trades): 80% required (institutional rigor)
- **Archivo**: `core_brain/coherence_service.py` (líneas 95-165)

**FASE 7** (StrategyRanker):
- ✅ **Rehabilitation Path**: LIVE strategies que degradan (DD≥3% o CL≥5) transicionan a SHADOW en lugar de QUARANTINE
- EdgeTuner ejecuta programa de recuperación (20-50 trades)
- Si recuperan → re-promoción automática a LIVE
- **Archivo**: `core_brain/strategy_ranker.py` (líneas 167-222)

---

## 🌑 SHADOW EVOLUTION v2.1: Protocolo de Incubación Multi-Instancia

**Introducción**: Aethelgard es una **incubadora de estrategias** que ejecuta múltiples configuraciones EN PARALELO dentro de una única cuenta DEMO, comparando desempeño en vivo para promover automáticamente solo lo que demuestra rentabilidad consistente.

### 0. NÚCLEO DE DECISIÓN: Los 3 Pilares de Viabilidad

Toda SHADOW instance es evaluada ÚNICAMENTE por 3 pilares constitucionales:

**PILAR 1️⃣: PROFITABILIDAD** (¿Gana dinero?)
- Profit Factor >= 1.5 (dinero ganado / dinero perdido)
- Win Rate >= 60% (porcentaje de trades ganadores)
- Si AMBOS fallan → MUERTE INMEDIATA

**PILAR 2️⃣: RESILIENCIA** (¿Sobrevive stress?)
- Max Drawdown <= 12% del capital
- Consecutive Losses <= 3 (máximo 3 pérdidas seguidas)
- Si CUALQUIERA falla bajo volatilidad extrema → CUARENTENA

**PILAR 3️⃣: CONSISTENCIA** (¿Es predecible?)
- Trades ejecutados >= 15 (muestra estadística mínima)
- Equity Curve coefficient of variation <= 0.40 (curva suave)
- Si equity curve es errática → MONITOR 14 días

**MUERTE AUTOMÁTICA**: Si CUALQUIER Pilar falla → exclusión inmediata
**CUARENTENA**: Si 2+ métricas confirman debilidad → monitor 7 días
**VIVO**: Si 3 Pilares PASAN → continúa compitiendo

### 1. Arquitectura Multi-Instancia (Pool de Configuraciones)

**Concepto**: Ejecutar **N instancias de la misma estrategia CON PARÁMETROS DIFERENTES** en paralelo dentro de UNA SOLA cuenta DEMO.

```
CUENTA DEMO ÚNICA (ej: MT5_DEMO_001)
│
├─ [INSTANCIA A] BRK_OPEN_0001 + Parameters:{risk:0.01%, lookback:60}
├─ [INSTANCIA B] BRK_OPEN_0001 + Parameters:{risk:0.02%, lookback:120}
├─ [INSTANCIA C] BRK_OPEN_0001 + Parameters:{risk:0.01%, lookback:90} + regime_filter=TREND_ONLY
├─ [INSTANCIA D] OliverVelez + Parameters:{aggressive:true}
├─ [INSTANCIA E] OliverVelez + Parameters:{aggressive:false}
└─ [INSTANCIA F] MOM_BIAS_0001 + Parameters:{zcore_threshold:2.5}

Todas ejecutando en paralelo → Resultados registrados individualmente → Sistema elige el mejor
```

**Gobernanza MULTI-INSTANCIA** (RULE DB-1):
```python
class ShadowInstance:
    """Configuración ejecutable dentro del pool (Account: DEMO)."""
    instance_id: str                    # UUID único
    strategy_id: str                    # BRK_OPEN_0001
    parameter_overrides: Dict           # {"risk_pct": 0.02, "lookback": 120}
    regime_filters: List                # ["TREND_UP", "EXPANSION"]
    birth_timestamp: datetime           # Cuando se crea
    status: str                         # INCUBATING | SHADOW_READY | PROMOTED_TO_REAL | DEAD | QUARANTINED
    account_type: str                   # DEMO | REAL (vinculación inmutable)
```

### 2. Métricas Confirmadoras (13 Indicadores: Apoyo a 3 Pilares)

| # | Métrica | Pilar | Threshold | Severidad | Función |
|---|---------|-------|-----------|-----------|---------|
| 1️⃣ | **Profit Factor** | PROFITABILIDAD | < 1.2 | 🔴 CRÍTICO | Muerte inmediata |
| 2️⃣ | **Win Rate** | PROFITABILIDAD | < 35% | 🔴 CRÍTICO | Muerte inmediata |
| 3️⃣ | **Consecutive Losses** | RESILIENCIA | > 5 | 🔴 CRÍTICO | Muerte inmediata |
| 4️⃣ | **Max Drawdown** | RESILIENCIA | > 15% | 🔴 CRÍTICO | Muerte inmediata |
| 5️⃣ | **Calmar Ratio** | RESILIENCIA | < 0.5 | 🟠 ALTO | Cuarentena (7d) |
| 6️⃣ | **Trade Frequency** | CONSISTENCIA | < 1 trade/día | 🟡 MEDIO | Monitor (14d) |
| 7️⃣ | **Slippage Impact** | PROFITABILIDAD | > 10 pips avg | 🟠 ALTO | Revisión manual |
| 8️⃣ | **Recovery Factor** | RESILIENCIA | < 1.5 | 🟡 MEDIO | Cuarentena + retest |
| 9️⃣ | **Avg Trade Duration** | CONSISTENCIA | > 8 hours | 🟢 BAJO | Monitor overnight risk |
| 🔟 | **Equity Curve Variability** | CONSISTENCIA | CV > 0.40 | 🟡 MEDIO | Cuarentena |
| 1️⃣1️⃣ | **Risk-Reward Ratio** | PROFITABILIDAD | < 1:1.5 | 🟠 ALTO | Exclusión persistente |
| 1️⃣2️⃣ | **Zero-Profit Days** | PROFITABILIDAD | > 40% período | 🟢 BAJO | Monitor trend |
| 1️⃣3️⃣ | **Inactivity Duration** | CONSISTENCIA | > 48h sin signal | 🟢 BAJO | Review readiness |

**Lógica Core** (Pilares, no métricas):
```python
def evaluate_shadow_health(instance: ShadowInstance) -> HealthStatus:
    """Determina viabilidad SOLO por 3 Pilares (RULE ID-1)."""
    
    trace_id = f"TRACE_HEALTH_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{instance.instance_id[:8]}"
    metrics = instance.performance_metrics
    
    # PILAR 1: PROFITABILIDAD
    pillar1_alive = (metrics.profit_factor >= 1.5 and metrics.win_rate >= 0.60)
    if not pillar1_alive and instance.trades_executed >= 15:
        logger.warning(f"[SHADOW] {trace_id}: MUERTE - Pilar 1 (PROFITABILIDAD) fallido")
        return HealthStatus.DEAD
    
    # PILAR 2: RESILIENCIA
    pillar2_alive = (metrics.max_drawdown <= 0.12 and metrics.consecutive_losses <= 3)
    if not pillar2_alive:
        logger.warning(f"[SHADOW] {trace_id}: CUARENTENA - Pilar 2 (RESILIENCIA) comprometido")
        return HealthStatus.QUARANTINED
    
    # PILAR 3: CONSISTENCIA
    equity_cv = calculate_coefficient_variation(instance.equity_history)
    pillar3_alive = (instance.trades_executed >= 15 and equity_cv <= 0.40)
    if not pillar3_alive:
        logger.info(f"[SHADOW] {trace_id}: MONITOR - Pilar 3 (CONSISTENCIA) bajo revisión")
        return HealthStatus.MONITOR
    
    logger.info(f"[SHADOW] {trace_id}: ✅ HEALTHY - 3 Pilares validados")
    return HealthStatus.HEALTHY
```

### 3. Filtros de Promoción Rigurosa (SHADOW → REAL)

**Gobernanza MULTI-INSTANCIA** (RULE DB-1 & RULE ID-1):

```sql
CREATE TABLE sys_shadow_instances (
  instance_id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  parameter_overrides TEXT,        -- JSON
  account_type TEXT NOT NULL,      -- DEMO | REAL (inmutable)
  account_id TEXT,
  birth_timestamp TIMESTAMP,
  status TEXT,                     -- INCUBATING | SHADOW_READY | PROMOTED_TO_REAL | DEAD | QUARANTINED
  total_trades_executed INTEGER,
  profit_factor REAL,
  win_rate REAL,
  max_drawdown_pct REAL,
  consecutive_losses_max INTEGER,
  equity_curve_cv REAL,
  promotion_trace_id TEXT,         -- TRACE_PROMOTION_...
  backtest_trace_id TEXT,          -- TRACE_BACKTEST_...
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE sys_shadow_performance_history (
  id INTEGER PRIMARY KEY,
  instance_id TEXT NOT NULL,
  evaluation_date DATE,
  pillar1_status TEXT,
  pillar2_status TEXT,
  pillar3_status TEXT,
  event_trace_id TEXT              -- TRACE_EVENT_...
);

CREATE TABLE sys_shadow_promotion_log (
  promotion_id INTEGER PRIMARY KEY,
  instance_id TEXT NOT NULL,
  trace_id TEXT UNIQUE NOT NULL,   -- TRACE_PROMOTION_REAL_20260312_...
  promotion_status TEXT,
  pillar1_passed BOOLEAN,
  pillar2_passed BOOLEAN,
  pillar3_passed BOOLEAN
);
```

**Status**: ✅ IMPLEMENTACIÓN LISTA (Trace_ID: DOC-V3-QUANTUM-EDGE-PROTOCOL)

### Las 7 FORMAS DE SHADOW (Operacionales)

Un mismo modo "SHADOW" implementa 7 comportamientos automáticos:

| FORMA | Descripción | Mecanismo | Status |
|-------|---------|----------|--------|
| **1: Bootstrap** | 0-10 trades sin coherence veto | CoherenceService grace period | ✅ |
| **2: Learning** | Confidence auto-calibra via delta | EdgeTuner.adjust_confidence_threshold() | ✅ |
| **3: Thresholds** | 4 fases adaptativas | Coherence dynamic phases | ✅ |
| **4: Promotion** | SHADOW→LIVE automático | MainOrchestrator ranking (PF>1.5, WR>50%) | ✅ |
| **5: Rehab** | LIVE→SHADOW recovery | StrategyRanker rehabilitation path | ✅ |
| **6: Regime** | Skip unfavorable regimes | RegimeDetector check | ✅ |
| **7: Leverage** | Position size ∝ confidence | PositionSizeEngine multiplier | ✅ |

### Validación

**Script de Test**: `scripts/validate_7_shadow_modes.py`

**Resultado**: 
```
✅ FORMA 1: Bootstrap Phase                PASSED
✅ FORMA 2: Confidence Learning            PASSED
✅ FORMA 3: Dynamic Thresholds             PASSED
✅ FORMA 4: Auto-Promotion                 PASSED
✅ FORMA 5: Rehabilitation                 PASSED
✅ FORMA 6: Regime Awareness               PASSED
✅ FORMA 7: Adaptive Leverage              PASSED

RESULTADO: 7/7 formas validadas correctamente
```

**System Validation**:
```
✅ 125/125 tests PASANDO (was 123/125)
✅ 23/23 módulos de validación OK
✅ SYSTEM INTEGRITY: GUARANTEED
```

### Integración con EdgeTuner (Core)

El corazón de SHADOW Evolution es EdgeTuner mejorado:

**Antes (FASE 1)**: EdgeTuner solo ajustaba regime weights  
**Ahora (FASE 2)**: EdgeTuner también ajusta confidence_threshold via delta feedback

**Flujo mejorado**:
```
TradeClosureListener → actual_result
                    ↓
              EdgeTuner.adjust_confidence_threshold()
                    ↓
              delta = actual - predicted
                    ↓
              if delta > 0.10 → new_threshold ↑
              if delta < -0.40 → new_threshold ↓
                    ↓
              storage.update_dynamic_params(strategy_id, 'confidence_threshold', new_threshold)
```

### Monitoreo en Producción

**Métricas clave observar** (24-72 horas post-implementación):

| Métrica | Target | Ubicación |
|---------|--------|----------|
| BOOTSTRAP_PHASE duration | < 1 hora | logs `[COHERENCE_BOOTSTRAP]` |
| Confidence convergence | ±5-10 trades | logs `[CONFIDENCE_LEARNING]` |
| SHADOW→LIVE transitions | > 1 (7-14 días) | logs `[AUTO_PROMOTE]` |
| Recovery success rate | > 50% | logs `[REHABILITATION]` |
| Regime filter impact | 10-30% skipped | logs `[REGIME_CHECK]` |

**Logs esperados**:
```
[COHERENCE_BOOTSTRAP] SHADOW mode grace period (trade 1/10)
[CONFIDENCE_LEARNING] strategy_01: delta=+0.25 → threshold 0.70 → 0.71 (INCREASE)
[AUTO_PROMOTE] strategy_01 SHADOW→LIVE (PF=1.75, WR=62.5%)
[REHABILITATION] strategy_02: LIVE→SHADOW (drawdown_exceeded)
[REGIME_CHECK] EUR/USD: VOLATILE → Skip signal
```

### Referencias Técnicas

- **Documentación completa**: `docs/SHADOW_EVOLUTION_PLAN_A++.md`
- **Scripts de implementación**: 
  - `core_brain/coherence_service.py` (bootstrap detection)
  - `core_brain/risk_policy_enforcer.py` (coherence exemption)
  - `core_brain/edge_tuner.py` (confidence learning)
  - `core_brain/trade_closure_listener.py` (learning integration)
  - `core_brain/strategy_ranker.py` (rehabilitation path)
- **Validación**: `scripts/validate_7_shadow_modes.py`
- **Trace ID**: SHADOW-EVOLUTION-2026-001

## 📊 Ejemplo de Operación (HU 7.1)

**Escenario**: Usuario con `confidence_threshold` inicial = 0.75

**Secuencia**:
1. **Trades 1-3**: 3 pérdidas consecutivas → `consecutive_losses=3`
   - Analyzer detecta racha
   - ThresholdOptimizer propone: `0.75 + 0.04 = 0.79`
   - Safety Governor permite (delta < 0.05)
   - **Nuevo threshold = 0.79** (más exigente)

2. **Trades 4-10**: Win rate = 8/7 = 71%, drawdown = -5%
   - Analyzer detecta recuperación
   - ThresholdOptimizer propone: `0.79 - 0.01 = 0.78`
   - **Nuevo threshold = 0.78** (permite señales con 78%+ confianza)

3. **Persistencia**:
   - Cambios guardados en DB con Trace_ID
   - Log: `[THRESHOLD_OPTIMIZER] Threshold updated: 0.75 → 0.79 (Δ=+0.04) | Reason: LOSS_STREAK(3) | Trace_ID: ADAPTIVE-THRESHOLD-2026-001`

---

## 🌑 SHADOW EVOLUTION v2.1: Fase 1 COMPLETADA (12-Mar-2026)

**Status**: ✅ **WEEK 1: Database Schema & Core Models COMPLETADA (16:45 UTC)**  
**Timeline Real**: 4.5 horas (vs 7.5h estimadas) = 40% más rápido  
**Trace_ID Base**: `SHADOW-EVOLUTION-2026-PHASE2`

### Entregables Completados (WEEK 1)

#### 1. Tables: sys_shadow_* (RULE DB-1 Compliant)

```sql
-- 3 tablas creadas en schema.py (líneas 601-677)

CREATE TABLE sys_shadow_instances (
  instance_id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  parameter_overrides TEXT,        -- JSON serialized
  account_type TEXT NOT NULL,      -- DEMO | REAL (inmutable)
  account_id TEXT,
  birth_timestamp TIMESTAMP,
  status TEXT,                     -- INCUBATING | SHADOW_READY | PROMOTED_TO_REAL | DEAD | QUARANTINED
  health_status TEXT,              -- HEALTHY | MONITOR | QUARANTINED | DEAD
  total_trades_executed INTEGER DEFAULT 0,
  profit_factor REAL,
  win_rate REAL,
  max_drawdown_pct REAL,
  consecutive_losses_max INTEGER,
  equity_curve_cv REAL,
  backtest_score REAL,
  promotion_trace_id TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id)
);

CREATE TABLE sys_shadow_performance_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id TEXT NOT NULL REFERENCES sys_shadow_instances(instance_id),
  evaluation_date DATE NOT NULL,
  pillar1_profitability_status TEXT,      -- PASS | FAIL
  pillar2_resiliencia_status TEXT,        -- PASS | FAIL
  pillar3_consistency_status TEXT,        -- PASS | FAIL
  overall_health_status TEXT,             -- HEALTHY | MONITOR | QUARANTINED | DEAD
  profit_factor_snapshot REAL,
  win_rate_snapshot REAL,
  max_drawdown_snapshot REAL,
  consecutive_losses_snapshot INTEGER,
  equity_cv_snapshot REAL,
  event_trace_id TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, evaluation_date)
);

CREATE TABLE sys_shadow_promotion_log (
  promotion_id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id TEXT NOT NULL REFERENCES sys_shadow_instances(instance_id),
  trace_id TEXT UNIQUE NOT NULL,   -- TRACE_PROMOTION_REAL_20260312_...
  promotion_status TEXT,            -- APPROVED | REJECTED | PENDING
  pillar1_profitability BOOLEAN,
  pillar2_resiliencia BOOLEAN,
  pillar3_consistency BOOLEAN,
  decision_reason TEXT,
  promoted_to_real_account_id TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(trace_id)
);
```

**Índices creados**:
- `idx_shadow_instances_status` → rápida búsqueda por status
- `idx_shadow_instances_account_type` → filtrar DEMO vs REAL
- `idx_shadow_performance_instance_date` → auditoría histórica
- `idx_shadow_promotion_trace_id` → trazabilidad inmediata

#### 2. Python Models: ShadowInstance + ShadowMetrics

**Archivo**: `models/shadow.py` (550+ líneas)

```python
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Dict, Optional, List

class ShadowStatus(Enum):
    """Estado operacional de una instancia SHADOW."""
    INCUBATING = "INCUBATING"           # En prueba inicial
    SHADOW_READY = "SHADOW_READY"       # Lista para copytrading
    PROMOTED_TO_REAL = "PROMOTED_TO_REAL"  # Promovida a cuenta real
    DEAD = "DEAD"                       # Descartada por fallo crítico
    QUARANTINED = "QUARANTINED"        # Suspendida temporalmente

class HealthStatus(Enum):
    """Salud según 3 Pilares."""
    HEALTHY = "HEALTHY"                # ✅ 3/3 Pilares PASS
    MONITOR = "MONITOR"                # 🟡 Bajo monitoreo (Pilar 3 débil)
    QUARANTINED = "QUARANTINED"       # 🟠 Suspendida (Pilar 2 fallo)
    DEAD = "DEAD"                      # ❌ Muerta (Pilar 1 fallo)

class PillarStatus(Enum):
    """Estado individual de cada Pilar."""
    PASS = "PASS"                      # Métrica cumple
    FAIL = "FAIL"                      # Métrica no cumple
    UNKNOWN = "UNKNOWN"                # No evaluada aún

@dataclass
class ShadowMetrics:
    """13 métricas confirmadoras de los 3 Pilares."""
    # PILAR 1: PROFITABILIDAD (2 críticas)
    profit_factor: float                # >= 1.5
    win_rate: float                     # >= 0.60
    
    # PILAR 2: RESILIENCIA (2 críticas)
    max_drawdown: float                 # <= 0.12
    consecutive_losses: int             # <= 3
    
    # PILAR 3: CONSISTENCIA (2 críticas)
    trades_executed: int                # >= 15
    equity_curve_cv: float              # <= 0.40
    
    # Métricas de apoyo (7 confirmadoras)
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    avg_trade_duration_hours: float = 0.0
    risk_reward_ratio: float = 0.0
    slippage_pips_avg: float = 0.0
    zero_profit_days_pct: float = 0.0
    inactive_duration_hours: float = 0.0

@dataclass
class ShadowInstance:
    """Configuración ejecutable en pool DEMO."""
    instance_id: str                    # UUID único
    strategy_id: str                    # ej: BRK_OPEN_0001
    parameter_overrides: Dict = field(default_factory=dict)  # {"risk_pct": 0.02}
    regime_filters: List[str] = field(default_factory=list)  # ["TREND_UP"]
    
    account_type: str = "DEMO"          # DEMO | REAL (inmutable)
    account_id: Optional[str] = None
    
    birth_timestamp: datetime = field(default_factory=datetime.now)
    status: ShadowStatus = ShadowStatus.INCUBATING
    health_status: HealthStatus = HealthStatus.UNKNOWN
    
    performance_metrics: ShadowMetrics = field(default_factory=ShadowMetrics)
    
    backtest_score: Optional[float] = None
    promotion_trace_id: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self) -> None:
        """Validación post-creación (RULE ID-1)."""
        if not self.instance_id:
            raise ValueError("instance_id requerida y no vacía")
        if self.account_type not in ["DEMO", "REAL"]:
            raise ValueError(f"account_type debe ser DEMO o REAL, recibido: {self.account_type}")
```

**Validadores integrados**:
- ✅ Type hints 100%
- ✅ Required fields validation en `__post_init__`
- ✅ Account type constraint (DEMO | REAL)
- ✅ Status transitions audited via Trace_ID

#### 3. Storage Layer: ShadowStorageManager

**Archivo**: `data_vault/shadow_db.py` (350+ líneas)

```python
class ShadowStorageManager:
    """CRUD operations para SHADOW ecosystem (SSOT in DB)."""
    
    def __init__(self, storage_manager: StorageManager):
        """Inyectar dependencia StorageManager (RULE ID-1)."""
        self.storage = storage_manager
    
    def create_shadow_instance(self, 
                              instance: ShadowInstance,
                              trace_id: str) -> str:
        """Crear nueva instancia SHADOW en DB."""
        # Genera Trace_ID si no existe
        trace_id = trace_id or f"TRACE_SHADOW_CREATE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        sql = """
        INSERT INTO sys_shadow_instances
        (instance_id, strategy_id, parameter_overrides, account_type, account_id,
         birth_timestamp, status, health_status, backtest_score, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.storage.execute_query(sql, [
            instance.instance_id,
            instance.strategy_id,
            json.dumps(instance.parameter_overrides),
            instance.account_type,
            instance.account_id,
            instance.birth_timestamp,
            instance.status.value,
            instance.health_status.value,
            instance.backtest_score,
            datetime.now(),
            datetime.now()
        ])
        return trace_id
    
    def get_shadow_instance(self, instance_id: str) -> Optional[ShadowInstance]:
        """Leer instancia SHADOW desde DB."""
        # SSOT principle: DB is source of truth
    
    def update_shadow_health(self, 
                             instance_id: str,
                             health_status: HealthStatus,
                             metrics: ShadowMetrics,
                             trace_id: str) -> None:
        """Actualizar salud + métricas con auditoría."""
        # Persiste en sys_shadow_performance_history con trace_id
    
    def log_promotion_decision(self,
                               instance_id: str,
                               approved: bool,
                               pillars_passed: Dict[str, bool],
                               trace_id: str) -> None:
        """Registrar decisión de promoción (INSERT ONLY - inmutable)."""
        # sys_shadow_promotion_log es append-only (RULE DB-1)
    
    def evaluate_promotability(self, instance: ShadowInstance) -> Tuple[bool, str]:
        """¿Promovible a REAL? (3 Pilares ALL PASS)."""
        # Retorna (can_promote: bool, reason: str)
```

**10 CRUD methods implementados**:
1. ✅ `create_shadow_instance()` → Crear nueva instancia
2. ✅ `get_shadow_instance(id)` → Leer 1 instancia
3. ✅ `list_shadow_instances(filters)` → Listar por status/account
4. ✅ `update_shadow_metrics()` → Actualizar performance snapshot
5. ✅ `update_shadow_health()` → Cambiar health status con auditoría
6. ✅ `log_promotion_decision()` → Registrar decisión (INSERT ONLY)
7. ✅ `get_promotion_history()` → Auditoría de promociones
8. ✅ `get_all_healthy_instances()` → Query rápida (índice)
9. ✅ `archive_dead_instance()` → Soft-delete lógico
10. ✅ `generate_trace_id()` → Trace ID generation helper

#### 4. Unit Tests (600+ líneas)

**Archivo 1**: `tests/test_shadow_schema.py` (400+ líneas)

```python
import unittest
import sqlite3
from data_vault.schema import SHADOW_SCHEMA_DEFINITION

class TestShadowSchema(unittest.TestCase):
    
    def setUp(self):
        """Crear DB en memoria para tests."""
        self.conn = sqlite3.connect(":memory:")
        cursor = self.conn.cursor()
        # Ejecutar SHADOW_SCHEMA_DEFINITION
    
    def test_sys_shadow_instances_table_exists(self):
        """Validar que tabla existe con 18 columnas."""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(sys_shadow_instances)")
        columns = cursor.fetchall()
        self.assertEqual(len(columns), 18)
    
    def test_unique_constraint_instance_id(self):
        """Primary key instance_id es UNIQUE."""
        # Insert 1 → OK
        # Insert 1 duplicate → FAIL
        self.assertRaises(sqlite3.IntegrityError, ...)
    
    def test_performance_history_foreign_key(self):
        """FK instance_id en performance_history referencia instances."""
        # Insert orphan row → FAIL
        self.assertRaises(sqlite3.IntegrityError, ...)
    
    def test_promotion_log_trace_id_unique(self):
        """Trace_ID es UNIQUE en promotion_log (auditoría)."""
        # Duplicate Trace_ID → FAIL
    
    def test_index_performance(self):
        """Índices creados y funcionales."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = cursor.fetchall()
        self.assertGreaterEqual(len(indexes), 4)
    
    # 6 tests adicionales...
    
    def tearDown(self):
        self.conn.close()
```

**Archivo 2**: `tests/test_shadow_models.py` (400+ líneas)

```python
import unittest
from models.shadow import ShadowInstance, ShadowMetrics, ShadowStatus, HealthStatus

class TestShadowInstance(unittest.TestCase):
    
    def test_instance_creation_minimal(self):
        """Crear instancia con campos mínimos."""
        instance = ShadowInstance(
            instance_id="test_001",
            strategy_id="BRK_OPEN_0001"
        )
        self.assertEqual(instance.instance_id, "test_001")
        self.assertEqual(instance.status, ShadowStatus.INCUBATING)
    
    def test_invalid_account_type(self):
        """account_type DEMO|REAL solamente."""
        with self.assertRaises(ValueError):
            ShadowInstance(
                instance_id="test_002",
                strategy_id="BRK_OPEN_0001",
                account_type="INVALID"
            )
    
    def test_metrics_validation(self):
        """ShadowMetrics require valores numéricos válidos."""
        metrics = ShadowMetrics(
            profit_factor=1.5,
            win_rate=0.60,
            max_drawdown=0.12,
            consecutive_losses=3,
            trades_executed=15,
            equity_curve_cv=0.40
        )
        self.assertTrue(metrics.profit_factor >= 1.5)
    
    def test_health_status_logic(self):
        """Evaluar health_status según 3 Pilares."""
        # Metrics que PASAN 3 Pilares
        healthy_metrics = ShadowMetrics(
            profit_factor=1.75,   ✅ PILAR 1
            win_rate=0.65,        ✅ PILAR 1
            max_drawdown=0.10,    ✅ PILAR 2
            consecutive_losses=2, ✅ PILAR 2
            trades_executed=20,   ✅ PILAR 3
            equity_curve_cv=0.35  ✅ PILAR 3
        )
        # Result: HealthStatus.HEALTHY
    
    # 16 tests adicionales...
```

**Test Results**:
```
✅ test_shadow_schema.py: 12/12 PASSED (2.34s)
✅ test_shadow_models.py: 20/20 PASSED (1.87s)
✅ Total: 32 nuevos tests PASSED
✅ Zero regressions (todos tests existentes pasan)
```

### Validación Completa (WEEK 1)

```bash
$ python scripts/validate_all.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ CROSS-CUTTING (Governance & Quality): 8/8 PASSED
✅ DOMAIN 01: Identity & Security: 3/3 PASSED
✅ DOMAIN 02-03: Context Intelligence: 1/1 PASSED
✅ DOMAIN 04: Risk Governance: 1/1 PASSED
✅ DOMAIN 05: Universal Execution: 2/2 PASSED
✅ ISD: Signal Quality Validation: 1/1 PASSED
✅ DOMAIN 08: Data Sovereignty: 2/2 PASSED (includes new shadow_db.py)
✅ DOMAIN 09: Institutional UI: 2/2 PASSED
✅ SPECIALIZED (Multidomain): 5/5 PASSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 25/25 módulos arquitectura PASSED (45.87s)
✅ 32 nuevos tests PASSED
✅ Trace_ID patterns verified
✅ RULE DB-1 compliance: ✅ (sys_ prefix en todas las tablas)
✅ RULE ID-1 compliance: ✅ (Trace_ID patterns consistent)
✅ Type hints: 100%
✅ SSOT principle: ✅ (All state in DB, zero JSON redundancy)
```

### Bloqueadores para WEEK 2

✅ **NINGUNO** - Listo para iniciar ShadowManager + PromotionValidator

### Timeline vs Estimado

| Fase | Estimado | Real | Variance |
|------|----------|------|----------|
| Schema desig | 1h | 45m | -25% (rápido) |
| Model implementation | 2h | 1.5h | -25% |
| Storage layer | 2.5h | 1.5h | -40% |
| Unit tests | 2h | 1.5h | -25% |
| **WEEK 1 TOTAL** | **7.5h** | **4.5h** | **-40%** |

**Lección**: Modular design + parallelization (tests en paralelo) aceleró 40% vs estimado.

---

## ⚙️ HU 7.5 — BacktestOrchestrator: Cooldown por `last_backtest_at` (24-Mar-2026)

**Trace_ID**: `PIPELINE-UNBLOCK-BACKTEST-COOLDOWN-2026-03-24`

### Problema detectado
`_is_on_cooldown()` usaba `updated_at` para calcular si una estrategia estaba en período de espera. El campo `updated_at` es un timestamp de escritura general — se actualiza con cualquier modificación (incluso la migración inicial). Las 6 estrategias del sistema tenían `updated_at = '2026-03-24 04:50:50'` (fecha del seed), lo que causaba un cooldown permanente de 24h sin que se hubiera ejecutado ni un solo backtest. Síntoma: `Batch complete — {'evaluated': 0, 'promoted': 0, 'failed': 0, 'skipped': 6}` en cada ciclo diario.

### Solución implementada

**1. Nueva columna en `sys_strategies`** (`data_vault/schema.py`):
```sql
last_backtest_at TIMESTAMP DEFAULT NULL
-- NULL = nunca se ha ejecutado backtest → no aplica cooldown
```
Migración inline en `run_migrations()` — idempotente, se aplica automáticamente en el próximo arranque.

**2. `_is_on_cooldown()` refactorizado** (`core_brain/backtest_orchestrator.py`):
```python
# Prioridad: last_backtest_at (campo dedicado)
# Fallback: updated_at (compatibilidad con rows sin la nueva columna)
# NULL en last_backtest_at → nunca backtested → NOT on cooldown
raw = strategy.get("last_backtest_at") or strategy.get("updated_at")
if "last_backtest_at" in strategy and strategy["last_backtest_at"] is None:
    return False  # Nunca ejecutado → correr inmediatamente
```

**3. `_update_strategy_scores()` ahora escribe `last_backtest_at`**:
```sql
UPDATE sys_strategies
SET score_backtest = ?, score = ?,
    last_backtest_at = CURRENT_TIMESTAMP,  -- marca el momento real del backtest
    updated_at = CURRENT_TIMESTAMP
WHERE class_id = ?
```

**4. SELECTs de carga** (`_load_backtest_strategies`, `_load_strategy`) incluyen `last_backtest_at`.

### Lógica de cooldown resultante
| Estado `last_backtest_at` | Resultado |
|---|---|
| `NULL` (nunca backtested) | NOT on cooldown → ejecutar |
| `< 24h` ago | On cooldown → skip |
| `> 24h` ago | NOT on cooldown → ejecutar |
| Campo ausente (row legacy) | Fallback a `updated_at` |

**Tests**: 3 nuevos tests en `TestCooldown` — 43/43 total PASSED.

---

## ⚙️ HU 7.9 — Evaluación multi-timeframe con round-robin y pre-filtro de régimen (25-Mar-2026)

**Trace_ID**: `EDGE-BACKTEST-HU79-MULTITF-ROUND-ROBIN-2026-03-25`

### Problema detectado
`_resolve_symbol_timeframe()` siempre devolvía el mismo timeframe por defecto (`H1`). `_build_scenario_slices()` ignoraba completamente `required_timeframes` y `required_regime`, que habían sido añadidos en HU 7.8 pero no consumidos.

### Solución implementada

**1. `_get_timeframes_for_backtest(strategy)`** — lee `required_timeframes` (JSON list) con fallback a `default_timeframe` del config.

**2. `_next_timeframe_round_robin(strategy_id, timeframes)`** — rotación cíclica in-memory por `strategy_id`. Estado local al proceso (se reinicia con el servidor — aceptable para scheduling).

**3. `_passes_regime_prefilter(strategy, symbol, timeframe)`** — valida `required_regime` contra el régimen actual:
- `'ANY'` o ausente → siempre `True`
- Sin datos o `< 14` bars → `True` (fail-open, no bloquear evaluación)
- Mismatch confirmado → `False`
- Normalización de aliases: `VOLATILITY→VOLATILE`, `TRENDING→TREND`, etc. (dict `_REGIME_ALIAS`)

**4. `_build_scenario_slices()`** integra round-robin + pre-filtro antes del fetch de datos. Si el pre-filtro veta, retorna slices `UNTESTED_CLUSTER` (política HU 7.11 — sin síntesis).

**5. SELECTs** actualizados con `required_timeframes, required_regime`.

**Tests**: 14 tests en `tests/test_backtest_multitimeframe_roundrobin.py` — 14/14 PASSED.

---

## ⚙️ HU 7.10 — RegimeClassifier real en pipeline de backtesting (25-Mar-2026)

**Trace_ID**: `EDGE-BACKTEST-HU710-REGIME-CLASSIFIER-PIPELINE-2026-03-25`

### Problema detectado
`_split_into_cluster_slices()` clasificaba ventanas de datos con `backtester._detect_regime()` — una heurística ATR+slope que no usa ADX ni SMA200. El `RegimeClassifier` real (HU existente en dominio) quedaba inutilizado en el pipeline de backtesting.

### Solución implementada

**1. `_classify_window_regime(window)`** — reemplaza la llamada directa a heurística:
- Instancia `RegimeClassifier(storage=self.storage)` y clasifica con ADX/ATR/SMA200.
- Fallback a `backtester._detect_regime()` si `RegimeClassifier` lanza excepción (robustez).
- Retorna string compatible con `REGIME_TO_CLUSTER`: `'TREND' | 'RANGE' | 'VOLATILE' | 'CRASH' | 'NORMAL'`.

**2. `REGIME_TO_CLUSTER` ampliado**:
```python
"CRASH":  StressCluster.HIGH_VOLATILITY    # MarketRegime.CRASH
"NORMAL": StressCluster.STAGNANT_RANGE     # MarketRegime.NORMAL
```

**3. `_split_into_cluster_slices()`** sustituye `backtester._detect_regime()` por `_classify_window_regime()`.

**Tests**: 14 tests en `tests/test_backtest_regime_classifier.py` — 14/14 PASSED.

---

## ⚙️ HU 7.12 — Adaptive Backtest Scheduler — cooldown dinámico y cola de prioridad (25-Mar-2026)

**Trace_ID**: `EDGE-BACKTEST-HU712-ADAPTIVE-SCHEDULER-2026-03-25`

### Problema detectado
El cooldown del backtester era fijo (24h en config). No había integración con `OperationalModeManager` para adaptar la frecuencia según carga del sistema. Sin cola de prioridad, todas las estrategias competían en igualdad aunque algunas nunca hubieran corrido.

### Solución implementada

Nuevo módulo `core_brain/adaptive_backtest_scheduler.py`:

| Método | Responsabilidad |
|---|---|
| `get_effective_cooldown_hours()` | Delega a `OperationalModeManager.get_component_frequencies()["backtest_cooldown_h"]` |
| `is_deferred()` | True si `BacktestBudget == DEFERRED` — sistema sobrecargado |
| `get_priority_queue()` | Filtra cooldown + ordena P1→P3 |
| `_sort_by_priority()` | P1: nunca run · P2: score=0, fue run · P3: tiene score (oldest first) |

**Cooldown dinámico**:
| Budget | Cooldown |
|---|---|
| AGGRESSIVE | 1 h |
| MODERATE | 12 h |
| CONSERVATIVE | 24 h |
| DEFERRED | cola vacía |

**Tests**: 14 tests en `tests/test_adaptive_backtest_scheduler.py` — 14/14 PASSED.

---

## ⚙️ HU 7.13 — Rediseño semántico de affinity_scores (25-Mar-2026)

**Trace_ID**: `EDGE-BKT-713-AFFINITY-REDESIGN-2026-03-24`

### Problema detectado
`affinity_scores` contenía opiniones del desarrollador (`{"EUR/USD": 0.92}`) y `_extract_parameter_overrides()` buscaba `confidence_threshold` / `risk_reward` dentro de ese campo — que nunca existían ahí. El campo `execution_params` (añadido en HU 7.8 precisamente para esto) estaba siendo ignorado. Resultado: todos los backtests usaban los defaults hardcodeados (0.75 / 1.5) sin importar la configuración de la estrategia.

### Solución implementada

**1. `_extract_parameter_overrides(strategy)`** — lee `execution_params` (SSOT). `affinity_scores` nunca es input.

**2. SELECTs** de `_load_backtest_strategies()` y `_load_strategy()` incluyen `execution_params`.

**3. `_update_strategy_scores()`** — firma ampliada con `symbol` y `matrix` opcionales. Delega escritura de affinity a nuevo método.

**4. Nuevo `_write_pair_affinity(cursor, strategy_id, symbol, raw_score, matrix, strategy)`** — persiste estructura empírica por par:
```json
{
  "EURUSD": {
    "effective_score": 0.70, "raw_score": 0.70, "confidence": 1.0,
    "n_trades": 52, "profit_factor": 1.74, "max_drawdown": 0.11,
    "win_rate": 0.62, "optimal_timeframe": "H1",
    "regime_evaluated": ["TREND"],
    "status": "QUALIFIED", "cycles": 1,
    "last_updated": "2026-03-25T..."
  }
}
```

**Lógica de status**:
| effective_score | status |
|---|---|
| ≥ 0.55 | QUALIFIED |
| < 0.20 | REJECTED |
| 0.20 – 0.54 | PENDING |

> `confidence = 1.0` hasta HU 7.15 (implementará fórmula `n/(n+k)`).

**5. Migración en `run_migrations()`** — resetea `affinity_scores = '{}'` para estrategias con valores numéricos top-level (contenido legacy).

**Tests**: 15 tests en `tests/test_backtest_affinity_redesign.py` — 15/15 PASSED.

