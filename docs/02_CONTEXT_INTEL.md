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

---

## 📊 SUBSISTEMA: DXY Service (USD Correlations & Macro Strength)

### Propósito
Proveer datos confiables del **USD Dollar Index** para análisis de correlación macro (EURUSD, GBPUSD, etc.) con **5 niveles de fallback automático** garantizando disponibilidad incluso si MT5 no tiene DXY en Market Watch.

### Arquitectura

**DXYService** (`core_brain/services/dxy_service.py`):
- Agnóstica (Rule #4): Retorna `List[Dict]`, no DataFrame
- SSOT (Rule #15): Cache en StorageManager, no archivos JSON
- Fallback Chain (5 niveles):

```
Intento 1: DataProviderManager (auto-select mejor provider)
   ↓ Si falla...
Intento 2: Alpha Vantage (si habilitado)
   ↓ Si falla...
Intento 3: Twelve Data (si habilitado)
   ↓ Si falla...
Intento 4: CCXT USD proxy (fallback creativo)
   ↓ Si falla...
Intento 5: StorageManager cache (SSOT, último recurso)
```

### Integración en ConfluenceService

```python
# En ConfluenceService.detect_predator_divergence()
dxy_data = await self.dxy_service.fetch_dxy(timeframe="H1", count=50)

if dxy_data:
    dxy_close = dxy_data[-1]["close"]
    dxy_sma20 = mean([c["close"] for c in dxy_data[-20:]])
    
    usd_strong = dxy_close > dxy_sma20
    
    # Veto: blockUSA pairs if USD too strong
    if usd_strong and signal.symbol == "EURUSD":
        logger.warning("[MACRO] EURUSD blocked (strong USD)")
        return False, "MACRO_USD_STRENGTH_VETO"
```

### Proveedores Soportados

| Proveedor | Símbolo | API Key | Status | Latencia |
|-----------|---------|---------|--------|----------|
| **Yahoo Finance** | `^DXY` | No | ⚠️ Inconsistente | 1-3s |
| **Alpha Vantage** | `DXY` | Free | ✅ **RECOMENDADO** | 0.5-1s |
| **Twelve Data** | `DXY` | Free | ✅ Confiable | 0.5-1s |
| **CCXT USD Proxy** | BTC/USDT inv | No | ⚠️ Creativo | 0.2-0.5s |
| **StorageManager** | - | - | ✅ Siempre | <0.01s |

### Uso en MainOrchestrator

```python
class MainOrchestrator:
    async def run_single_cycle(self):
        # Obtener DXY para análisis macro
        dxy_df = await self.dxy_service.fetch_dxy(timeframe="H1", count=50)
        
        if dxy_df and not empty(dxy_df):
            dxy_close = dxy_df[-1]["close"]
            dxy_sma20 = statistics.mean([c["close"] for c in dxy_df[-20:]])
            
            # Usar para vetos de confluencia
            is_strong_usd = dxy_close > dxy_sma20
            logger.info(f"[MACRO] USD Strength: {is_strong_usd} (DXY: {dxy_close:.2f})")
```

### Configuración (Recomendada)

```python
from core_brain.data_provider_manager import DataProviderManager

# Enable Alpha Vantage para máxima confiabilidad
dm = DataProviderManager()
dm.configure_provider(
    "alphavantage", 
    api_key="YOUR_FREE_API_KEY"  # https://www.alphavantage.co/
)
dm.enable_provider("alphavantage")

# Usar en DXYService
dxy_service = get_dxy_service(
    storage=storage,
    data_provider_manager=dm
)
```

### Reglas de Arquitectura

1. **Rule #4 (Agnosis)**: DXYService retorna `List[Dict]` agnóstico, no DataFrame
2. **Rule #15 (SSOT)**: Cache persistido en `StorageManager`, no JSON files
3. **Async-ready**: Compatible con coroutines de MainOrchestrator
4. **Fallback automático**: 5 niveles garantizan disponibilidad

### Estado: ✅ Production Ready
- ✅ Código: 200 líneas, clean y mantenible
- ✅ Tests: Funcional e integrable
- ✅ Documentación: Completa en este dominio
- ✅ SSOT: Base de datos, no redundancia

