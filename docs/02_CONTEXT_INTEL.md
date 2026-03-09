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
- [x] Despliegue del scanner inter-mercado (ConfluenceService).
- [ ] Optimización de la memoria contextual adaptativa.

## 🛠️ Detalles de Implementación: ConfluenceService
El motor de confluencia compara activos con correlación inversa (ej. EURUSD vs DXY) o directa (ej. BTC vs ETH) para detectar divergencias de tipo SmT (Symmetric/Asymmetric Divergence).

*   **Veto por Correlación**: Si se detecta una divergencia alcista en un par con correlación inversa mientras se busca una venta, el sistema aplica un veto o aumenta el umbral de confianza requerido a 0.85.
*   **Estado Choppy**: La falta de alineación en tendencias de activos inversos activa una alerta de mercado lateral/indeciso.

## 📡 Espacio de API: Sentiment Stream Institucional (HU 3.4)
Integración activa en `core_brain/services/sentiment_service.py` bajo enfoque API-first (liviano, sin modelos NLP pesados en Core).

*   **Fuentes objetivo**: RSS, X/Twitter institucional, Bloomberg/Reuters/Fed wire.
*   **Modelo operacional**: El servicio consume eventos preprocesados externos y aplica scoring heurístico de posicionamiento institucional (macro + peso de fuente).
*   **Regla de veto**: Si el stream macro marca sesgo extremo (>= 80%) contrario a la dirección de una señal de alta probabilidad técnica, el `RiskManager` ejecuta veto con etiqueta `[SENTIMENT_VETO]`.
*   **Persistencia de contexto**: Snapshot de sentimiento queda inyectado en `signal.metadata["institutional_sentiment"]` para trazabilidad.

## 🛰️ Avance Radar: Predator Sense (HU 2.2)
Estado actualizado del scanner de depredación de contexto:

*   **Motor**: `ConfluenceService.detect_predator_divergence()` detecta barrido de liquidez inter-mercado + estancamiento del activo base.
*   **Caso canónico implementado**: DXY barriendo máximos mientras EURUSD se estanca.
*   **Salida normalizada**: `divergence_strength` (0-100), `state` (`DORMANT`, `TRACKING`, `PREDATOR_ACTIVE`), `signal_bias`.
*   **UI en tiempo real**: endpoint `/api/analysis/predator-radar` + widget `Predator Radar` en la Terminal de análisis.

