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

## 🌑 SHADOW Evolution Integration (Plan A++)

**Fecha de Implementación**: 9 de Marzo de 2026  
**Estado**: ✅ COMPLETADO Y VALIDADO  
**Trace ID**: SHADOW-EVOLUTION-2026-001

### Problema Resuelto

**Antes**: 6 estrategias en modo SHADOW atrapadas en deadlock circular:
- CircuitBreaker bloqueaba cualquier modo ≠ 'LIVE'
- CoherenceService rechazaba señales con 0% confidence (sin trades pasados)
- Resultado: **nunca ejecutaban → nunca acumulaban trades → nunca acumulaban confidence → DEADLOCK PERMANENTE**

**Ahora**: ✅ Sistema autónomo donde estrategias SHADOW evolucionan sin intervención humana

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
