# AETHELGARD MANIFESTO
## Única Fuente de Verdad del Proyecto

> **Versión:** 1.0  
> **Última Actualización:** Enero 2026  
> **Estado del Proyecto:** Fase 2 - Implementación de Estrategias Modulares

---

## 📋 Tabla de Contenidos

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Reglas de Autonomía](#reglas-de-autonomía)
4. [Roadmap de Implementación](#roadmap-de-implementación)
5. [Estrategias](#estrategias)

---

## 🎯 Visión General

### ¿Qué es Aethelgard?

**Aethelgard** es un sistema de trading algorítmico **autónomo**, **agnóstico** y **adaptativo** diseñado para operar múltiples estrategias de manera inteligente basándose en la clasificación de régimen de mercado.

### Principios Fundamentales

#### 1. **Autonomía**
Aethelgard opera de forma independiente, tomando decisiones basadas en:
- Clasificación automática de régimen de mercado (TREND, RANGE, CRASH, NEUTRAL)
- Auto-calibración de parámetros mediante análisis de datos históricos
- Detección de drift y activación de modo seguridad sin intervención humana

#### 2. **Agnosticismo de Plataforma**
El sistema está diseñado para ser completamente independiente de cualquier plataforma de trading específica:
- **Core Brain** (Python) nunca depende de librerías de NinjaTrader o MetaTrader
- Comunicación universal vía **JSON sobre WebSockets**
- Conectores modulares que se adaptan a cada plataforma sin modificar el núcleo

#### 3. **Adaptatividad**
Aethelgard evoluciona continuamente mediante:
- **Feedback Loop**: Cada decisión se contrasta con resultados reales del mercado
- **Auto-Tune**: Re-ejecución de tests de sensibilidad sobre datos históricos
- **Aprendizaje Continuo**: Optimización autónoma de parámetros (ADX, volatilidad, umbrales)

### Objetivo Principal

Crear un **cerebro centralizado** que:
- Reciba señales de múltiples plataformas (NinjaTrader 8, MetaTrader 5, TradingView)
- Clasifique el régimen de mercado en tiempo real
- Active estrategias modulares según el contexto detectado
- Aprenda de sus resultados para mejorar continuamente

---

## 🏗️ Arquitectura del Sistema

### Modelo Hub-and-Spoke

Aethelgard utiliza una arquitectura **Hub-and-Spoke** donde el **Core Brain** (Python) actúa como el centro de control, y los **Conectores** se comunican con él mediante WebSockets.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CORE BRAIN (Hub)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │   Server     │  │   Regime     │  │   Storage    │                   │
│  │  (FastAPI)   │  │ Classifier   │  │  (SQLite)    │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   Tuner      │  │ SignalFactory│  │   Scanner    │  │ RiskManager │ │
│  │ (Auto-Calib) │  │ (Strategies) │  │ (Proactivo)  │  │  (Escudo)   │ │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│                           │                  │                 │        │
│                           ▼                  ▼                 ▼        │
│                    ┌──────────────────────────────────────────────┐    │
│                    │          OrderExecutor (Cerebro)             │    │
│                    │  • Validación RiskManager                    │    │
│                    │  • Factory Pattern (Routing)                 │    │
│                    │  • Resiliencia ante fallos                   │    │
│                    │  • Audit Trail + Telegram                    │    │
│                    └─────────────────┬────────────────────────────┘    │
└──────────────────────────────────────┼─────────────────────────────────┘
                                       │
                     ┌─────────────────┼─────────────────┐
                     │                 │                 │
                 WebSocket        WebSocket         HTTP/DataProvider
                     │                 │                 │
                ┌────▼────┐       ┌────▼────┐      ┌────▼────┐
                │   NT8   │       │   MT5   │      │   TV    │       ┌─────────────┐
                │ Bridge  │       │ Bridge  │      │Webhook  │───────│ MT5 Data    │
                └─────────┘       └─────────┘      └─────────┘       │ Provider    │
                                                                      │(copy_rates) │
                                                                      └─────────────┘
```
                                                    │(copy_rates) │
                                                    └─────────────┘
```

### Componentes Principales

#### 1. **Core Brain** (`core_brain/`)

##### `server.py` - Servidor FastAPI con WebSockets
- **Función**: Punto de entrada principal del sistema
- **Responsabilidades**:
  - Gestionar múltiples conexiones WebSocket simultáneas
  - Diferenciar entre conectores (NT, MT5, TV)
  - Procesar señales recibidas
  - Coordinar clasificación de régimen
  - Enviar respuestas a los conectores

**Endpoints:**
- `GET /`: Información del sistema
- `GET /health`: Health check
- `WS /ws/{connector}/{client_id}`: WebSocket principal
- `POST /api/signal`: Recibir señal vía HTTP (webhooks)
- `GET /api/regime/{symbol}`: Obtener régimen actual
- `GET /api/signals`: Obtener señales recientes

##### `regime.py` - Clasificador de Régimen de Mercado
- **Función**: Analizar condiciones de mercado y clasificar el régimen
- **Métricas Calculadas**:
  - **ADX (Average Directional Index)**: Fuerza de tendencia
  - **Volatilidad**: Desviación estándar de retornos
  - **ATR (Average True Range)**: Volatilidad base de largo plazo
  - **SMA Distance**: Distancia del precio a SMA 200 (sesgo alcista/bajista)
  - **Volatility Shock**: Detección de movimientos extremos

**Regímenes Detectados:**
- **TREND**: Mercado con tendencia clara (ADX > 25, con histéresis)
- **RANGE**: Mercado lateral/rango (ADX < 20)
- **CRASH**: Movimiento extremo detectado (volatilidad > 5x base)
- **NEUTRAL**: Estado indefinido o insuficientes datos

**Características Avanzadas:**
- **Histéresis ADX**: Entrar TREND > 25, salir TREND → RANGE < 18
- **Filtro de Persistencia**: Cambio confirmado solo tras 2 velas consecutivas
- **Filtro de Volatilidad Mínima**: Evita falsos CRASH en mercados muertos
- **Parámetros Dinámicos**: Carga desde `config/dynamic_params.json`
- **`load_ohlc(df)`**: Carga masiva OHLC para escáner proactivo (p. ej. desde MT5)

##### `scanner.py` - Escáner Proactivo Multihilo
- **Función**: Orquestador que escanea una lista de activos de forma proactiva, sin depender de NinjaTrader ni de gráficas abiertas.
- **Componentes**:
  - **ScannerEngine**: Recibe `assets` y un **DataProvider** (inyectado; agnóstico de plataforma). Un `RegimeClassifier` por símbolo.
  - **CPUMonitor**: Lee uso de CPU (`psutil`). Si supera `cpu_limit_pct` (configurable en `config/config.json`), aumenta el sleep entre ciclos.
- **Multithreading**: `concurrent.futures.ThreadPoolExecutor` para procesar cada activo en hilos separados.
- **Priorización**: TREND/CRASH → escaneo cada 1 s; RANGE → cada 10 s; NEUTRAL → cada 5 s (configurable).
- **Configuración**: `config/config.json` → `scanner` (`assets`, `cpu_limit_pct`, `sleep_*_seconds`, `mt5_timeframe`, `mt5_bars_count`, etc.).
- **Entrypoint**: `run_scanner.py` (usa `MT5DataProvider`). Test sin MT5: `test_scanner_mock.py`.

##### `main_orchestrator.py` - Orquestador Resiliente del Sistema
- **Función**: Coordina el ciclo completo de trading: Scan → Signal → Risk → Execute
- **Arquitectura**: "Orquestador Resiliente" con recuperación automática tras fallos
- **Características Principales**:
  - **Bucle Asíncrono**: Usa `asyncio` para ejecución no bloqueante
  - **Frecuencia Dinámica**: Ajusta velocidad del loop según régimen de mercado:
    - TREND: 5 segundos (rápido)
    - RANGE: 30 segundos (lento, ahorro de CPU)
    - VOLATILE: 15 segundos (intermedio)
    - SHOCK: 60 segundos (muy lento, modo precaución)
  - **Latido de Guardia (Adaptive Heartbeat)**:
    - Sleep se reduce a 3 segundos cuando hay señales activas
    - Permite respuesta rápida a condiciones cambiantes del mercado
    - CPU-friendly: respeta límites de uso de CPU configurados
  - **SessionStats con Reconstrucción desde DB**:
    - Rastrea estadísticas del día actual (signals_processed, signals_executed, cycles_completed, errors_count)
    - **RESILIENCIA**: Al iniciar, reconstruye estado desde la base de datos
    - Método `SessionStats.from_storage()` consulta señales ejecutadas de hoy vía `StorageManager.count_executed_signals()`
    - Garantiza que trades ejecutados hoy NO se olviden tras reinicios/crashes
  - **Persistencia Continua**:
    - Persiste señales ejecutadas inmediatamente a DB tras ejecución (`storage.save_signal()`)
    - Persiste session_stats tras cada ciclo (`_persist_session_stats()`)
    - Minimiza pérdida de datos ante crashes inesperados
  - **Graceful Shutdown**: Manejo de Ctrl+C (SIGINT) y SIGTERM:
    1. Cierra conexiones de brokers limpiamente
    2. Persiste estado de lockdown en `data_vault`
    3. Guarda estadísticas de sesión finales
    4. Sale de forma ordenada sin pérdida de datos
- **Ciclo de Ejecución**:
  1. Scanner busca oportunidades en activos configurados
  2. Signal Factory genera señales basadas en estrategias
  3. Risk Manager valida contra lockdown mode
  4. Executor ejecuta señales aprobadas
  5. **Persiste señal a DB inmediatamente** (critical for recovery)
  6. Actualiza estadísticas y régimen actual
  7. Persiste session_stats tras cada ciclo
- **Configuración**: `config/config.json` → `orchestrator` (`loop_interval_trend`, `loop_interval_range`, `loop_interval_volatile`, `loop_interval_shock`)
- **Tests de Resiliencia**: `tests/test_orchestrator_recovery.py` 
  - Verifica reconstrucción de SessionStats desde DB
  - Simula crash y recuperación
  - Valida que señales ejecutadas hoy no se pierden
  - Prueba latido adaptativo con señales activas
  - Confirma persistencia tras cada ciclo
- **Tests Funcionales**: `tests/test_orchestrator.py` (11 tests cubriendo ciclo completo, frecuencia dinámica, shutdown graceful, manejo de errores)
- **Ejemplo de Uso**:
```python
from core_brain.main_orchestrator import MainOrchestrator

# SessionStats se reconstruye automáticamente desde DB
orchestrator = MainOrchestrator(
    scanner=scanner_instance,
    signal_factory=factory_instance,
    risk_manager=risk_instance,
    executor=executor_instance,
    storage=storage_instance  # Necesario para persistencia
)
await orchestrator.run()  # Inicia el loop resiliente

# Si el sistema crashea y se reinicia:
# - SessionStats recupera count de señales ejecutadas desde DB
# - Trades del día actual se mantienen en memoria
# - No hay pérdida de información crítica
```

**Ventajas del Orquestador Resiliente:**
- ✅ **Zero Data Loss**: Señales persistidas inmediatamente tras ejecución
- ✅ **Crash Recovery**: Estado completo reconstruible desde DB
- ✅ **Adaptive Performance**: Latido rápido con señales activas, lento en calma
- ✅ **Production Ready**: Diseñado para operación 24/7 sin supervisión

##### `tuner.py` - Sistema de Auto-Calibración
- **Función**: Optimizar parámetros basándose en datos históricos
- **Proceso**:
  1. Analiza estados de mercado históricos desde `data_vault`
  2. Calcula tasa de falsos positivos para diferentes umbrales
  3. Optimiza umbrales ADX (TREND, RANGE, EXIT)
  4. Optimiza multiplicador de volatilidad para shocks
  5. Guarda configuración optimizada en `config/dynamic_params.json`

#### 2. **Conectores** (`connectors/`)

##### `bridge_nt8.cs` - Bridge para NinjaTrader 8
- **Lenguaje**: C# (NinjaScript)
- **Función**: Conectar estrategias de NT8 con Aethelgard
- **Comunicación**: WebSocket hacia `ws://localhost:8000/ws/NT/{client_id}`
- **Formato**: JSON con estructura `Signal`

##### `bridge_mt5.py` - Bridge para MetaTrader 5
- **Lenguaje**: Python
- **Función**: Conectar Expert Advisors de MT5 con Aethelgard
- **Comunicación**: WebSocket hacia `ws://localhost:8000/ws/MT5/{client_id}`
- **Formato**: JSON con estructura `Signal`

##### `mt5_data_provider.py` - Ingestión autónoma de datos OHLC (MT5)
- **Lenguaje**: Python
- **Función**: Obtener OHLC de forma autónoma vía `mt5.copy_rates_from_pos`, **sin gráficas abiertas**. Usado por el Escáner Proactivo.
- **Interface**: `fetch_ohlc(symbol, timeframe, count)` → `DataFrame` con columnas `time`, `open`, `high`, `low`, `close`.
- **Requisitos**: MT5 en ejecución; símbolos en Market Watch. Timeframes: M1, M5, M15, M30, H1, H4, D1, W1, MN1.

##### `generic_data_provider.py` - Proveedor de Datos Genérico (Yahoo Finance)
- **Lenguaje**: Python
- **Función**: Obtener datos OHLC de Yahoo Finance mediante `yfinance`
- **Ventajas**: 100% gratuito, sin API key, autónomo
- **Soporta**: Stocks, Forex, Crypto, Commodities, Índices
- **Interface**: `fetch_ohlc(symbol, timeframe, count)` → `DataFrame` con OHLC

##### Sistema Multi-Proveedor de Datos

**DataProviderManager** (`core_brain/data_provider_manager.py`): Sistema centralizado para gestionar múltiples proveedores de datos con fallback automático.

**Proveedores Disponibles:**

1. **Yahoo Finance** (Gratuito, sin API key)
   - Prioridad: 100 (más alta)
   - Soporta: Stocks, Forex, Crypto, Commodities, Índices
   - Sin límites de requests
   - Librería: `yfinance`

2. **CCXT** (Gratuito, sin API key)
   - Prioridad: 90
   - Soporta: Crypto (100+ exchanges)
   - Exchange por defecto: Binance
   - Librería: `ccxt`

3. **Alpha Vantage** (Gratuito con API key)
   - Prioridad: 80
   - Soporta: Stocks, Forex, Crypto
   - Límite: 500 requests/día
   - Registrarse: https://www.alphavantage.co/support/#api-key
   - Librería: `requests`

4. **Twelve Data** (Gratuito con API key)
   - Prioridad: 70
   - Soporta: Stocks, Forex, Crypto, Commodities
   - Límite: 800 requests/día
   - Registrarse: https://twelvedata.com/pricing
   - Librería: `requests`

5. **Polygon.io** (Gratuito con API key)
   - Prioridad: 60
   - Soporta: Stocks, Forex, Crypto, Options
   - Datos con delay en tier gratuito
   - Registrarse: https://polygon.io/
   - Librería: `requests`

6. **MetaTrader 5** (Requiere instalación local)
   - Prioridad: 95
   - Soporta: Forex, Stocks, Commodities, Índices
   - Requiere: MT5 instalado y configurado
   - Librería: `MetaTrader5`

**Características del Sistema Multi-Proveedor:**
- ✅ **Fallback Automático**: Si falla el proveedor principal, usa el siguiente
- ✅ **Priorización Inteligente**: Selección basada en prioridad y disponibilidad
- ✅ **Gestión desde Dashboard**: Activar/desactivar proveedores desde UI
- ✅ **Configuración Persistente**: Settings guardados en `config/data_providers.json`
- ✅ **Detección de Tipo**: Selección automática del mejor proveedor según símbolo
- ✅ **Sin Vendor Lock-in**: Cambio de proveedor sin modificar código del core

**Uso del DataProviderManager:**

```python
from core_brain.data_provider_manager import DataProviderManager

# Inicializar manager
manager = DataProviderManager()

# Obtener mejor proveedor disponible
provider = manager.get_best_provider()

# Obtener datos con fallback automático
data = manager.fetch_ohlc("AAPL", timeframe="M5", count=500)

# Habilitar/deshabilitar proveedores
manager.enable_provider("alphavantage")
manager.disable_provider("yahoo")

# Configurar API keys
manager.configure_provider("alphavantage", api_key="YOUR_KEY_HERE")
```

##### `webhook_tv.py` - Webhook para TradingView
- **Lenguaje**: Python
- **Función**: Recibir alertas de TradingView
- **Comunicación**: HTTP POST hacia `http://localhost:8000/api/signal`
- **Puerto**: 8001 (servidor independiente)

#### 3. **Data Vault** (`data_vault/`)

##### `storage.py` - Sistema de Persistencia SQLite
- **Base de Datos**: `data_vault/aethelgard.db`
- **Tablas**:
  - `signals`: Todas las señales recibidas
  - `signal_results`: Resultados y feedback de señales ejecutadas
  - `market_states`: Estados completos de mercado (para aprendizaje)

**Funcionalidades:**
- Guardar señales con régimen detectado
- Registrar resultados de trades (PNL, feedback)
- Almacenar estados de mercado con todos los indicadores
- Consultas para análisis histórico y auto-calibración

#### 4. **Models** (`models/`)

##### `signal.py` - Modelos de Datos Pydantic
- **Signal**: Modelo de señal recibida
- **SignalResult**: Modelo de resultado de trade
- **MarketRegime**: Enum de regímenes (TREND, RANGE, CRASH, NEUTRAL)
- **ConnectorType**: Enum de conectores (NT, MT5, TV)
- **SignalType**: Enum de tipos de señal (BUY, SELL, CLOSE, MODIFY)

---

## 🤖 Reglas de Autonomía

### 1. Auto-Calibración

**Principio**: Ningún parámetro numérico debe considerarse estático.

#### Parámetros Auto-Calibrables

- **Umbrales ADX**:
  - `adx_trend_threshold`: Umbral para entrar en TREND (default: 25.0)
  - `adx_range_threshold`: Umbral para entrar en RANGE (default: 20.0)
  - `adx_range_exit_threshold`: Umbral para salir de TREND (default: 18.0)
- **Volatilidad**:
  - `volatility_shock_multiplier`: Multiplicador para detectar CRASH (default: 5.0)
  - `min_volatility_atr_period`: Período ATR base (default: 50)
- **Persistencia**:
  - `persistence_candles`: Velas consecutivas para confirmar cambio (default: 2)

#### Proceso de Auto-Calibración

1. **Recolección de Datos**: El sistema almacena todos los estados de mercado en `market_states`
2. **Análisis Histórico**: `ParameterTuner` analiza los últimos N registros (default: 1000)
3. **Cálculo de Falsos Positivos**: Evalúa cambios de régimen que se revirtieron en 5-10 velas
4. **Optimización**: Busca umbrales que minimicen la tasa de falsos positivos
5. **Actualización**: Guarda nuevos parámetros en `config/dynamic_params.json`
6. **Aplicación**: `RegimeClassifier` recarga parámetros automáticamente

**Ejecución Manual:**
```python
from core_brain.tuner import ParameterTuner
from data_vault.storage import StorageManager

storage = StorageManager()
tuner = ParameterTuner(storage)
new_params = tuner.auto_calibrate(limit=1000)
```

### 2. Patrón de Orquestador Resiliente

**Principio**: El sistema debe recuperarse automáticamente de fallos sin pérdida de datos críticos.

#### Arquitectura de Resiliencia

El **Orquestador Resiliente** implementa tres capas de protección:

**1. Persistencia Inmediata (Zero Data Loss)**
```python
# Tras ejecutar una señal, persistir INMEDIATAMENTE a DB
if success:
    signal_id = self.storage.save_signal(signal)
    logger.info(f"Signal persisted: {signal_id}")
    self.stats.signals_executed += 1
```

**2. Reconstrucción de Estado (Crash Recovery)**
```python
# Al inicializar SessionStats, reconstruir desde DB
@classmethod
def from_storage(cls, storage: StorageManager) -> 'SessionStats':
    today = date.today()
    
    # Consultar DB para contar señales ejecutadas hoy
    executed_count = storage.count_executed_signals(today)
    
    # Restaurar estadísticas si existen
    system_state = storage.get_system_state()
    session_data = system_state.get("session_stats", {})
    
    # Reconstruir objeto con datos persistidos
    return cls(
        date=today,
        signals_executed=executed_count,  # Siempre desde DB
        signals_processed=session_data.get("signals_processed", 0),
        ...
    )
```

**3. Latido de Guardia Adaptativo (Adaptive Heartbeat)**
```python
def _get_sleep_interval(self) -> int:
    base_interval = self.intervals.get(self.current_regime, 30)
    
    # Si hay señales activas, reducir sleep a 3 segundos
    if self._active_signals:
        return min(base_interval, self.MIN_SLEEP_INTERVAL)
    
    return base_interval
```

#### Flujo de Recuperación tras Crash

```
┌─────────────────┐
│  Sistema Inicia │
│   (o Reinicia)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ SessionStats.from_storage(storage)      │
│  1. Consulta count_executed_signals()   │
│  2. Lee session_stats de system_state   │
│  3. Reconstruye objeto con datos reales │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Orquestador Operacional                 │
│  • Todos los trades del día recuperados │
│  • Estadísticas correctas               │
│  • Sin pérdida de información           │
└─────────────────────────────────────────┘
```

#### Garantías del Orquestador Resiliente

✅ **No Dual-Execution**: Cada señal se ejecuta y persiste una única vez  
✅ **Idempotencia**: Reiniciar el sistema no duplica trades  
✅ **Auditabilidad**: Todos los trades en DB con timestamp y detalles completos  
✅ **Recovery < 1s**: Tiempo de recuperación tras crash inferior a 1 segundo  
✅ **Production-Grade**: Diseñado para operar 24/7 sin intervención humana  

#### Tests de Resiliencia

Ver `tests/test_orchestrator_recovery.py`:
- `test_session_stats_reconstruction_from_db`: Verifica reconstrucción completa
- `test_orchestrator_recovery_after_crash`: Simula crash y valida recuperación
- `test_persistence_after_execution`: Confirma persistencia inmediata
- `test_adaptive_heartbeat_with_signals`: Valida latido adaptativo

### 3. Feedback Loop Obligatorio

**Principio**: Cada decisión debe ser contrastada con el resultado del mercado.

#### Ciclo de Feedback

```
┌─────────────┐
│   Señal     │
│  Generada   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Clasificar │
│   Régimen   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Ejecutar   │
│  Estrategia │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌─────────────┐
│  Registrar  │─────▶│  Evaluar    │
│  Resultado  │      │  Resultado  │
└─────────────┘      └──────┬──────┘
                            │
                            ▼
                    ┌─────────────┐
                    │  Ajustar    │
                    │ Parámetros  │
                    └─────────────┘
```

#### Ventanas de Evaluación

El sistema evalúa resultados en múltiples horizontes temporales:
- **5 velas**: Resultado inmediato
- **10 velas**: Resultado a corto plazo
- **20 velas**: Resultado a medio plazo

#### Métricas de Feedback

- **PNL (Profit and Loss)**: Resultado financiero del trade
- **Feedback Score**: Puntuación 0-1 basada en:
  - Ejecución exitosa
  - PNL positivo/negativo
  - Persistencia del régimen detectado
  - Precisión de la estrategia activada

### 3. Aprendizaje Continuo

**Principio**: El sistema debe mejorar autónomamente con el tiempo.

#### Proceso de Auto-Tune

1. **Re-ejecución de Tests**: El sistema re-ejecuta tests de sensibilidad sobre datos históricos
2. **Análisis de Patrones**: Identifica qué combinaciones de parámetros funcionaron mejor
3. **Propuesta de Mejoras**: Sugiere nuevos parámetros basándose en evidencia estadística
4. **Validación**: Verifica que los nuevos parámetros no degraden el rendimiento

#### Detección de Drift

El sistema debe detectar cuando sus predicciones están fallando:
- **Métrica**: Tasa de acierto de clasificación de régimen
- **Umbral**: Si la tasa cae por debajo de un umbral (ej. 60%), activar modo seguridad
- **Acción**: Reducir exposición, aumentar filtros, o detener trading

### 4. Independencia y Modo Seguridad

**Principio**: El sistema debe ser capaz de protegerse sin intervención humana.

#### Condiciones para Modo Seguridad

- Tasa de acierto de régimen < umbral crítico
- Serie de pérdidas consecutivas > límite
- Volatilidad extrema detectada (CRASH)
- Error en comunicación con conectores

#### Acciones en Modo Seguridad

- Cerrar posiciones abiertas
- Suspender nuevas señales
- Notificar al operador
- Registrar evento para análisis posterior

---

## 🗺️ Roadmap de Implementación

### Fase 1: Infraestructura Base ✅ **COMPLETADA**

**Objetivo**: Establecer la arquitectura fundamental del sistema.

**Componentes Implementados:**
- ✅ Servidor FastAPI con WebSockets (`core_brain/server.py`)
- ✅ Clasificador de Régimen de Mercado (`core_brain/regime.py`)
- ✅ Sistema de persistencia SQLite (`data_vault/storage.py`)
- ✅ Modelos de datos Pydantic (`models/signal.py`)
- ✅ Conectores básicos (NT8, MT5, TradingView)
- ✅ Sistema de auto-calibración (`core_brain/tuner.py`)

**Funcionalidades:**
- Recepción de señales desde múltiples plataformas
- Clasificación de régimen en tiempo real
- Almacenamiento de señales y estados de mercado
- Auto-calibración de parámetros ADX y volatilidad

---

### Fase 1.1: Escáner Proactivo Multihilo ✅ **COMPLETADA** (Enero 2026)

**Objetivo**: Transformar Aethelgard en un **escáner proactivo** que obtenga datos de forma autónoma y escanee múltiples activos en paralelo, con control de recursos y priorización por régimen.

**Componentes implementados:**
- ✅ **`core_brain/scanner.py`**: `ScannerEngine` (orquestador), `CPUMonitor`, protocolo `DataProvider`. Multithreading con `concurrent.futures.ThreadPoolExecutor`.
- ✅ **`connectors/mt5_data_provider.py`**: Ingestión autónoma OHLC vía `mt5.copy_rates_from_pos` (sin gráficas abiertas).
- ✅ **`config/config.json`**: Configuración del escáner (`assets`, `cpu_limit_pct`, `sleep_trend_seconds`, `sleep_range_seconds`, etc.).
- ✅ **`RegimeClassifier.load_ohlc(df)`**: Carga masiva OHLC para uso en escáner.
- ✅ **`run_scanner.py`**: Entrypoint del escáner con MT5. `test_scanner_mock.py`: test con DataProvider mock (sin MT5).

**Funcionalidades:**
- Lista de activos configurable; un `RegimeClassifier` por símbolo.
- Escaneo en hilos separados por activo.
- **Control de recursos**: si CPU > `cpu_limit_pct` (configurable), aumenta el sleep entre ciclos.
- **Priorización**: TREND/CRASH cada 1 s, RANGE cada 10 s, NEUTRAL cada 5 s (configurables).
- Agnóstico de plataforma: el escáner recibe un `DataProvider` inyectado (p. ej. MT5).

---

### Fase 2: Implementación de Estrategias Modulares 🚧 **EN PROGRESO**

**Objetivo**: Implementar estrategias modulares que se activen según el régimen detectado.

#### 2.1 Estrategias de Oliver Vélez

**Estado**: Pendiente de implementación

**Estrategias a Implementar:**
- **Trend Following**: Para régimen TREND
- **Range Trading**: Para régimen RANGE
- **Breakout Trading**: Para transiciones de régimen
- **Risk Management**: Gestión de riesgo dinámica según volatilidad

#### 2.2 Gestión de Riesgo Dinámica

**Estado**: Pendiente de implementación

**Componentes:**
- Cálculo de tamaño de posición basado en volatilidad (ATR)
- Stop Loss dinámico según régimen
- Take Profit adaptativo
- Gestión de drawdown máximo

#### 2.3 Sistema de Activación de Estrategias

**Estado**: Pendiente de implementación

**Lógica:**
```python
def activate_strategy(regime: MarketRegime, symbol: str):
    if regime == MarketRegime.TREND:
        return trend_following_strategy(symbol)
    elif regime == MarketRegime.RANGE:
        return range_trading_strategy(symbol)
    elif regime == MarketRegime.CRASH:
        return safety_mode()  # No trading en crashes
    else:
        return None  # Esperar más datos
```

---

### Fase 3: Feedback Loop y Aprendizaje Autónomo ✅ **COMPLETADA**

**Objetivo**: Implementar ciclo completo de feedback y aprendizaje basado en resultados reales.

**Fecha de Implementación**: Enero 2026

#### 3.1 Feedback Loop de Resultados ✅

**Componentes Implementados:**

##### ClosingMonitor (`core_brain/monitor.py`)
- **Función**: Monitorea señales ejecutadas y actualiza la DB con resultados reales del broker
- **Características**:
  - Verificación periódica de posiciones cerradas (cada 60 segundos por defecto)
  - Consulta automática al historial de órdenes de MT5/NT8
  - Cálculo automático de PIPs (adaptado por tipo de instrumento: Forex, JPY, Gold)
  - Detección inteligente del motivo de cierre (TAKE_PROFIT, STOP_LOSS, MANUAL)
  - Actualización en tiempo real de la tabla `trades` en SQLite
  
- **Workflow**:
  1. El monitor detecta señales con estado `EXECUTED` en la DB
  2. Consulta a los conectores (`MT5Bridge.get_closed_positions()`) por órdenes cerradas
  3. Empareja órdenes cerradas con señales mediante ticket o signal_id
  4. Calcula PIPs, profit real, duración y resultado (win/loss)
  5. Actualiza señal a estado `CLOSED` y registra resultado en tabla `trades`

##### Extensiones de StorageManager (`data_vault/storage.py`)

**Métodos Nuevos**:
- `get_signals_by_status(status)`: Obtiene señales filtradas por estado (ej. EXECUTED)
- `get_signal_by_id(signal_id)`: Recupera señal específica para actualización
- `update_signal_status(signal_id, status, metadata)`: Actualiza estado de señal con metadatos
- `get_win_rate(symbol, days)`: Calcula Win Rate % basado en trades reales
- `get_total_profit(symbol, days)`: Suma profit/loss de trades cerrados
- `get_profit_by_symbol(days)`: Análisis detallado por activo (profit, win rate, pips)
- `get_all_trades(limit)`: Obtiene historial completo de trades cerrados

##### MT5Bridge Enhancement (`connectors/bridge_mt5.py`)

**Método Nuevo**:
- `get_closed_positions(hours)`: Obtiene posiciones cerradas del historial de MT5
  - Consulta a `mt5.history_deals_get()` con rango de tiempo
  - Filtra deals por magic number de Aethelgard
  - Identifica entry/exit deals para reconstruir posiciones completas
  - Extrae entry_price, exit_price, profit, exit_reason automáticamente
  - Detecta razón de cierre (TP/SL/Manual) mediante análisis del comentario

#### 3.2 Dashboard de Análisis Avanzado ✅

**Nueva Pestaña: 💰 Análisis de Activos**

**KPIs Principales** (calculados desde datos reales):
- **Profit Total**: Suma de ganancias/pérdidas de todos los trades
- **Win Rate %**: Porcentaje de trades ganadores sobre total
- **Total Trades**: Número de operaciones cerradas
- **Profit Promedio**: Ganancia promedio por trade

**Gráficos Interactivos** (Plotly):
- **Gráfico de Barras**: Profit acumulado por símbolo (código de color verde/rojo)
- **Tabla Detallada**: Por cada activo muestra:
  - Símbolo
  - Total de trades
  - Win Rate %
  - Profit Total
  - Profit Promedio
  - PIPs Totales
  - Resultado visual (🟢 Ganador / 🔴 Perdedor)

**Tabla de Señales con Resultado Real**:
- Lista de últimos 20 trades cerrados
- Muestra: Símbolo, Entrada, Salida, PIPs, Profit, Razón de Salida, Fecha
- Colores condicionales: Verde para trades ganados, Rojo para perdidos
- Filtro de período (1-90 días)

#### 3.3 Integración del Monitor en el Sistema

**Uso en Producción**:
```python
from core_brain.monitor import ClosingMonitor
from connectors.bridge_mt5 import MT5Bridge

# Inicializar monitor con conectores
mt5_connector = MT5Bridge()
monitor = ClosingMonitor(
    storage=storage,
    connectors={'MT5': mt5_connector},
    interval_seconds=60
)

# Ejecutar como tarea asíncrona
await monitor.start()
```

**Tests Implementados** (`tests/test_monitor.py`):
- ✅ Verificación de inicialización correcta
- ✅ Actualización de trades en DB desde posiciones cerradas
- ✅ Cálculo correcto de PIPs para diferentes instrumentos (EUR/USD, USD/JPY, XAU/USD)
- ✅ Clasificación correcta de trades ganados/perdidos
- ✅ Manejo robusto de errores de conexión con brokers
- ✅ Loop asíncrono de monitoreo continuo

**Dependencias Agregadas**:
- `plotly>=5.18.0` (para gráficos interactivos en Dashboard)

#### Impacto en el Sistema

**Antes del Feedback Loop**:
- Señales ejecutadas sin seguimiento post-ejecución
- Win Rate y profit calculados con datos simulados
- Imposible medir rendimiento real por activo
- Sin datos para optimización del Tuner

**Después del Feedback Loop**:
- ✅ Tracking automático de todos los trades cerrados
- ✅ KPIs calculados con datos reales del broker
- ✅ Análisis detallado de rentabilidad por símbolo
- ✅ Base de datos robusta para análisis histórico
- ✅ Datos reales alimentan el ParameterTuner para auto-calibración
- ✅ Visibilidad completa del rendimiento en Dashboard

**Próximos Pasos (Aprendizaje Avanzado)**:
- Integrar resultados en ParameterTuner para ajuste automático de umbrales
- Implementar sistema de scoring de estrategias basado en win rate real
- Crear alertas automáticas ante degradación de rendimiento
- Desarrollar modelo predictivo de éxito de señales basado en histórico

---

### Fase 4: Evolución Comercial 🎯 **FUTURA**

**Objetivo**: Transformar Aethelgard en un sistema comercial multi-usuario con capacidades avanzadas de gestión y monitoreo.

#### 4.1 Multi-Tenant System

**Estado**: Pendiente de implementación

**Objetivo**: Capacidad para gestionar múltiples cuentas de usuario de forma aislada.

**Componentes:**
- Sistema de autenticación y autorización (JWT tokens)
- Aislamiento de datos por usuario/tenant
- Gestión de cuotas y límites por cuenta
- Base de datos multi-tenant con esquemas separados o filtrado por tenant_id
- API de gestión de usuarios y permisos

**Arquitectura:**
- Cada usuario tiene su propio espacio de datos aislado
- Señales, resultados y estados de mercado separados por tenant
- Configuración de parámetros independiente por usuario
- Límites de recursos configurables (número de señales, estrategias activas, etc.)

#### 4.2 Módulos bajo Demanda

**Estado**: Pendiente de implementación

**Objetivo**: Activación/Desactivación de estrategias mediante una API Key.

**Componentes:**
- Sistema de API Keys por usuario
- Gestión de suscripciones a estrategias específicas
- Activación/desactivación dinámica de módulos
- Middleware de validación de API Key en endpoints
- Dashboard de gestión de suscripciones

**Funcionalidades:**
- Cada usuario recibe una API Key única
- Activación selectiva de estrategias (Trend Following, Range Trading, etc.)
- Control granular de permisos por estrategia
- Facturación basada en estrategias activas (si aplica)
- Logs de uso por API Key para auditoría

#### 4.3 Sistema de Notificaciones

**Estado**: Pendiente de implementación

**Objetivo**: Integración con Telegram/Discord para alertas de señales en tiempo real.

**Componentes:**
- Integración con Telegram Bot API
- Integración con Discord Webhooks
- Sistema de plantillas de mensajes personalizables
- Configuración de notificaciones por usuario
- Filtros de notificación (por régimen, por estrategia, por símbolo)

**Tipos de Notificaciones:**
- **Señales de Trading**: Alertas cuando se genera una señal
- **Cambios de Régimen**: Notificación de transiciones de régimen
- **Resultados de Trades**: Resumen de PNL y resultados
- **Alertas del Sistema**: Modo seguridad, errores críticos, drift detectado
- **Métricas Diarias**: Resumen de rendimiento del día

**Configuración:**
- Preferencias de notificación por usuario
- Horarios de notificación (evitar spam fuera de horario)
- Umbrales personalizables (solo notificar si PNL > X, etc.)

#### 4.4 Web Dashboard

**Estado**: Pendiente de implementación

**Objetivo**: Interfaz en Streamlit o React para visualizar el rendimiento y el régimen de mercado actual.

**Tecnología**: Streamlit (rápido) o React (más flexible para producción)

**Funcionalidades Principales:**

**Panel de Control:**
- Estado del sistema en tiempo real
- Conexiones activas (NT8, MT5, TradingView)
- Régimen de mercado actual por símbolo
- Métricas de rendimiento (win rate, PNL, Sharpe ratio)

**Visualización de Régimen:**
- Gráficos de evolución de régimen en tiempo real
- Indicadores técnicos (ADX, volatilidad, SMA distance)
- Histórico de cambios de régimen
- Comparativa de precisión de clasificación

**Gestión de Estrategias:**
- Lista de estrategias activas/inactivas
- Activación/desactivación de módulos
- Configuración de parámetros por estrategia
- Histórico de ejecuciones

**Análisis de Rendimiento:**
- Gráficos de PNL acumulado
- Análisis por régimen (qué régimen es más rentable)
- Análisis por estrategia (rendimiento comparativo)
- Métricas de riesgo (drawdown, volatilidad de retornos)

**Gestión de Usuarios (Multi-Tenant):**
- Panel de administración de usuarios
- Gestión de API Keys
- Configuración de permisos y suscripciones
- Logs de actividad por usuario

**Características Técnicas:**
- Actualización en tiempo real (WebSockets o polling)
- Responsive design (móvil y desktop)
- Exportación de datos (CSV, PDF reports)
- Filtros avanzados y búsqueda

---

## 📊 Estrategias

### Signal Factory - Lógica de Decisión Dinámica ✅ IMPLEMENTADO (Enero 2026)

**Estado**: ✅ Implementado y funcional en `core_brain/signal_factory.py`

Motor de generación de señales basado en la **estrategia de Oliver Vélez** para swing trading, con sistema de scoring matemático (0-100) y filtrado por membresía.

#### Sistema de Scoring

Evaluación cuantitativa de oportunidades de trading:

| Criterio | Puntos | Descripción |
|----------|--------|-------------|
| **Régimen TREND** | +30 | Mercado en tendencia clara (ADX > 25) |
| **Vela Elefante** | +20 | Vela de alto momentum (rango > 2x ATR) |
| **Volumen Alto** | +20 | Volumen superior al promedio 20 períodos |
| **Cerca de SMA 20** | +30 | Precio rebotando en zona soporte/resistencia (±1%) |

**Fórmula**:
```
Score = (Régimen TREND ? 30 : 0) +
        (Vela Elefante ? 20 : 0) +
        (Volumen Alto ? 20 : 0) +
        (Cerca SMA 20 ? 30 : 0)

Total: 0-100 puntos
```

#### Filtrado por Membresía

Sistema de tres niveles que determina acceso a señales según calidad:

| Tier | Score Mínimo | Descripción |
|------|--------------|-------------|
| **FREE** | 0-79 | Señales básicas, disponibles para todos |
| **PREMIUM** | 80-89 | Señales de alta calidad (4 criterios cumplidos) |
| **ELITE** | 90-100 | Señales excepcionales (todos los criterios) |

**Implementación**:
- `models/signal.py`: Enum `MembershipTier` y campos de scoring
- `signal_factory.py`: Métodos `_calculate_score()` y `filter_by_membership()`
- Dashboard/Telegram: Listo para filtrado de señales por tier de usuario

#### Integración MT5 - Auto-Ejecución

**Bridge MT5 actualizado** (`connectors/bridge_mt5.py`):
- ✅ Recepción de señales desde Signal Factory
- ✅ Ejecución automática BUY/SELL en cuentas DEMO
- ✅ Verificación de seguridad (solo DEMO por defecto)
- ✅ Tracking de posiciones activas y resultados
- ✅ Cálculo automático de SL/TP (Risk/Reward 1:2)
- ✅ Registro en `signal_results` para feedback loop

**Parámetros de Seguridad**:
```python
auto_execute=True   # Habilitar auto-ejecución
demo_mode=True      # Solo ejecutar en DEMO (protección)
magic_number=234000 # ID único Aethelgard
```

#### Componentes Técnicos

**Indicadores utilizados**:
- ATR (14): Volatilidad y cálculo de SL/TP
- SMA (20): Zonas de soporte/resistencia
- Volumen: Confirmación de movimientos
- Análisis de velas: Detección de momentum (Velas Elefante)

**Métodos principales**:
```python
SignalFactory.generate_signal()        # Genera señal para un símbolo
SignalFactory.generate_signals_batch() # Procesa múltiples símbolos
SignalFactory.filter_by_membership()   # Filtra por tier usuario
SignalFactory._calculate_score()       # Calcula score 0-100
SignalFactory._is_elephant_candle()    # Detecta velas de momentum
SignalFactory._is_volume_above_average() # Analiza volumen
SignalFactory._is_near_sma20()         # Verifica proximidad SMA
```

**Archivos**:
- `core_brain/signal_factory.py`: Motor completo (580 líneas)
- `example_live_system.py`: Sistema integrado Scanner + Signal Factory + MT5
- `test_signal_factory.py`: Suite de tests del scoring

---

### Risk Manager - Gestión de Riesgo Agnóstica y Resiliente ✅ IMPLEMENTADO (Enero 2026, v2.0)

**Estado**: ✅ Refactorizado y testeado para cumplir con los principios de Autonomía y Resiliencia.

Módulo de gestión de riesgo que implementa position sizing dinámico y agnóstico, y un modo de protección `Lockdown` persistente que sobrevive a reinicios del sistema.

#### Características Principales

**1. Position Sizing Agnóstico y Auto-Ajustable**
- **Riesgo Dinámico**: El riesgo por operación (`risk_per_trade`) no es estático. Se carga desde `config/dynamic_params.json`, permitiendo que el **`tuner.py`** lo modifique basándose en el análisis del rendimiento histórico almacenado en `data_vault`.
- **Cálculo Agnóstico**: El tamaño de la posición se calcula de forma universal, aceptando un `point_value` explícito. Esto permite que funcione igual para un lote de Forex (valor por pip) que para un contrato de Futuros (valor por punto) sin cambiar la lógica.
- **Reducción por Régimen**: El riesgo se reduce automáticamente a la mitad en regímenes de alta incertidumbre (RANGE, CRASH).

**2. Lockdown Mode Persistente**
- **Activación**: Se activa automáticamente tras un número configurable de pérdidas consecutivas (leído desde `dynamic_params.json`).
- **Persistencia**: Al activarse o desactivarse, el estado de `Lockdown` **se escribe inmediatamente en la base de datos** (`data_vault`) a través del `StorageManager`.
- **Recuperación Autónoma**: Si el sistema se reinicia, el `RiskManager` **recupera el estado de Lockdown desde la base de datos** al inicializarse. Esto garantiza que el sistema permanezca en modo seguro aunque haya un fallo o reinicio, cumpliendo el principio de Independencia.

**3. Resiliencia de Datos**
- Adopta una postura defensiva (tamaño de posición `0`) si el régimen de mercado llega como `None`, evitando fallos por datos inesperados.

#### Métodos Principales

```python
RiskManager.calculate_position_size(account_balance, stop_loss_distance, point_value, current_regime)
RiskManager.record_trade_result()      # Registra resultado y actualiza estado de lockdown
RiskManager._activate_lockdown()       # Activa y persiste el lockdown
RiskManager._deactivate_lockdown()     # Desactiva y persiste el lockdown
```

#### Reglas de Riesgo

| Régimen | Multiplicador de Riesgo | Lógica |
|---------|-------------------------|--------|
| **TREND** | 1.0x | Condiciones óptimas, riesgo base |
| **NEUTRAL** | 1.0x | Riesgo base |
| **RANGE** | 0.5x | Alta incertidumbre, riesgo reducido |
| **CRASH** | 0.5x | Volatilidad extrema, riesgo reducido |

**Fórmula de Position Sizing (Agnóstica)**:
```
# Risk per trade es cargado dinámicamente
RiskAmount = AccountBalance * risk_per_trade * RegimeMultiplier
ValueAtRisk = StopLossDistance * PointValue
PositionSize = RiskAmount / ValueAtRisk
```

#### Protección Lockdown

**Activación**:
- `N` pérdidas consecutivas → Lockdown activado.
- El estado `{'lockdown_mode': True}` se guarda en la base de datos.
- `calculate_position_size()` retorna `0`.

**Desactivación**:
- Manual o por reglas custom (ej. 1 operación ganadora).
- El estado `{'lockdown_mode': False}` se actualiza en la base de datos.

#### Tests Implementados (Suite TDD Completa)

**Test Suite** (`tests/test_risk_manager.py`):
- ✅ **Agnosticismo**: Cálculo correcto para Futuros (puntos) y Forex (pips).
- ✅ **Auto-Ajuste**: Carga correcta del `risk_per_trade` desde `dynamic_params.json`.
- ✅ **Persistencia de Lockdown**: Verifica que el estado de lockdown se recupera al instanciar un nuevo `RiskManager`.
- ✅ **Resiliencia**: Devuelve `0` si el régimen es `None`.
- ✅ Activación de lockdown tras N pérdidas.
- ✅ Reducción de riesgo en RANGE/CRASH.
- ✅ Actualización de capital y estado general.

---

### Order Executor - Ejecución de Señales con Validación y Resiliencia ✅ IMPLEMENTADO (Enero 2026, v1.0)

**Estado**: ✅ Implementado siguiendo TDD con suite completa de tests.

Módulo de ejecución de órdenes que actúa como el **brazo ejecutor** de Aethelgard. Valida señales con RiskManager, enruta a conectores usando Factory Pattern, y maneja fallos con resiliencia.

#### Características Principales

**1. Validación por RiskManager**
- **Última Verificación**: Antes de enviar cualquier orden, consulta `RiskManager.is_locked()`.
- **Bloqueo Automático**: Si el sistema está en lockdown, rechaza la señal y registra el intento en `data_vault` como `REJECTED_LOCKDOWN`.
- **Retorno Explícito**: `execute_signal()` retorna `False` cuando la señal es bloqueada.

**2. Factory Pattern para Conectores (Agnosticismo)**
- **Routing Dinámico**: Basado en el `ConnectorType` de la señal, delega la ejecución al conector apropiado:
  - `ConnectorType.METATRADER5` → `mt5_connector`
  - `ConnectorType.NINJATRADER8` → `nt8_connector`
  - `ConnectorType.WEBHOOK` → `webhook_connector`
- **Independencia del Core**: El `OrderExecutor` no importa librerías de brokers, mantiene el cerebro agnóstico.
- **Manejo de Conectores Faltantes**: Si un conector no está configurado, rechaza la señal con notificación.

**3. Resiliencia ante Fallos de Conexión**
- **Captura de Errores**: Captura `ConnectionError` y excepciones generales del conector.
- **Registro en Data Vault**: Marca señales fallidas como `REJECTED_CONNECTION` en la base de datos.
- **Notificación Inmediata a Telegram**: Envía alerta urgente con detalles del fallo:
  - Símbolo
  - Acción (BUY/SELL)
  - Conector que falló
  - Mensaje de error
  - Timestamp

**4. Audit Trail Completo**
- **Estado PENDING**: Registra cada señal como `PENDING` antes de ejecutar.
- **Estado EXECUTED**: Marca señales exitosas con `order_id` del broker.
- **Estado REJECTED**: Guarda motivo de rechazo (LOCKDOWN, INVALID_DATA, CONNECTION).

**5. Validación de Datos (Seguridad)**
- Verifica campos requeridos (`symbol`, `signal_type`, `connector_type`).
- Valida `confidence` en rango [0.0, 1.0].
- Rechaza `signal_type` inválidos (solo BUY, SELL, HOLD).

#### Métodos Principales

```python
OrderExecutor.execute_signal(signal: Signal) -> bool
    # Flujo completo: validar → checkear lockdown → registrar PENDING → 
    # enrutar a conector → manejar fallo → notificar

OrderExecutor._validate_signal(signal: Signal) -> bool
    # Validación de datos de entrada

OrderExecutor._get_connector(connector_type: ConnectorType) -> Optional[Connector]
    # Factory Pattern: retorna el conector apropiado

OrderExecutor._register_pending_signal(signal: Signal)
    # Registra señal con estado PENDING en data_vault

OrderExecutor._handle_connector_failure(signal: Signal, error_message: str)
    # Maneja fallos: registra REJECTED_CONNECTION + notifica Telegram

OrderExecutor.get_status() -> Dict
    # Retorna estado: conectores disponibles, lockdown, notificaciones
```

#### Flujo de Ejecución

```
┌─────────────────┐
│  Signal Input   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Validate Signal Data   │ ◄─── Seguridad: validar todas las entradas externas
└────────┬────────────────┘
         │
         ▼
┌──────────────────────────┐
│ RiskManager.is_locked()? │ ◄─── Última consulta antes de ejecutar
└────┬────────────┬────────┘
     │ YES        │ NO
     │            │
     ▼            ▼
┌──────────┐  ┌─────────────────┐
│ REJECTED │  │ Register PENDING│ ◄─── Audit trail
│ Return   │  └────────┬────────┘
│ False    │           │
└──────────┘           ▼
              ┌────────────────────┐
              │ Factory: Get       │ ◄─── Agnosticismo
              │ Connector by Type  │
              └────────┬───────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │ connector.execute() │
              └────┬────────┬───────┘
                   │ SUCCESS│ FAIL
                   │        │
                   ▼        ▼
         ┌──────────┐  ┌────────────────────┐
         │ EXECUTED │  │ REJECTED_CONNECTION│ ◄─── Resiliencia
         │ Return   │  │ + Telegram Alert   │
         │ True     │  │ Return False       │
         └──────────┘  └────────────────────┘
```

#### Tests Implementados (Suite TDD Completa)

**Test Suite** (`tests/test_executor.py`):
1. ✅ **Bloqueo por RiskManager**: Verifica que `execute_signal()` retorna `False` cuando `is_locked() == True` y registra intento fallido.
2. ✅ **Envío Exitoso**: Señal enviada correctamente cuando RiskManager permite.
3. ✅ **Factory Pattern**: Enrutamiento correcto a MT5 y NT8 según `ConnectorType`.
4. ✅ **Resiliencia ante Fallos**: Maneja `ConnectionError`, registra como `REJECTED_CONNECTION`, notifica a Telegram.
5. ✅ **Registro PENDING**: Verifica que cada señal se marca como `PENDING` antes de ejecutar.
6. ✅ **Conectores Faltantes**: Maneja conectores no configurados sin crashear.
7. ✅ **Validación de Datos**: Rechaza señales con `confidence` inválida o campos faltantes.

**Ejecución de Tests:**
```bash
.\venv\Scripts\python.exe -m pytest tests/test_executor.py -v
# ====================== 7 passed in 1.01s ======================
```

#### Ejemplo de Uso

```python
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from core_brain.notificator import TelegramNotifier
from models.signal import Signal, ConnectorType

# Setup
risk_manager = RiskManager(initial_capital=10000)
notificator = TelegramNotifier(bot_token="...", basic_chat_id="...")

# Conectores (configurados externamente)
from connectors.bridge_mt5 import MT5Bridge
mt5_bridge = MT5Bridge(symbol="EURUSD", auto_execute=True)

connectors = {
    ConnectorType.METATRADER5: mt5_bridge
}

# Executor
executor = OrderExecutor(
    risk_manager=risk_manager,
    notificator=notificator,
    connectors=connectors
)

# Señal de entrada
signal = Signal(
    symbol="EURUSD",
    signal_type="BUY",
    confidence=0.85,
    connector_type=ConnectorType.METATRADER5,
    entry_price=1.1050,
    stop_loss=1.1000,
    take_profit=1.1150,
    volume=0.01
)

# Ejecutar
success = executor.execute_signal(signal)
if success:
    print("✅ Orden ejecutada")
else:
    print("❌ Orden rechazada (lockdown o fallo de conexión)")
```

#### Integración con Sistema Completo

El `OrderExecutor` se integra en el flujo principal de Aethelgard:

```
Scanner → Signal Factory → RiskManager (sizing) → OrderExecutor → Connector → Broker
   ↓            ↓                ↓                      ↓             ↓          ↓
DataVault   DataVault       DataVault             DataVault     WebSocket   Order
```

---

### Estrategias de Oliver Vélez

#### Activación por Régimen

Las estrategias se activan según el régimen de mercado detectado:

| Régimen | Estrategia Principal | Lógica de Activación |
|---------|---------------------|---------------------|
| **TREND** | Trend Following | ADX > 25, precio en tendencia clara |
| **RANGE** | Range Trading | ADX < 20, precio oscilando entre soportes/resistencias |
| **CRASH** | Safety Mode | Volatilidad extrema detectada, no trading |
| **NEUTRAL** | Wait | Insuficientes datos, esperar más información |

#### Trend Following (Régimen TREND)

**Estado**: ✅ Implementado en Signal Factory

**Estrategia Oliver Vélez - Swing Trading**:

**Principios implementados**:
1. ✅ Operar solo en tendencia (verifica `regime == TREND`)
2. ✅ Buscar velas de momentum (Velas Elefante: rango > 2x ATR)
3. ✅ Confirmar con volumen (volumen > promedio 20 períodos)
4. ✅ Entrar en zonas clave (rebote en SMA 20 como soporte/resistencia)
5. ✅ Risk/Reward favorable (SL: 1.5x ATR, TP: 3x ATR → Ratio 1:2)

**Condiciones de Entrada BUY:**
- Régimen: TREND
- SMA 20 ascendente (uptrend)
- Precio rebota en SMA 20 (de abajo hacia arriba)
- Vela actual cierra por encima de SMA 20
- Vela anterior cerró por debajo o tocó SMA 20
- Score alto = mayor probabilidad de éxito

**Condiciones de Entrada SELL:**
- Régimen: TREND
- SMA 20 descendente (downtrend)
- Precio rechaza en SMA 20 (de arriba hacia abajo)
- Vela actual cierra por debajo de SMA 20
- Vela anterior cerró por encima o tocó SMA 20
- Score alto = mayor probabilidad de éxito

**Gestión de Riesgo:**
- Stop Loss: precio ± (1.5 × ATR)
- Take Profit: precio ± (3.0 × ATR)
- Risk/Reward: 1:2 (objetivo 2x el riesgo)
- Volumen por defecto: 0.01 lotes (ajustable según capital)
- Tamaño de posición: Basado en ATR (mayor volatilidad = menor tamaño)

#### Range Trading (Régimen RANGE)

**Estado**: Pendiente de implementación completa

**Condiciones de Entrada:**
- Régimen: RANGE
- ADX < 20
- Identificación de soportes y resistencias
- Oscilador en extremos (RSI, Stochastic)

**Gestión de Riesgo:**
- Stop Loss: Fuera del rango identificado
- Take Profit: En el extremo opuesto del rango
- Tamaño de posición: Conservador debido a naturaleza lateral

**Nota**: Actualmente el Signal Factory prioriza señales en TREND. Range Trading se implementará en futuras iteraciones.

#### Breakout Trading (Transiciones de Régimen)

**Estado**: Detectado automáticamente por Scanner, pendiente estrategia específica

**Condiciones de Entrada:**
- Transición de RANGE → TREND
- Ruptura de soporte/resistencia con volumen
- Confirmación de nuevo régimen TREND

**Gestión de Riesgo:**
- Stop Loss: Estricto (falsa ruptura)
- Take Profit: Amplio (sigue la nueva tendencia)
- Tamaño de posición: Moderado inicialmente

---

## 📝 Notas de Desarrollo

### Estructura de Directorios

```
Aethelgard/
├── config/
│   ├── config.json          # Escáner: assets, cpu_limit_pct, intervalos, MT5
│   ├── dynamic_params.json  # RegimeClassifier: ADX, volatilidad, etc.
│   └── modules.json         # Módulos de estrategias
├── core_brain/
│   ├── scanner.py           # Escáner proactivo multihilo (CPUMonitor, ScannerEngine)
│   ├── regime.py            # RegimeClassifier + load_ohlc
│   ├── server.py            # FastAPI + WebSockets
│   ├── tuner.py             # Auto-calibración
│   ├── risk_manager.py      # Gestión de riesgo agnóstica + Lockdown persistente
│   ├── executor.py          # Ejecución de órdenes con Factory Pattern + Resiliencia
│   ├── signal_factory.py    # Generación de señales (Oliver Vélez)
│   ├── notificator.py       # Notificaciones Telegram
│   └── module_manager.py    # Gestión de membresías
├── connectors/
│   ├── data_provider_manager.py # Sistema multi-proveedor con fallback automático
│   ├── generic_data_provider.py # Yahoo Finance (gratis, sin auth)
│   ├── alpha_vantage_provider.py # Alpha Vantage (25 req/día gratis)
│   ├── twelve_data_provider.py  # Twelve Data (800 req/día gratis)
│   ├── polygon_provider.py      # Polygon.io (requiere pago)
│   ├── iex_cloud_provider.py    # IEX Cloud (50k req/mes gratis)
│   ├── finnhub_provider.py      # Finnhub (60 req/min gratis)
│   ├── mt5_data_provider.py     # OHLC vía copy_rates_from_pos (sin gráficas)
│   ├── bridge_mt5.py            # Bridge WebSocket MT5 → Aethelgard
│   └── ...
├── data_vault/              # Persistencia SQLite
├── models/                  # Modelos de datos (Signal, MarketRegime, etc.)
├── tests/                   # Tests TDD
│   ├── test_risk_manager.py     # Suite RiskManager (7 tests)
│   ├── test_executor.py         # Suite OrderExecutor (7 tests)
│   ├── test_signal_factory.py   # Suite SignalFactory
│   └── test_data_providers.py   # Suite Data Providers (10 tests)
├── config/
│   ├── config.json              # Configuración general del sistema
│   ├── dynamic_params.json      # Parámetros auto-calibrables
│   └── data_providers.json      # Configuración de proveedores de datos
├── run_scanner.py           # Entrypoint del escáner proactivo
├── test_scanner_mock.py     # Test del escáner con mock (sin MT5)
├── strategies/              # Estrategias modulares (por crear)
│   ├── trend_following.py
│   ├── range_trading.py
│   └── risk_manager.py
└── dashboard/               # Dashboard web (Fase 4)
```

### Sistema Multi-Proveedor de Datos

Aethelgard implementa un sistema robusto de múltiples proveedores de datos con fallback automático:

#### Proveedores Gratuitos (sin autenticación):
- **Yahoo Finance**: Proveedor principal, sin límites, sin API key
- **MT5 Data Provider**: Datos directos desde MetaTrader 5 (requiere instalación)

#### Proveedores Gratuitos (con API key):
- **Alpha Vantage**: 25 requests/día, 5 requests/minuto
- **Twelve Data**: 800 requests/día, 8 requests/minuto
- **Finnhub**: 60 requests/minuto
- **IEX Cloud**: 50,000 requests/mes

#### Proveedores de Pago:
- **Polygon.io**: Desde $29/mes, datos profesionales

#### Características del Sistema:
- **Fallback Automático**: Si un proveedor falla, intenta con el siguiente
- **Configuración por Prioridad**: Define el orden de uso en `data_providers.json`
- **Activación/Desactivación**: Control granular de cada proveedor
- **Dashboard Integrado**: Gestión visual de proveedores y API keys

### Convenciones de Código

- **Python**: PEP 8, asíncrono (asyncio/FastAPI)
- **C#**: Estilo NinjaScript profesional
- **Tipado**: Type Hints y modelos Pydantic obligatorios
- **Documentación**: Comentarios claros en funciones críticas

### Principios de Diseño

1. **Agnosticismo**: Core Brain nunca depende de librerías específicas de plataforma
2. **Modularidad**: Estrategias en archivos independientes
3. **Resiliencia**: Manejo de errores y reconexión automática (incluye fallback de datos)
4. **Trazabilidad**: Todo se registra en `data_vault` para aprendizaje

---

## 🔄 Actualización del Manifiesto

**Última Actualización**: 27 de Enero 2026
- ✅ Implementado sistema multi-proveedor de datos con 6 proveedores
- ✅ Fallback automático entre proveedores
- ✅ Tests TDD completos (10 tests, 9 passing)
- ✅ Dashboard con gestión de proveedores y API keys

Este documento debe actualizarse cuando:
- Se complete una fase del roadmap
- Se añada una nueva estrategia
- Se modifique la arquitectura fundamental
- Se cambien las reglas de autonomía

**Mantenedor**: Equipo de desarrollo Aethelgard  
**Revisión**: Mensual o tras cambios significativos

---

*Este manifiesto es la Única Fuente de Verdad del proyecto Aethelgard. Cualquier decisión de diseño o implementación debe alinearse con los principios y arquitectura documentados aquí.*
