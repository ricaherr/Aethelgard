# Dominio 07: ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)

## 🎯 Propósito
Cerrar el bucle de inteligencia del sistema mediante el meta-aprendizaje autónomo, ajustando parámetros operativos basados en el feedback real del mercado y la infraestructura.

## 🚀 Componentes Críticos
*   **EdgeTuner**: Motor de optimización paramétrica que calibra umbrales de confianza en tiempo real. Ajusta pesos de métricas por régimen (`regime_configs`) basándose en resultados reales (Delta Feedback).
*   **Safety Governor**: Sistema anti-overfitting que aplica reglas de suavizado y límites (Floor/Ceiling) a los ajustes automáticos.
*   **Feedback Loops**: Sistema de auditoría post-trade que vincula resultados con condiciones de micro-estructura.

## ⚙️ Funcionamiento Técnico (EdgeTuner)
**Archivo**: `core_brain/edge_tuner.py`

**Flujo Delta Feedback**:
1. Trade cierra → `TradeClosureListener` detecta el resultado.
2. `process_trade_feedback()` calcula `Delta = Resultado - Score_Predicho`.
3. Si `|Delta|` supera umbrales → `_adjust_regime_weights()` ajusta el peso dominante del régimen.
4. El resultado se persiste en `edge_learning` con `action_taken` descriptivo.

## 🛡️ Límites de Gobernanza
| Regla | Valor | Descripción |
|---|---|---|
| `GOVERNANCE_MIN_WEIGHT` | `0.10` | Floor: ningún peso puede bajar de aquí. |
| `GOVERNANCE_MAX_WEIGHT` | `0.50` | Ceiling: ningún peso puede subir de aquí. |
| `GOVERNANCE_MAX_SMOOTHING` | `0.02` | Max cambio por evento de aprendizaje (2%). |

Cuando el Governor interviene, el evento se marca con `[SAFETY_GOVERNOR]` en la base de datos.

## 🖥️ UI/UX REPRESENTATION
*   **Curva de Exigencia Algorítmica**: Visualizador dinámico de los umbrales de entrada activos vs recomendados.
*   **Edge Evolution Logs**: Feed de pensamientos del sistema sobre sus propios ajustes y calibraciones.

## 📈 Roadmap del Dominio
1.  Consolidación de la telemetría post-mortem.
2.  Automatización de umbrales en base a volatilidad.
3.  Meta-aprendizaje sobre latencia y slippage real.
