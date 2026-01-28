# Aethelgard - Sistema de Trading Algorítmico Agnóstico

Framework de inteligencia financiera multi-estrategia basado en clasificación de régimen de mercado.

## Arquitectura

Aethelgard está diseñado como un sistema modular que permite integrar múltiples plataformas de trading y estrategias de manera independiente.

### Componentes Principales

#### 1. Core Brain (`core_brain/`)
- **`server.py`**: Servidor FastAPI con WebSockets que gestiona múltiples conexiones simultáneas
- **`regime.py`**: Clasificador de régimen de mercado (TREND, RANGE, CRASH, NEUTRAL)
- **`scanner.py`**: Escáner proactivo multihilo; orquesta activos, `RegimeClassifier` por símbolo, monitor de CPU y priorización TREND (1s) / RANGE (10s)
- **`signal_factory.py`**: ⚡ **NUEVO** Motor de generación de señales con estrategia Oliver Vélez y sistema de scoring (0-100)

#### 2. Conectores (`connectors/`)
- **`bridge_nt8.cs`**: Bridge para NinjaTrader 8 (C#)
- **`bridge_mt5.py`**: Bridge para MetaTrader 5 (Python) - ⚡ **ACTUALIZADO** con ejecución automática en Demo
- **`mt5_data_provider.py`**: Ingestión autónoma de OHLC vía `mt5.copy_rates_from_pos` (sin gráficas abiertas)
- **`webhook_tv.py`**: Webhook para recibir alertas de TradingView

#### 3. Data Vault (`data_vault/`)
- **`storage.py`**: Sistema de persistencia SQLite para señales y feedback loop

#### 4. Models (`models/`)
- **`signal.py`**: Modelos de datos para señales y resultados

## Instalación

### Requisitos
- Python 3.12+
- Windows 11
- MetaTrader 5 (opcional, para conector MT5)
- NinjaTrader 8 (opcional, para conector NT8)

### Setup

1. Clonar el repositorio
```bash
git clone <repository-url>
cd Aethelgard
```

2. Crear entorno virtual
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```

3. Instalar dependencias
```bash
pip install -r requirements.txt
```

## Inicio Rápido

### Iniciar Sistema Completo (Motor + Dashboard)
```powershell
.\venv\Scripts\Activate.ps1
py start.py
```

### Iniciar Solo Dashboard
```powershell
.\start_dashboard.ps1
```

El dashboard estará disponible en: http://localhost:8501

3. Instalar dependencias
```bash
pip install -r requirements.txt
```

## Uso

### 🎯 Sistema Completo con Auto-Ejecución (NUEVO)

**Ejecutar el sistema completo**: Scanner + Signal Factory + MT5 Auto-Execute

```bash
python example_live_system.py
```

Este sistema integra:
1. **Scanner Proactivo**: Escanea múltiples activos en tiempo real
2. **Signal Factory**: Genera señales con estrategia Oliver Vélez
3. **MT5 Auto-Execute**: Ejecuta operaciones automáticamente en cuenta Demo

**⚠️ IMPORTANTE**: Solo ejecuta en cuentas DEMO por seguridad.

### Iniciar el servidor principal

```bash
python -m core_brain.server
```

El servidor estará disponible en `http://localhost:8000`

### Conectar MetaTrader 5

```bash
python connectors/bridge_mt5.py
```

### Escáner proactivo multihilo

El escáner consulta datos de forma **autónoma** vía MT5 `copy_rates_from_pos` (sin gráficas abiertas), orquesta múltiples activos con `RegimeClassifier` en hilos (`concurrent.futures`), controla CPU y prioriza por régimen.

**Ejecución:**

```bash
python run_scanner.py
```

**Requisitos:** MetaTrader 5 instalado y en ejecución. Los símbolos deben estar en Market Watch.

**Configuración** (`config/config.json` → `scanner`):

| Parámetro | Descripción | Default |
|-----------|-------------|---------|
| `assets` | Lista de símbolos a escanear | `["AAPL","TSLA","MES","EURUSD"]` |
| `cpu_limit_pct` | Umbral de CPU (%); si se supera, se aumenta el sleep entre ciclos | `80.0` |
| `sleep_trend_seconds` | Intervalo de escaneo para activos en TREND | `1.0` |
| `sleep_range_seconds` | Intervalo para activos en RANGE | `10.0` |
| `sleep_neutral_seconds` | Intervalo para NEUTRAL | `5.0` |
| `sleep_crash_seconds` | Intervalo para CRASH | `1.0` |
| `base_sleep_seconds` | Sleep base entre ciclos | `1.0` |
| `max_sleep_multiplier` | Límite del multiplicador de sleep cuando CPU > límite | `5.0` |
| `mt5_timeframe` | Timeframe MT5 (M1, M5, M15, H1, …) | `"M5"` |
| `mt5_bars_count` | Velas OHLC a solicitar por símbolo | `500` |
| `config_path` | Ruta a `dynamic_params` del clasificador | `"config/dynamic_params.json"` |

**Priorización:** TREND y CRASH → cada 1 s; RANGE → cada 10 s; NEUTRAL → cada 5 s.

**Control de recursos:** Si el uso de CPU supera `cpu_limit_pct`, el escáner aumenta el tiempo de espera entre ciclos (hasta `max_sleep_multiplier`).

**Test sin MT5** (DataProvider mock):

```bash
python test_scanner_mock.py
```

### Iniciar webhook de TradingView

```bash
python connectors/webhook_tv.py
```

El webhook estará disponible en `http://localhost:8001/webhook`

### Conectar NinjaTrader 8

1. Copiar `connectors/bridge_nt8.cs` a la carpeta de estrategias de NinjaTrader 8
2. Compilar en NT8
3. Añadir la estrategia a un gráfico
4. Configurar la URL del servidor en los parámetros

## Endpoints API

### WebSocket
- `ws://localhost:8000/ws/{connector}/{client_id}`
  - `connector`: NT, MT5, o TV
  - `client_id`: ID único del cliente

### HTTP
- `GET /`: Información del sistema
- `GET /health`: Health check
- `POST /api/signal`: Recibir señal (para webhooks)
- `GET /api/regime/{symbol}`: Obtener régimen de mercado
- `GET /api/signals`: Obtener señales recientes

## Clasificador de Régimen

El clasificador analiza:
- **Volatilidad**: Basada en desviación estándar de retornos
- **Tendencia**: Fuerza de tendencia (aproximación ADX)
- **Movimientos extremos**: Detección de crashes

### Regímenes
- **TREND**: Mercado con tendencia clara
- **RANGE**: Mercado lateral/rango
- **CRASH**: Movimiento extremo detectado
- **NEUTRAL**: Estado neutral/indefinido

## 🚀 Signal Factory - Lógica de Decisión Dinámica

### Sistema de Scoring (0-100)

El Signal Factory evalúa oportunidades de trading basándose en la estrategia de **Oliver Vélez** (swing trading):

| Criterio | Puntos | Descripción |
|----------|--------|-------------|
| **Régimen TREND** | +30 | El mercado está en tendencia clara (mejor régimen para operar) |
| **Vela Elefante** | +20 | Vela de alto momentum (rango > 2x ATR) |
| **Volumen Alto** | +20 | Volumen superior al promedio (confirmación) |
| **Cerca de SMA 20** | +30 | Precio rebotando en zona de soporte/resistencia |

**Score Total**: 0-100 puntos

### Filtrado por Membresía

Las señales se filtran según su calidad (score):

| Tier | Score Mínimo | Descripción |
|------|--------------|-------------|
| **FREE** | 0-79 | Señales básicas, disponibles para todos |
| **PREMIUM** | 80-89 | Señales de alta calidad (4 criterios cumplidos) |
| **ELITE** | 90-100 | Señales excepcionales (todos los criterios) |

**Pestaña Dashboard**:
- FREE: Ve solo señales FREE
- PREMIUM: Ve señales FREE + PREMIUM
- ELITE: Ve todas las señales

### Estrategia Oliver Vélez

Principios implementados:
1. ✅ **Operar solo en tendencia** (TREND regime)
2. ✅ **Buscar velas de momentum** (Velas Elefante)
3. ✅ **Confirmar con volumen** (> promedio)
4. ✅ **Entrar en zonas clave** (SMA 20 como soporte/resistencia)
5. ✅ **Risk/Reward 1:2** (SL 1.5x ATR, TP 3x ATR)

### Ejemplo de Uso

```python
from core_brain.signal_factory import SignalFactory
from models.signal import MarketRegime, MembershipTier

# Crear factory
factory = SignalFactory(
    strategy_id="oliver_velez_swing",
    premium_threshold=80.0,
    elite_threshold=90.0
)

# Generar señal
signal = factory.generate_signal(
    symbol="EURUSD",
    df=ohlc_dataframe,
    regime=MarketRegime.TREND
)

if signal:
    print(f"Señal: {signal.signal_type.value}")
    print(f"Score: {signal.score}/100")
    print(f"Tier: {signal.membership_tier.value}")
    print(f"Precio: {signal.price}")
    print(f"SL: {signal.stop_loss}")
    print(f"TP: {signal.take_profit}")

# Filtrar por membresía
premium_signals = factory.filter_by_membership(
    signals=[signal],
    user_tier=MembershipTier.PREMIUM
)
```

### Test del Sistema de Scoring

```bash
python test_signal_factory.py
```

Verifica:
- ✅ Cálculo correcto de scores
- ✅ Clasificación de tiers (FREE/PREMIUM/ELITE)
- ✅ Detección de velas elefante
- ✅ Análisis de volumen
- ✅ Proximidad a SMA 20
- ✅ Generación por lote

## Configuración

- **`config/config.json`**: Parámetros del escáner (activos, CPU, intervalos, MT5). Véase tabla en [Escáner proactivo](#escáner-proactivo-multihilo).
- **`config/dynamic_params.json`**: Parámetros del `RegimeClassifier` (ADX, volatilidad, persistencia, etc.).
- **`config/modules.json`**: Módulos de estrategias activos y niveles de membresía.

## Estructura Modular

Para añadir nuevas estrategias:

1. Crear módulo en `strategies/` (por crear)
2. Implementar lógica basada en régimen de mercado
3. Registrar en el sistema principal

Ejemplo de estructura:
```
strategies/
  __init__.py
  trend_following.py
  mean_reversion.py
  breakout.py
```

## Estructura de archivos clave

```
Aethelgard/
├── config/
│   ├── config.json         # Escáner: assets, cpu_limit_pct, intervalos, MT5
│   ├── dynamic_params.json # RegimeClassifier: ADX, volatilidad, etc.
│   └── modules.json        # Módulos de estrategias
├── core_brain/
│   ├── scanner.py          # Escáner proactivo multihilo (CPUMonitor, ScannerEngine)
│   ├── regime.py           # RegimeClassifier + load_ohlc
│   └── server.py           # FastAPI + WebSockets
├── connectors/
│   ├── mt5_data_provider.py # OHLC vía copy_rates_from_pos (sin gráficas)
│   └── bridge_mt5.py       # Bridge WebSocket MT5 → Aethelgard
├── run_scanner.py          # Entrypoint del escáner
└── test_scanner_mock.py    # Test del escáner con mock (sin MT5)
```

## Base de Datos

SQLite se inicializa automáticamente en `data_vault/aethelgard.db`

Tablas:
- `signals`: Almacena todas las señales recibidas
- `signal_results`: Almacena resultados y feedback

## Documentación

- **[AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md)**: 📖 **Fuente de verdad del proyecto** - Visión completa, arquitectura detallada, reglas de autonomía, estrategias implementadas (Signal Factory, Oliver Vélez) y guías técnicas.
- **[ROADMAP.md](ROADMAP.md)**: 🗺️ **Estado del proyecto** - Fases completadas y pendientes, incluyendo Scanner Proactivo (Fase 1.1) y Signal Factory (Fase 2.1).

**Para información completa sobre:**
- Sistema de Scoring y Membresías → Ver [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#signal-factory---lógica-de-decisión-dinámica)
- Estrategia Oliver Vélez implementada → Ver [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#trend-following-régimen-trend)
- Arquitectura y flujo de datos → Ver [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#arquitectura-del-sistema)

## Desarrollo

El código está diseñado para ser modular y extensible. Cada componente puede funcionar de manera independiente.

## Licencia

[Especificar licencia]
