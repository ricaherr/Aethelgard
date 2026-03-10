# 📊 Cómo Obtener DXY (USD Dollar Index) - 5 Opciones con Fallback Automático

## El Problema

DXY no está disponible en MT5 Market Watch. Sistema necesita múltiples opciones para obtener este dato crítico para análisis macro.

## La Solución: 5 Niveles de Fallback

El `DXYService` intenta obtener DXY automáticamente en este orden:

```
Intento 1: Yahoo Finance (^DXY)
    ↓ Si falla...
Intento 2: Alpha Vantage (si habilitado)
    ↓ Si falla...
Intento 3: Twelve Data (si habilitado)
    ↓ Si falla...
Intento 4: CCXT USD Proxy (si habilitado)
    ↓ Si falla...
Intento 5: Cache Local (última 24h)
```

---

## Quick Start (Recomendado)

```python
from core_brain.services.dxy_service import get_dxy_service
from core_brain.data_provider_manager import DataProviderManager
import asyncio

async def main():
    # Habilitar al menos 1 fallback para confiabilidad
    dm = DataProviderManager()
    dm.enable_provider("alphavantage")
    dm.configure_provider("alphavantage", api_key="YOUR_FREE_API_KEY")
    
    # Obtener DXY con fallback automático
    dxy_service = get_dxy_service(data_provider_manager=dm)
    df = await dxy_service.fetch_dxy(timeframe="H1", count=50)
    
    if df is not None:
        print(f"✅ DXY Close: {df.iloc[-1]['close']:.2f}")
    else:
        print("❌ No data (enable fallback providers)")

asyncio.run(main())
```

---

## Opción 1: Yahoo Finance (Sin API Key)

**Ventajas**: Gratis, sin configuración  
**Desventajas**: Inconsistente (puede no funcionar)  
**Símbolo**: `^DXY`

```python
from connectors.generic_data_provider import get_provider

provider = get_provider()
df = provider.fetch_ohlc("DXY", "H1", 50)

if df is not None:
    print(f"DXY: {df.iloc[-1]['close']:.2f}")
```

---

## Opción 2: Alpha Vantage ✅ **RECOMENDADO**

**Ventajas**: ✅ Confiable, ✅ Rápido, ✅ API Key gratuita  
**Desventajas**: Requiere registro (2 min)  
**Símbolo**: `DXY` directamente

### Setup:
```python
from core_brain.data_provider_manager import DataProviderManager

dm = DataProviderManager()
dm.configure_provider("alphavantage", api_key="YOUR_KEY")
dm.enable_provider("alphavantage")
```

### Use:
```python
provider = dm.get_provider("alphavantage")
df = provider.fetch_ohlc("DXY", "H1", 50)
```

### Get Free API Key: 
👉 https://www.alphavantage.co/  
- Gratuita: 500 req/día
- Institucional: 800+ req/día

---

## Opción 3: Twelve Data

**Ventajas**: ✅ Confiable, ✅ Generosos rate limits  
**Desventajas**: Requiere registro  
**Símbolo**: `DXY` (índice)

### Setup:
```python
dm = DataProviderManager()
dm.configure_provider("twelvedata", api_key="YOUR_KEY")
dm.enable_provider("twelvedata")
```

### Get Free API Key:
👉 https://twelvedata.com/pricing  
- Gratuita: 800 req/día

---

## Opción 4: CCXT (USD Proxy)

**Ventajas**: ✅ Sin API Key, ✅ Disponible 24/7  
**Desventajas**: ⚠️ Proxy (BTC/USDT inverted), no es DXY real  
**Símbolo**: `BTC/USDT` → invertido

```python
dm = DataProviderManager()
dm.enable_provider("ccxt")

# Sistema automáticamente usa BTC/USDT como USD proxy
```

---

## Opción 5: Cache Local

**Ventajas**: ✅ Siempre disponible, offline  
**Desventajas**: Datos < 24h  
**Ubicación**: `data_vault/cache/dxy_cache.json`

```python
# Automático si otros proveedores fallan
df = await dxy_service.fetch_dxy(use_cache=True)
```

---

## Verificar Estado

```python
dxy_service = get_dxy_service()
status = dxy_service.get_dxy_status()

# Output:
# {
#   'service': 'DXYService',
#   'cache_available': True,
#   'cache_size': 100,
#   'latest_close': 105.23,
#   'fallback_count': 5
# }
```

---

## Ejemplo de Integración en MainOrchestrator

```python
class MainOrchestrator:
    async def run_single_cycle(self):
        # Obtener DXY
        dxy_df = await self.dxy_service.fetch_dxy(timeframe="H1", count=50)
        
        if dxy_df is not None:
            dxy_close = dxy_df.iloc[-1]['close']
            dxy_sma20 = dxy_df['close'].rolling(20).mean().iloc[-1]
            
            is_strong_usd = dxy_close > dxy_sma20
            
            # Uso: Filtrar operaciones EURUSD si USD está muy fuerte
            for signal in signals:
                if signal.symbol == "EURUSD" and is_strong_usd:
                    logger.warning("[MACRO] Skipping EURUSD (strong USD)")
                    continue  # Saltar esta operación
```

---

## Testing

```bash
# Demo completa (todas 5 opciones)
python scripts/utilities/dxy_demo.py

# Test rápido
python scripts/utilities/test_dxy_quick.py
```

---

## Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| "No DXY data" | Yahoo rate-limited | Habilitar Alpha Vantage |
| "All providers failed" | No fallbacks enabled | `dm.enable_provider("alphavantage")` |
| "Cache expired" | >24h sin actualización | Fetch fresco: `use_cache=False` |

---

## Comparación de Opciones

| Opción | API Key | Latencia | Confiable | Costo | Recomendación |
|--------|---------|----------|-----------|-------|---------------|
| 1: Yahoo | No | 1-3s | ⚠️ No | Gratis | Primer intento |
| **2: Alpha Vantage** | **Free** | **0.5-1s** | **✅ Sí** | **Gratis** | **🌟 USAR ESTO** |
| 3: Twelve Data | Free | 0.5-1s | ✅ Sí | Gratis | Segundo fallback |
| 4: CCXT | No | 0.2-0.5s | ⚠️ Proxy | Gratis | Última opción |
| 5: Cache | No | <0.01s | ✅ Sí | Gratis | Fallback final |

---

## Recomendación Final

Para **máxima confiabilidad**:

1. **Enable Alpha Vantage** (API Key gratuita de https://www.alphavantage.co/)
2. **Use DXYService** (maneja fallbacks automáticamente)
3. **Monitor cache** (verificar que tenga datos recientes)

```python
# 3 líneas para DXY guaranteed:
dm = DataProviderManager()
dm.configure_provider("alphavantage", api_key="YOUR_KEY")
dm.enable_provider("alphavantage")

dxy_service = get_dxy_service(data_provider_manager=dm)
df = await dxy_service.fetch_dxy(timeframe="H1")
```

---

**Updated**: 10 de Marzo 2026  
**Status**: ✅ Production Ready  
**Documentation**: Complete
