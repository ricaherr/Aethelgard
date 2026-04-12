# Dominio 01: CORE_ADAPTIVE_BRAIN

**ID de Transacción:** JOB-01-CORE-ADAPTIVE-BRAIN-2026-04-10
**Fecha:** 10 de abril de 2026

## 🎯 Tesis del Régimen (Market Regimes)

El sistema comprende la estructura del mercado clasificando cada `asset` en cuatro regímenes fundamentales. Esta inteligencia de contexto filtra y orienta las estrategias garantizando una mayor esperanza matemática.

*   **TREND (Tendencia)**: Movimiento direccional sostenido y claro. Entorno óptimo para capitalizar estrategias de seguimiento de tendencia, aprovechando el momentum de macro-escala.
*   **RANGE (Rango)**: Mercado lateralizado y oscilante entre delimitaciones (soportes/resistencias) claras. Beneficia enfoques de reversión a la media.
*   **NORMAL (Estándar)**: Comportamiento equilibrado de volatilidad y volumen promedio, sin direccionalidad agresiva ni contracciones severas que comprometan la liquidez.
*   **SHOCK (Volatilidad Extrema)**: Anomalías críticas de mercado asociadas con inyecciones de volatilidad macro, barridos institucionales de liquidez inter-mercado o impacto de noticias. Este régimen activa vetos de riesgo o mecanismos de *Predator Sense*.

## 🧠 Motor de Aprendizaje Adaptativo

Para garantizar su perpetuidad y eficiencia, el sistema evoluciona de forma autónoma procesando el resultado histórico y reciente para recalibrar su toma de decisiones.

*   **EdgeTuner**: Motor de calibración paramétrica en tiempo real. Evalúa los resultados de cada ejecución para reajustar los pesos de relevancia (`regime_configs`) basándose en el historial empírico.
*   **ThresholdOptimizer**: Controlador central del riesgo dinámico. Modula automáticamente la exigencia del sistema ajustando el `confidence_threshold`. Observa el desempeño (win_rate, drawdown continuo y pérdidas consecutivas) para elevar la precisión ante rachas negativas o permitir una mayor exploración algorítmica cuando la equidad es alcista.

### Métricas Sensoriales

Se elimina cualquier redundancia interpretativa centralizando la evaluación analítica del `asset` en métricas sensoriales claras:

*   **ADX (Average Directional Index)**: Determinante primario de la fuerza vectorial de una tendencia. Integrado con los sensores multitemporales (alineación fractal), certifica objetivamente la transición hacia un régimen TREND.
*   **Alineación Fractal**: Vectorización analítica que contrasta temporalidades desde marcos micro (M1/M5) hasta estructuras macro (H4/D1) para garantizar que una señal fluya a favor de la corriente institucional.
*   **Correlación y Sentimento**: El sistema rastrea métricas inter-mercado para detectar divergencias *Predator* previniendo así entradas sesgadas, apalancándose en integraciones ligeras sin exponer el core al ruido de datos rudimentarios.

## 🔄 El Bucle Delta Feedback

El ciclo de vida del aprendizaje se materializa post-trade, permitiendo que el sistema calibre dinámicamente cómo interpreta las métricas futuras. Los pasos del bucle son:

1. **Recepción del Score Final**: Al finalizar una posición (evento validado en `sys_trades` o `usr_trades`), el sistema audita el cierre a través del *TradeClosureListener*.
2. **Cálculo del Delta**: Se procesa la diferencia entre la efectividad teórica pronosticada y el resultado en bruto: `Delta = Resultado - Score_Predicho`.
3. **Retroalimentación**:
   * Si el *Delta* sobrepasa ciertos rangos de tolerancia, el **EdgeTuner** actualiza el sesgo y peso ponderado del régimen.
   * Dependiendo de la estructura de las últimas ejecuciones evaluadas en la tabla de registro, el **ThresholdOptimizer** decide si endurece o relaja el `confidence_threshold` dinámico.
4. **Persistencia Limpia (SSOT)**: Las readaptaciones se registran mediante inserciones auditadas en el esquema de sistema. Los overrides de parámetros se persisten en la columna `parameter_overrides` (JSON) de `sys_shadow_instances`; los eventos de deduplicación en la tabla `sys_dedup_events`. La fuente de verdad siempre emite parámetros ajustados en función del mercado sin intervención humana.

## 📈 Roadmap del Dominio

**Hitos Completados:**
- [x] Unificación de la lógica de regímenes dentro del sistema de inteligencia contextual.
- [x] Despliegue de scanner inter-mercado (ConfluenceService) para lecturas cruzadas asimétricas.
- [x] Implementación profunda del EdgeTuner y Bucle de Feedback paramétrico (Delta Feedback).
- [x] Despliegue del ThresholdOptimizer para reajuste autónomo del `confidence_threshold` bajo custodia de un Safety Governor.
- [x] SHADOW Evolution Integration: Promoción estructurada de modo BACKTEST → SHADOW → LIVE guardando historial en la tabla `sys_strategies`.
- [x] Dynamic Deduplication Windows: Aprendizaje de gaps óptimos procesados independientemente.

**Hitos Pendientes:**
- [ ] Optimización de la memoria contextual adaptativa (mayor alcance de histórico asimétrico).
- [ ] Meta-aprendizaje avanzado sobre la asimilación del slippage en ejecución real latente.
- [ ] Automatización integral de umbrales escalonada dictaminada estrictamente por microestructura de volatilidad en tiempo real.

## 💡 Submódulo de Generación de Ideas (Alpha Engine)

Este submódulo garantiza la generación constante de oportunidades de inversión mediante el escaneo proactivo de patrones institucionales y la ponderación dinámica de señales.

### Componentes Críticos
*   **Scanner Proactivo**: Escaneo multi-timeframe de alta eficiencia que busca ineficiencias de mercado.
*   **Technical Analyzer**: Fuente única de verdad para indicadores vectorizados y métricas de volatilidad.
*   **Liquidity Service**: Detección micro-estructural de Fair Value Gaps (FVG) y Order Blocks mediante análisis de absorción de volumen.
*   **Signal Factory**: Generador de señales con scoring dinámico basado en confluencia y riesgo/beneficio.
*   **Strategy Jury** *(Objetivo Arquitectónico — Pendiente de integración)*: Mecanismo de decisión darwinista (`StrategySignalValidator`) que evaluará la probabilidad de éxito de una señal antes de su ejecución mediante 4 Pilares (Sensorial, Régimen, Coherencia, Multi-tenant). Clase implementada en `core_brain/strategy_validator_quanter.py`; pendiente de cableado en `signal_factory.py`.

### Firmas Operativas Validadas

Cada firma sigue el **Protocolo Quanter** con los 4 Pilares (Sensorial, Régimen, Coherencia, Multi-tenant).

**Ejemplo: Market Open Gap - EUR/USD (Premium)**
- **Pilar Sensorial**: FVG (60 min pre), RSI, MA (20, 50), Order Block, ATR.
- **Pilar de Régimen**: TREND_UP, EXPANSION, ANOMALY.
- **Pilar de Coherencia**: CoherenceScore >= 75% (Shadow vs Live).
- **Pilar Multi-tenant**: Disponible para Premium+.

### Signal Deduplication & Confluence
Para evitar sobre-exposición, el motor implementa algoritmos restrictivos de deduplicación de señales (SignalDeduplicator) y análisis de confluencia (SignalConflictAnalyzer) que ajustan el *score* de la oportunidad basándose en la temporalidad macro, y ejecutan filtros de agresión dinámica en las entradas.
