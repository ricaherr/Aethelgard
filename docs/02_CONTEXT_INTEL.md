# Dominio 02: CONTEXT_INTELLIGENCE (Regime, Multi-Scale)

## 🎯 Propósito
Proveer al sistema de una conciencia situacional superior mediante el análisis de regímenes de mercado en múltiples escalas temporales, detectando divergencias y alineaciones fractales.

## 🚀 Componentes Críticos
*   **Regime Classifier**: Motor neuronal que identifica el estado del mercado (Trend, Range, Volatile). Clasifica el contexto para filtrar estrategias según su esperanza matemática en dicho escenario.
*   **Multi-Scale Vectorizer**: Algoritmo que normaliza lecturas desde M1 hasta Daily para una visión holística.
*   **Inter-Market Scanner**: Detección de correlaciones y divergencias entre activos correlacionados.

## 📟 Configuración de Timeframes
El sistema permite el análisis fractal mediante la activación selectiva de temporalidades. La configuración se gestiona dinámicamente para optimizar la carga de CPU y la fidelidad del análisis.

| Timeframe | Uso Recomendado | Ventana de Deduplicación |
|-----------|------------------|--------------------------|
| **M1**    | Scalping Agresivo | 10 min |
| **M5**    | Scalping Moderado | 20 min |
| **M15**   | Day Trading       | 45 min |
| **H1**    | Swing Intradiario | 120 min |
| **H4**    | Swing Trading     | 480 min |
| **D1**    | Position Trading  | 1440 min |

## 🖥️ UI/UX REPRESENTATION
*   **Fractal Context Manager**: Widget central con visualización de la alineación de tendencias multi-temporal.
*   **Alpha-Sync Matrix**: Matriz de correlación dinámica con alertas de divergencia visuales.
*   **Profundidad Cognitiva**: Slider interactivo que muestra la ventana de lookback adaptativo procesada por el cerebro.

## 📈 Roadmap del Dominio
- [x] Unificación de la lógica de regímenes (antes en Alpha).
- [ ] Despliegue del scanner inter-mercado.
- [ ] Optimización de la memoria contextual adaptativa.
