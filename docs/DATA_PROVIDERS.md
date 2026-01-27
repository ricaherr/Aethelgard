# 📡 Proveedores de Datos - Guía de Instalación

## 🎯 Resumen

Aethelgard soporta múltiples proveedores de datos con fallback automático. Puedes usar proveedores gratuitos sin API key o configurar proveedores con API key para mayor capacidad.

## 🆓 Proveedores Gratuitos (Sin API Key)

### Yahoo Finance (Recomendado - Por defecto)
```bash
pip install yfinance
```
- ✅ **100% gratuito**
- ✅ **Sin límites de requests**
- ✅ **No requiere registro**
- Soporta: Stocks, Forex, Crypto, Commodities, Índices

### CCXT (Para Criptomonedas)
```bash
pip install ccxt
```
- ✅ **100% gratuito para datos públicos**
- ✅ **100+ exchanges**
- ✅ **No requiere API key para datos de mercado**
- Soporta: Bitcoin, Ethereum, y todas las principales criptomonedas

## 🔑 Proveedores con API Key (Tier Gratuito Disponible)

### Alpha Vantage
```bash
pip install requests
```
- **Límite gratuito**: 500 requests/día
- **Registro**: https://www.alphavantage.co/support/#api-key
- Soporta: Stocks, Forex, Crypto

**Configuración:**
```python
# Desde código
manager.configure_provider("alphavantage", api_key="YOUR_API_KEY")

# O desde Dashboard UI
# Ir a pestaña "Proveedores de Datos" → Alpha Vantage → Configurar
```

### Twelve Data
```bash
pip install requests
```
- **Límite gratuito**: 800 requests/día
- **Registro**: https://twelvedata.com/pricing
- Soporta: Stocks, Forex, Crypto, Commodities

**Configuración:**
```python
manager.configure_provider("twelvedata", api_key="YOUR_API_KEY")
```

### Polygon.io
```bash
pip install requests
```
- **Límite gratuito**: Datos con delay
- **Registro**: https://polygon.io/
- Soporta: Stocks, Forex, Crypto, Options

**Configuración:**
```python
manager.configure_provider("polygon", api_key="YOUR_API_KEY")
```

## 🖥️ MetaTrader 5 (Local)

```bash
pip install MetaTrader5
```
- Requiere MT5 instalado en tu PC
- Conexión directa con tu broker
- Datos en tiempo real

**Configuración:**
```python
manager.configure_provider(
    "mt5",
    login="YOUR_LOGIN",
    password="YOUR_PASSWORD",
    server="YOUR_BROKER_SERVER"
)
```

## 🚀 Instalación Rápida - Todo Incluido

Para instalar **todos** los proveedores de una vez:

```bash
pip install yfinance ccxt requests MetaTrader5
```

## 📊 Uso desde el Dashboard

1. Inicia el dashboard:
```bash
streamlit run ui/dashboard.py
```

2. Ve a la pestaña "📡 Proveedores de Datos"

3. **Proveedores Gratuitos:**
   - Yahoo Finance: Habilitado por defecto
   - CCXT: Click en "Habilitar" para activar

4. **Proveedores con API Key:**
   - Click en el proveedor deseado
   - Ingresa tu API key en el formulario
   - Click "Guardar Configuración"
   - Click "Habilitar"

5. **Probar Conexión:**
   - Click en "🔍 Probar Conexión"
   - El sistema probará el proveedor activo y mostrará datos de ejemplo

## 🎛️ Uso desde Código

```python
from core_brain.data_provider_manager import DataProviderManager

# Inicializar manager
manager = DataProviderManager()

# Opción 1: Usar el mejor proveedor disponible automáticamente
data = manager.fetch_ohlc("AAPL", timeframe="M5", count=500)

# Opción 2: Especificar proveedor
data = manager.fetch_ohlc("AAPL", timeframe="M5", count=500, provider_name="yahoo")

# Habilitar/deshabilitar proveedores
manager.enable_provider("alphavantage")
manager.disable_provider("yahoo")

# Configurar API keys
manager.configure_provider("alphavantage", api_key="YOUR_KEY")

# Obtener mejor proveedor para un símbolo específico
provider = manager.get_provider_for_symbol("BTCUSD")  # Usará CCXT para crypto
```

## 🔄 Fallback Automático

El sistema usa **fallback automático** basado en prioridad:

1. **Yahoo Finance** (prioridad: 100)
2. **MetaTrader 5** (prioridad: 95) - si está configurado
3. **CCXT** (prioridad: 90) - para crypto
4. **Alpha Vantage** (prioridad: 80) - si tiene API key
5. **Twelve Data** (prioridad: 70) - si tiene API key
6. **Polygon.io** (prioridad: 60) - si tiene API key

Si el proveedor de mayor prioridad falla, el sistema automáticamente prueba el siguiente.

## 🛠️ Configuración Avanzada

### Cambiar Prioridades

```python
manager.set_provider_priority("ccxt", 110)  # Ahora CCXT es el más prioritario
```

### Configuración Persistente

La configuración se guarda automáticamente en:
```
config/data_providers.json
```

### Ejemplo de Variables de Entorno

Copia `config/data_providers.example.env` a `.env` y edita:

```bash
ALPHAVANTAGE_API_KEY=your_key_here
TWELVEDATA_API_KEY=your_key_here
POLYGON_API_KEY=your_key_here
```

## ❓ Troubleshooting

### Error: "Provider not available"
```bash
# Instalar la librería correspondiente
pip install yfinance  # Para Yahoo
pip install ccxt      # Para CCXT
pip install requests  # Para Alpha Vantage, Twelve Data, Polygon
pip install MetaTrader5  # Para MT5
```

### Error: "API key not configured"
- Configura la API key desde el Dashboard o código
- Verifica que el proveedor esté habilitado

### Sin datos retornados
- Verifica que el símbolo sea correcto
- Prueba con otro timeframe
- Revisa los logs en `logs/production.log`

## 📚 Más Información

- Ver documentación completa en `AETHELGARD_MANIFESTO.md`
- Tests en `tests/test_data_provider_manager.py`
- Código fuente en `core_brain/data_provider_manager.py`
