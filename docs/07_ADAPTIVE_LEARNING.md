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
