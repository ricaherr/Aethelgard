# AETHELGARD: 01 ALPHA ENGINE

## 🎯 Generación de Alpha y Estrategias
Motor de escaneo proactivo y generación de señales basadas en patrones institucionales.

---

### 🧠 Componentes Alpha
- **Scanner Proactivo**: Escaneo multi-timeframe de alta eficiencia.
- **Regime Classifier**: Clasificación de contexto (Trend, Range, Volatile).
- **Technical Analyzer**: Fuente única de verdad para indicadores vectorizados.
- **Signal Factory**: Generador de oportunidades con scoring dinámico.
- **Strategy Jury (The Jury)**: Mecanismo de decisión que evalúa la probabilidad de éxito basada en el rendimiento reciente (Darwinismo Algorítmico).

---

### 🏛️ Estrategia Universal
El sistema utiliza un **Shadow Engine** que decide si una señal merece riesgo real o seguimiento virtual, basándose en el "Shadow Performance" de la estrategia en el régimen actual.

---

### 📊 Estrategias de Ingeniería
- **Oliver Velez Swing v2**: Basada en Velas Elefante y ubicación en SMA20.
- **Multi-Timeframe Confluence**: Sistema EDGE para refuerzo de señales por alineación de temporalidades.

---

### ⚙️ Configuración Estratégica
Toda la lógica de Alpha se alimenta de parámetros dinámicos optimizados por el sistema `EdgeTuner`.

---

### 🤖 EdgeTuner — Feedback Loop Autónomo
**Archivo**: `core_brain/edge_tuner.py`

El `EdgeTuner` es el cerebro adaptativo del sistema. Ajusta pesos de métricas por régimen (`regime_configs`) y parámetros técnicos globales basándose en resultados reales de trading.

**Flujo Delta Feedback**:
1. Trade cierra → `TradeClosureListener` detecta el resultado
2. `process_trade_feedback(trade_result, predicted_score, regime)` calcula `Delta = Resultado - Score_Predicho`
3. Si `|Delta|` supera umbrales → `_adjust_regime_weights()` ajusta el peso dominante del régimen
4. El resultado se persiste en `edge_learning` con `action_taken` descriptivo

**Métodos clave**:
| Método | Propósito |
|---|---|
| `process_trade_feedback()` | Entry point del feedback loop |
| `apply_governance_limits()` | Safety Governor: aplica floor/ceiling/smoothing |
| `_adjust_regime_weights()` | Ajusta pesos en DB con governance integrado |
| `adjust_parameters()` | Ajuste paramétrico basado en win rate reciente |

---

### 🛡️ Safety Governor (Milestone 6.2)
Sistema anti-overfitting integrado en `EdgeTuner`. Aplica dos restricciones secuenciales:

| Regla | Valor | Descripción |
|---|---|---|
| `GOVERNANCE_MIN_WEIGHT` | `0.10` (10%) | Floor: ningún peso puede bajar de aquí |
| `GOVERNANCE_MAX_WEIGHT` | `0.50` (50%) | Ceiling: ningún peso puede subir de aquí |
| `GOVERNANCE_MAX_SMOOTHING` | `0.02` (2%) | Max cambio por evento de aprendizaje |

Cuando el Governor interviene, el campo `action_taken` del evento en `edge_learning` incluye el tag `[SAFETY_GOVERNOR]`, lo que activa el badge **⚡ Governor Active** en el panel `NeuralHistoryPanel` de la UI.

**Tests**: `tests/test_governance_limits.py` — **16/16 ✅**
