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

##### `scanner.py` - Escáner Proactivo Multi-Timeframe
- **Función**: Orquestador que escanea una lista de activos de forma proactiva en **múltiples timeframes simultáneamente**, sin depender de NinjaTrader ni de gráficas abiertas.
- **Componentes**:
  - **ScannerEngine**: Recibe `assets` y un **DataProvider** (inyectado; agnóstico de plataforma). Crea un `RegimeClassifier` por cada combinación **(símbolo, timeframe)**.
  - **CPUMonitor**: Lee uso de CPU (`psutil`). Si supera `cpu_limit_pct` (configurable en `config/config.json`), aumenta el sleep entre ciclos.
- **Multi-Timeframe Support**:
  - Usuario configura timeframes activos en `config.json` (M1, M5, M15, H1, H4, D1)
  - Cada símbolo se escanea en TODOS los timeframes activos
  - Genera claves compuestas: `"symbol|timeframe"` (ej: `"EURUSD|M5"`, `"EURUSD|H4"`)
  - Permite estrategias simultáneas: scalping en M5 + swing en H4 del mismo instrumento
- **Multithreading**: `concurrent.futures.ThreadPoolExecutor` para procesar cada combinación (símbolo, timeframe) en hilos separados.
- **Priorización**: TREND/CRASH → escaneo cada 1 s; RANGE → cada 10 s; NEUTRAL → cada 5 s (configurable).
- **Configuración**: `config/config.json` → `scanner` (`assets`, `cpu_limit_pct`, `sleep_*_seconds`, `timeframes[]`, `mt5_bars_count`, etc.).
- **Modos de Escaneo**: ECO (50% CPU), STANDARD (80% CPU), AGGRESSIVE (95% CPU)
- **Entrypoint**: `run_scanner.py` (usa `MT5DataProvider`). Test sin MT5: `test_scanner_mock.py`.
- **Documentación**: Ver `docs/TIMEFRAMES_CONFIG.md` para guía completa de configuración.

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
- **Arquitectura**: **Single Source of Truth = DATABASE** - Lee configuración de `broker_accounts` + `broker_credentials` (NO archivos JSON)
- **Interface**: `fetch_ohlc(symbol, timeframe, count)` → `DataFrame` con columnas `time`, `open`, `high`, `low`, `close`.
- **Requisitos**: MT5 en ejecución; los símbolos deben estar en Market Watch.

##### `mt5_connector.py` - Conector de Trading MT5
- **Lenguaje**: Python
- **Función**: Ejecutar operaciones de trading (abrir/cerrar posiciones) en MetaTrader 5
- **Arquitectura**: **Single Source of Truth = DATABASE** - Lee configuración de `broker_accounts` + `broker_credentials` (NO archivos JSON)
- **Seguridad**: Solo permite operaciones en cuentas DEMO (bloquea cuentas REAL automáticamente)
- **Interface**: `execute_signal()`, `close_position()`, `get_open_positions()`
- **Validación**: Verifica tipo de cuenta antes de cada operación

##### `generic_data_provider.py` - Proveedor de Datos Genérico (Yahoo Finance)
- **Lenguaje**: Python
- **Función**: Obtener datos OHLC de Yahoo Finance mediante `yfinance`
- **Robustez**: Bloqueo de concurrencia para llamadas a `yfinance`, manejo de MultiIndex, columnas duplicadas y fallback controlado.
- **Ventajas**: 100% gratuito, sin API key, totalmente autónomo.
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
- ✅ **Yahoo como Red de Seguridad**: Si NO hay proveedores habilitados o todos fallan, el sistema automáticamente usa Yahoo Finance (sin persistir cambio en DB)
- ✅ **Priorización Inteligente**: Selección basada en prioridad y disponibilidad
- ✅ **Gestión desde Dashboard**: Activar/desactivar proveedores desde UI
- ✅ **Configuración Persistente**: Settings guardados en base de datos (tabla `data_providers`)
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
- **Base de Datos**: `data_vault/aethelgard.db` (**SINGLE SOURCE OF TRUTH**)
- **Tablas**:
  - `signals`: Todas las señales recibidas
  - `signal_results`: Resultados y feedback de señales ejecutadas
  - `market_states`: Estados completos de mercado (para aprendizaje)
  - `broker_accounts`: Cuentas de brokers (MT5, NinjaTrader, Paper Trading)
  - `broker_credentials`: Credenciales encriptadas de conexión
  - `trades`: Registro completo de operaciones ejecutadas
  - `data_providers`: Proveedores de datos históricos configurados

**Funcionalidades clave:**
- Guardar señales con régimen detectado
- Registrar resultados de trades (PNL, feedback)
- Almacenar estados de mercado con todos los indicadores
- Consultas para análisis histórico y auto-calibración
- **Configuración Centralizada**: Credenciales, cuentas y proveedores en DB (NO archivos JSON/ENV)
- **Credenciales Encriptadas**: Passwords almacenados con Fernet encryption
- **Único Punto de Verdad**: Connectors y Dashboard leen SOLO de base de datos
- **Serialización y retry/backoff en escrituras críticas**: Todas las operaciones de escritura relevantes (señales, estado, cuentas) usan locking y reintentos automáticos para evitar bloqueos de base de datos y garantizar robustez en entornos concurrentes.
- **Control de cuenta activa única por broker**: Si existen varias cuentas demo activas para un broker, el sistema selecciona la primera como default y lo informa en logs/dashboard, asegurando que nunca se opere con más de una cuenta simultáneamente por broker.

#### 4. **Models** (`models/`)

##### `signal.py` - Modelos de Datos Pydantic
- **Signal**: Modelo de señal recibida
- **SignalResult**: Modelo de resultado de trade
- **MarketRegime**: Enum de regímenes (TREND, RANGE, CRASH, NEUTRAL)
- **ConnectorType**: Enum de conectores (NT, MT5, TV)
- **SignalType**: Enum de tipos de señal (BUY, SELL, CLOSE, MODIFY)

---


## 🤖 Reglas de Autonomía

### 6. Robustez y concurrencia en provisión de cuentas demo/real

**Principio:** El sistema debe garantizar que nunca existan bloqueos de base de datos ni duplicidad de cuentas activas por broker, incluso bajo alta concurrencia o provisión automática.

**Reglas implementadas:**
- Todas las escrituras críticas en la base de datos usan locking y retry/backoff.
- Si existen varias cuentas demo activas para un broker, se selecciona la primera como default y se informa explícitamente.
- Solo una cuenta demo activa por broker es utilizada para operar.
- Logs y dashboard reflejan siempre la cuenta seleccionada y el estado de provisión.


### 1. Auto-Calibración
### 5. Desarrollo Guiado por Pruebas (TDD)

**Principio**: Ningún cambio de código debe implementarse sin antes crear o actualizar un test que lo valide.

#### Proceso Obligatorio

1. **Primero el Test**: Antes de modificar o agregar cualquier funcionalidad, se debe crear o actualizar el test correspondiente en la carpeta `tests/`.
2. **Ejecución de Tests**: Ejecutar la suite completa de tests (`pytest`) y verificar que el nuevo test falle (red).
3. **Implementación Mínima**: Escribir el código mínimo necesario para que el test pase.
4. **Validación**: Ejecutar nuevamente todos los tests y asegurar que todos pasen (green).
5. **Refactorización**: Mejorar el código si es necesario, manteniendo los tests en verde.
6. **Documentación**: Actualizar este manifiesto y el ROADMAP.md con cada nueva regla, funcionalidad o cambio relevante.
7. **Commit Único**: Solo se permite hacer commit cuando todos los tests pasan y la documentación está actualizada.

**Regla de Oro**: Ningún cambio se considera terminado ni puede ser integrado al sistema si no sigue este flujo. El incumplimiento de TDD es considerado un bug crítico de proceso.

### 6. Reglas de Reuso y Diagnóstico de Tests

**Principio**: Antes de escribir código nuevo, se debe maximizar el reuso y respetar la intención del test.

**Reglas obligatorias**:
1. **Buscar reuso primero**: Antes de crear una nueva función, buscar implementaciones existentes con propósito similar.
2. **Refactorizar en lugar de duplicar**: Si existe una función compatible, refactorizarla para cubrir ambos casos y evitar duplicados.
3. **Tests no se cambian**: Si un test falla, no modificar el test. Explicar por qué la lógica actual no cumple el requisito del test y ajustar la implementación.

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

**2. Single Source of Truth = DATABASE**

La arquitectura ha sido **100% unificada** para garantizar que TODOS los componentes lean de la base de datos:

```python
# ❌ NUNCA MÁS: Configuración en archivos JSON/ENV
# config/mt5_config.json
# config/mt5.env
# config/data_providers.additional_config

# ✅ SIEMPRE: Configuración en base de datos
# Tablas: broker_accounts, broker_credentials, data_providers
```

**Componentes con DB-First:**

- **MT5Connector**: 
  ```python
  def __init__(self, account_id: Optional[str] = None):
      self.storage = StorageManager()
      self._load_config_from_db(account_id)  # Lee broker_accounts + broker_credentials
  ```

- **MT5DataProvider**:
  ```python
  def __init__(self, account_id, login=None, password=None, server=None, init_mt5=True):
      self.storage = StorageManager()
      self._load_from_db(account_id)  # Prioriza DB sobre parámetros legacy
  ```

- **Dashboard UI**:
  ```python
  # Solo guarda en DB, NO crea archivos JSON/ENV
  storage.save_credentials(account_id, password)
  st.rerun()  # NO time.sleep() innecesario
  ```

- **Scripts de Utilidad MT5**:
  ```python
  # setup_mt5_demo.py y diagnose_mt5_connection.py operan DB-first
  storage.save_broker_account(...)
  storage.get_broker_accounts()
  storage.get_credentials(account_id)
  ```

- **StorageManager**:
  ```python
  # No sincroniza archivos locales (mt5_config.json / mt5.env)
  # Toda la configuración vive en DB
  ```

- **CoherenceMonitor (EDGE)**:
  ```python
  # Auditoría end-to-end: Scanner -> Señal -> Estrategia -> Ejecución -> Ticket
  # Registra inconsistencias en tabla coherence_events
  # Reglas: símbolo no normalizado, EXECUTED sin ticket, PENDING con timeout
  ```

- **HealthManager**:
  ```python
  def check_mt5_connection(self):
      accounts = self.storage.get_broker_accounts()  # Lee de DB
      credentials = self.storage.get_credentials(account_id)  # Lee de DB
      # Verifica AutoTrading habilitado
      if not terminal_info.trade_allowed:
          return {
              "status": "warning",
              "message": "AutoTrading deshabilitado...",
              "help": "Paso 1: Abre MetaTrader 5..."
          }
  ```

**Beneficios:**
- ✅ **Cero Duplicación**: Una sola fuente de verdad (DB)
- ✅ **Cero Archivos Obsoletos**: No más `mt5_config.json` o `mt5.env`
- ✅ **Cero Reconexiones Fallidas**: Sin datos desactualizados en archivos
- ✅ **Credenciales Encriptadas**: Passwords protegidos con Fernet
- ✅ **Mensajes Mejorados**: Errores con pasos paso-a-paso para solucionar
- ✅ **AutoTrading Detection**: Sistema detecta si AutoTrading está habilitado
- ✅ **Normalización de Símbolos MT5**: `USDJPY=X` → `USDJPY`
- ✅ **Ejecución con Ticket Obligatorio**: No se marca `EXECUTED` sin `order_id`

---

## 🟢 Provisión EDGE de cuentas demo maestras y brokers (2026-01-30) ✅ COMPLETADA

**Resumen Ejecutivo:**
Se completó la provisión autónoma y óptima de cuentas demo maestras en brokers disponibles. El sistema detecta y crea cuentas demo solo cuando es necesario, evitando duplicados y asegurando resiliencia. Todo el estado y credenciales se gestionan exclusivamente en la base de datos, cumpliendo el principio de Single Source of Truth. El dashboard y los logs reflejan el estado actualizado y la lógica EDGE. Ver detalles y criterios en el [ROADMAP.md](ROADMAP.md).

**Reglas de Autonomía aplicadas:**
- Provisión solo cuando es óptimo (no redundante)
- Clasificación automática de brokers (auto/manual)
- Persistencia y validación en DB
- Visibilidad en dashboard y logs

**Referencias:**
- [ROADMAP.md](ROADMAP.md#fase-27-provision-edge-de-cuentas-demo-maestras-y-brokers)
- [Reglas de Autonomía](#reglas-de-autonomía)

---

## 🛡️ Fase 2.9: Monitor de Coherencia End-to-End (EDGE) ✅ **COMPLETADA** (2026-01-30)

**Prerrequisito: QA Guard Syntax Fixes** ✅ **COMPLETADO**
- Corregidos errores de sintaxis críticos que impedían análisis completo del código
- Archivos corregidos: `health.py`, `storage.py`, `bridge_mt5.py`, `dashboard.py`, `data_provider_manager.py`
- Resultado: QA Guard ejecuta completamente y reporta "Proyecto Limpio"

**Objetivo:** Auto-monitoreo inteligente de consistencia entre Scanner → Señal → Estrategia → Ejecución → Ticket.

**Alcance:**
- Detectar cuando hay condiciones de mercado pero no se genera señal.
- Detectar cuando hay señal pero no se ejecuta (o no hay ticket).
- Detectar cuando la estrategia válida no coincide con ejecución.

**Plan de Trabajo (2026-01-30):**
1. Definir eventos y métricas de coherencia (Scanner, SignalFactory, Executor, MT5Connector).
2. Diseñar y crear tabla `coherence_events` en DB para trazabilidad por símbolo/timeframe/estrategia.
3. Implementar reglas de coherencia (mismatch detector con razones exactas y tipo de incoherencia).
4. Integrar registro de eventos en el ciclo del orquestador.
5. Exponer estado y eventos en el dashboard UI.
6. Crear tests de cobertura para casos de incoherencia y recuperación.
7. Documentar criterios y resultados en el MANIFESTO.

**Checklist de tareas:**
- [x] Definición de eventos y métricas
- [x] Diseño y migración de DB (tabla coherence_events)
- [x] Implementación de reglas de coherencia
- [x] Integración en orquestador
- [x] Visualización en dashboard
- [x] Tests de cobertura
- [x] Documentación actualizada

**3. Reconstrucción de Estado (Crash Recovery)**
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

### Fase 1.1: Escáner Proactivo Multi-Timeframe ✅ **COMPLETADA** (Enero 2026)

**Objetivo**: Transformar Aethelgard en un **escáner proactivo multi-timeframe** que obtenga datos de forma autónoma y escanee múltiples activos en **todos los timeframes activos simultáneamente**, con control de recursos y priorización por régimen.

**Componentes implementados:**
- ✅ **`core_brain/scanner.py`**: `ScannerEngine` (orquestador multi-timeframe), `CPUMonitor`, protocolo `DataProvider`. Multithreading con `concurrent.futures.ThreadPoolExecutor`.
- ✅ **Multi-Timeframe Support**: Configuración de timeframes activos (M1, M5, M15, H1, H4, D1) con flags enabled
- ✅ **`connectors/mt5_data_provider.py`**: Ingestión autónoma OHLC vía `mt5.copy_rates_from_pos` (sin gráficas abiertas).
- ✅ **`config/config.json`**: Configuración del escáner con array de timeframes configurables.
- ✅ **`RegimeClassifier.load_ohlc(df)`**: Carga masiva OHLC para uso en escáner.
- ✅ **`run_scanner.py`**: Entrypoint del escáner con MT5. `test_scanner_mock.py`: test con DataProvider mock (sin MT5).
- ✅ **`docs/TIMEFRAMES_CONFIG.md`**: Guía completa de configuración de timeframes

**Funcionalidades:**
- Lista de activos configurable desde `InstrumentManager` (solo instrumentos habilitados)
- Un `RegimeClassifier` por cada combinación **(símbolo, timeframe)**
- Escaneo paralelo de todas las combinaciones activas
- **Control de recursos**: si CPU > `cpu_limit_pct`, aumenta el sleep entre ciclos
- **Priorización**: TREND/CRASH cada 1s, RANGE cada 10s, NEUTRAL cada 5s (configurables)
- **Modos de escaneo**: ECO (50% CPU), STANDARD (80% CPU), AGGRESSIVE (95% CPU)
- **Deduplicación inteligente**: Permite señales del mismo símbolo en diferentes timeframes
- Agnóstico de plataforma: el escáner recibe un `DataProvider` inyectado

**Tests implementados:**
- ✅ `tests/test_scanner_multiframe.py` (6 tests): Validación multi-timeframe
- ✅ `tests/test_multiframe_deduplication.py` (6 tests): Deduplicación por (symbol, timeframe)
- ✅ Suite completa: **134/134 tests passing**

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
  2. Consulta a los conectores (`get_closed_positions()`) por órdenes cerradas
  3. Empareja órdenes cerradas con señales mediante ticket o signal_id
  4. Calcula PIPs, profit real, duración y resultado (win/loss)
  5. Actualiza señal a estado `CLOSED` y registra resultado en tabla `trades`

**Nota de Integración**:
- `PaperConnector` implementa `get_closed_positions()` y retorna lista vacía para evitar errores en ClosingMonitor.

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

#### 3.3 Dashboard de Control (Upgrade UX) ✅

**Arquitectura de Navegación (Sidebar)**:
- **Operación Hub**: Gestión crítica del sistema (Salud, Brokers, Monitor de Resiliencia, Señales).
- **Análisis & Mercado**: Clasificación de Régimen en tiempo real, KPIs y Análisis de Activos.
- **Configuración**: Gestión de Módulos, Tuner EDGE y Proveedores de Datos.

**Beneficios**:
- ✅ **Responsividad**: Navegación lateral que evita el clipping de secciones en pantallas pequeñas.
- ✅ **Categorización**: Agrupación lógica de las 10 secciones del sistema.
- ✅ **Visibilidad**: Acceso directo y persistente a todas las funciones del hub.

#### 3.4 Integración del Monitor en el Sistema

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

### Fase 4: Auto-Provisioning y Multi-Broker 🚀 **EN PROGRESO**

**Objetivo**: Sistema autónomo capaz de crear y gestionar cuentas demo automáticamente en múltiples brokers sin intervención humana.

#### 4.1 Arquitectura Correcta: Brokers vs Plataformas ✅ **CORREGIDO**

**Estado**: Completado (Enero 2026)

**Objetivo**: Separación correcta de conceptos: Broker (proveedor), Plataforma (software), Cuenta (configuración usuario).

**Conceptos Clave:**
- **BROKER** = Proveedor de liquidez/intermediario financiero (Pepperstone, IC Markets, Binance, IBKR)
- **PLATFORM** = Software de ejecución (MetaTrader 5, NinjaTrader 8, TradingView, API)
- **ACCOUNT** = Cuenta específica en un broker usando una plataforma

**Relaciones:**
- Un BROKER puede ofrecer múltiples PLATFORMS (Pepperstone: MT5, MT4, cTrader)
- Un BROKER puede tener múltiples ACCOUNTS (Pepperstone Demo 1, Pepperstone Live)
- Una ACCOUNT usa una PLATFORM específica y un SERVER específico

**Ejemplo Correcto:**
```
Broker: Pepperstone (proveedor de liquidez forex)
├── Platforms Available: [MT5, MT4, cTrader]
├── Data Server: Pepperstone-Demo
└── Accounts:
    ├── Account 1:
    │   ├── Platform: MT5
    │   ├── Server: Pepperstone-Demo
    │   ├── Type: demo
    │   ├── Account Number: 123456789
    │   └── Credentials: config/accounts/pepperstone_mt5_demo_123.json
    └── Account 2:
        ├── Platform: cTrader
        ├── Server: Pepperstone-cTrader-Demo
        ├── Type: demo
        └── Credentials: config/accounts/pepperstone_ctrader_demo_456.json
```

**Schema SQL:**
```sql
-- Catálogo de Brokers (proveedores)
CREATE TABLE brokers (
    broker_id TEXT PRIMARY KEY,           -- pepperstone, ic_markets, binance
    name TEXT NOT NULL,                   -- Pepperstone, IC Markets
    type TEXT,                            -- forex, crypto, multi_asset, futures
    website TEXT,                         -- URL oficial
    platforms_available TEXT,             -- JSON: ["mt5", "mt4", "ctrader"]
    data_server TEXT,                     -- Servidor de datos históricos
    auto_provision_available BOOLEAN,     -- Soporta auto-provisioning?
    registration_url TEXT,                -- URL para crear cuenta
    created_at TEXT,
    updated_at TEXT
);

-- Catálogo de Plataformas (software)
CREATE TABLE platforms (
    platform_id TEXT PRIMARY KEY,         -- mt5, nt8, tradingview, binance_api
    name TEXT NOT NULL,                   -- MetaTrader 5, NinjaTrader 8
    vendor TEXT,                          -- MetaQuotes, NinjaTrader LLC
    type TEXT,                            -- desktop, web, api
    capabilities TEXT,                    -- JSON: ["forex", "futures", "crypto"]
    connector_class TEXT,                 -- connectors.mt5_connector.MT5Connector
    created_at TEXT
);

-- Cuentas configuradas (usuario)
CREATE TABLE broker_accounts (
    account_id TEXT PRIMARY KEY,          -- uuid generado
    broker_id TEXT,                       -- FK a brokers
    platform_id TEXT,                     -- FK a platforms
    account_name TEXT,                    -- "Pepperstone Demo 1"
    account_number TEXT,                  -- Login del broker
    server TEXT,                          -- Pepperstone-Demo, api.binance.com
    account_type TEXT,                    -- demo, live, paper
    credentials_path TEXT,                -- config/accounts/pepperstone_mt5_demo.json
    enabled BOOLEAN DEFAULT 1,
    last_connection TEXT,
    balance REAL,                         -- Último balance conocido
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (broker_id) REFERENCES brokers(broker_id),
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id)
);
```

**Datos Iniciales Seeded:**

**Plataformas (7):**
- MetaTrader 5 (desktop)
- MetaTrader 4 (desktop)
- NinjaTrader 8 (desktop)
- TradingView (web)
- Binance API (api)
- Interactive Brokers API (api)
- cTrader (desktop)

**Brokers (7):**
- Pepperstone (forex) - Platforms: MT5, MT4, cTrader [👤 Manual]
- IC Markets (forex) - Platforms: MT5, MT4, cTrader [👤 Manual]
- XM Global (forex) - Platforms: MT5, MT4 [👤 Manual]
- **Binance (crypto)** - Platforms: API [🤖 Auto-Provision]
- Interactive Brokers (multi-asset) - Platforms: API [👤 Manual]
- AMP Futures (futures) - Platforms: NT8 [👤 Manual]
- **Tradovate (futures)** - Platforms: API, NT8 [🤖 Auto-Provision]

**Migración de Datos:**
```bash
# 1. Migrar schema (elimina tabla vieja, crea nuevas)
python scripts/migrate_broker_schema.py

# 2. Poblar brokers y plataformas iniciales
python scripts/seed_brokers_platforms.py

# Output:
# ✅ 7 Platforms seeded
# ✅ 7 Brokers seeded
# Auto-Provision Available: 2/7
```

#### 4.2 Auto-Provisioning de Cuentas Demo ✅ **ACTUALIZADO**

**Estado**: Actualizado con arquitectura correcta (Enero 2026)

**Objetivo**: Crear cuentas demo automáticamente en brokers que lo permitan.

**Arquitectura Correcta:**
- El sistema ahora distingue entre **BROKER** (proveedor) y **PLATFORM** (software)
- Auto-provisioning se aplica a nivel de **ACCOUNT** (combinación broker + platform)
- Datos almacenados en DB: tablas `brokers`, `platforms`, `broker_accounts`

**Clasificación de Brokers:**

| Broker | Tipo | Auto-Provisioning | Método | Estado |
|--------|------|-------------------|--------|--------|
| **Binance Testnet** | Crypto | ✅ Full | API pública | Automático |
| **TradingView Paper** | Multi-Asset | ✅ Full | Webhook | Automático |
| **MT5 MetaQuotes Demo** | Forex/CFD | ✅ Partial | API demo | Automático |
| **NinjaTrader Kinetic** | Futures | ✅ Partial | Simulador local | Automático |
| **MT5 Pepperstone/IC** | Forex | ⚠️ Partial | Registro web | Manual |
| **Interactive Brokers** | Multi-Asset | ❌ None | Cuenta real requerida | Manual |
| **Rithmic** | Futures | ❌ None | Registro comercial | Manual |

**Funcionalidad:**
```bash
# Modo DEMO: Auto-crea cuentas si no existen
python start_production.py --mode demo

# Sistema automáticamente:
# 1. Verifica si existe cuenta demo guardada
# 2. Si NO existe y broker soporta auto-creation → CREA automáticamente
# 3. Si broker requiere manual → Muestra instrucciones de registro
# 4. Guarda credenciales en config/demo_accounts/ (encriptado)
# 5. Conecta y opera en modo demo
```

**Proveedores Automáticos:**
- **Binance**: Genera API keys en testnet sin registro
- **TradingView**: Configura webhook para paper trading integrado
- **MT5 MetaQuotes**: Crea cuenta demo instantánea (sin broker específico)
- **NT8 Kinetic**: Activa simulador local (sin conexión externa)

**Proveedores Manuales:**
- **MT5 Brokers**: Usuario debe registrarse en sitio web (Pepperstone, IC Markets, XM)
- **IBKR**: Requiere cuenta real primero, luego habilitar paper trading
- **Rithmic**: Requiere solicitud comercial y aprobación

**Seguridad:**
- Credenciales guardadas en `config/demo_accounts/*.json`
- Permisos 600 (solo propietario)
- Validación de cuentas demo antes de ejecutar trades
- Lockdown automático si detecta cuenta real en modo DEMO

#### 4.2 Modo DEMO Autónomo ✅ **IMPLEMENTADO**

**Estado**: Completado (Enero 2026)

**Cómo Funciona:**
```python
# Sistema detecta si usuario elige --mode demo
# Si broker soporta auto-creation:
provisioner = BrokerProvisioner()
success, creds = await provisioner.ensure_demo_account('binance')

if success:
    # Cuenta creada/cargada automáticamente
    # Sistema opera sin intervención humana
else:
    # Broker requiere setup manual
    # Muestra instrucciones: URL registro + pasos
```

**Experiencia de Usuario:**

**Broker Automático (Binance):**
```
🤖 Auto-Provisioning: Configurando brokers DEMO...
   Verificando binance...
   ✅ binance demo disponible
   Account: aethelgard_a3f9b2c1
   API Key: test_****
   Ready to trade!
```

**Broker Manual (IBKR):**
```
⚠️  ibkr requiere configuración manual
   1. Registro: https://www.interactivebrokers.com/...
   2. Crear cuenta real
   3. Habilitar Paper Trading en Account Management
   4. Guardar credenciales en config/demo_accounts/ibkr_demo.json
```

#### 4.3 Roadmap Multi-Broker 🎯 **FUTURO**

**Próximos Brokers:**
- [ ] Implementar conector Binance Testnet completo
- [ ] Implementar conector TradingView webhook
- [ ] Completar auto-provision MT5 MetaQuotes Demo
- [ ] Implementar NT8 Kinetic simulator connector
- [ ] Agregar IBKR paper trading (manual)
- [ ] Agregar más exchanges crypto (Bybit testnet, OKX demo)

#### 4.4 Gestión de Brokers desde Dashboard ✅ **IMPLEMENTADO**

**Estado**: Completado (Enero 2026)

**Objetivo**: Interfaz visual para gestionar conexiones con brokers sin editar archivos manualmente.

**Componentes Implementados:**
- ✅ Tabla `brokers` en SQLite con toda la configuración
- ✅ Script de migración `migrate_brokers_to_db.py` (JSON → DB)
- ✅ Tab "🔌 Configuración de Brokers" en Dashboard
- ✅ 8 tests unitarios en `test_broker_storage.py` (todos pasando)

**Funcionalidades de la Interfaz:**

**Vista General:**
- Lista de todos los brokers configurados
- Estado visual: 🟢 Habilitado / 🔴 Deshabilitado
- Iconos de auto-provisioning: 🤖 Full / ⚙️ Partial / 👤 Manual
- Filtros: Todos / Habilitados / Deshabilitados
- Estadísticas: Total, Habilitados %, Auto-Provision Full, Configurados %

**Por Broker (Expandible):**
- **Información**: Tipo, Auto-Provisioning nivel, Proveedores disponibles
- **Estado**: Última conexión, Credenciales configuradas (✅/⚠️)
- **Toggle**: Habilitar/Deshabilitar con un click
- **Acciones**:
  * 🔌 **Test Conexión**: Verifica conectividad, auto-crea cuenta si soportado
  * 🤖 **Auto-Provision**: Crea cuenta demo automáticamente (si aplicable)
  * 📁 **Ver Credenciales**: Muestra configuración (oculta passwords/keys)

**Flujo de Trabajo:**
```
Usuario → Dashboard → Tab "Configuración de Brokers"
→ Selecciona broker (ej: Binance)
→ Click "Auto-Provision"
→ Sistema crea cuenta testnet automáticamente
→ Guarda credenciales en config/demo_accounts/
→ Actualiza DB con path y timestamp
→ Broker listo para operar
```

**Persistencia:**
```sql
-- Tabla brokers (catálogo de proveedores disponibles)
CREATE TABLE brokers (
    broker_id TEXT PRIMARY KEY,              -- binance, mt5, ibkr, nt8, tradingview
    name TEXT NOT NULL,                      -- Binance, MetaTrader 5, etc.
    type TEXT,                               -- crypto, forex_cfd, multi_asset, futures
    website TEXT,                            -- URL oficial del broker
    platforms_available TEXT,                -- JSON: ["mt5", "api", "tradingview"]
    data_server TEXT,                        -- Servidor de datos demo/prod
    auto_provision_available BOOLEAN,        -- ¿Soporta creación automática de cuentas?
    registration_url TEXT,                   -- URL para registro manual
    created_at TEXT,
    updated_at TEXT
);

-- Tabla broker_accounts (cuentas específicas del usuario)
CREATE TABLE broker_accounts (
    account_id TEXT PRIMARY KEY,
    broker_id TEXT,                          -- FK a brokers
    platform_id TEXT,                        -- mt5, binance_api, ibkr_api
    account_name TEXT,                       -- Nombre descriptivo
    account_number TEXT,                     -- Login/Usuario
    server TEXT,                             -- Server específico
    account_type TEXT,                       -- demo, real
    credentials_path TEXT,                   -- Ruta a credenciales cifradas
    enabled BOOLEAN DEFAULT 1,               -- ⚠️ enabled SOLO en cuentas, NO en brokers
    last_connection TEXT,
    balance REAL,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (broker_id) REFERENCES brokers(broker_id)
);
```

**Métodos de StorageManager (API Actual):**

*Gestión de Brokers (Catálogo):*
- `save_broker(broker_config)`: Guarda/actualiza broker en catálogo
- `get_brokers()`: Lista todos los brokers del catálogo
- `get_broker(broker_id)`: Obtiene broker específico
- `save_platform(platform_config)`: Guarda plataforma (mt5, nt8, etc.)
- `get_platforms()`: Lista todas las plataformas

*Gestión de Cuentas (Usuario):*
- `save_broker_account(broker_id, platform_id, account_name, ...)`: Crea cuenta de trading
- `get_broker_accounts(broker_id=None, enabled_only=False, account_type=None)`: Filtra cuentas
- `get_account(account_id)`: Obtiene cuenta específica
- `update_account_status(account_id, enabled)`: Habilita/deshabilita cuenta
- `update_account_connection(account_id, balance)`: Actualiza conexión y balance
- `update_account_type(account_id, account_type)`: Cambia demo ↔ real

*Métodos Deprecated (NO usar):*
- ~~`save_broker_config()`~~ → usar `save_broker()`
- ~~`get_enabled_brokers()`~~ → usar `get_broker_accounts(enabled_only=True)`
- ~~`update_broker_status()`~~ → NO EXISTE (enabled solo en cuentas)
- ~~`update_broker_credentials()`~~ → credenciales en cuenta, no en broker

**Migración de Datos:**
```bash
# Migrar brokers de config/brokers.json a DB (una sola vez)
python scripts/migrate_brokers_to_db.py

# Output:
# ✅ Migrated: binance (Binance)
# ✅ Migrated: mt5 (MetaTrader 5)
# ✅ Migrated: ibkr (Interactive Brokers)
# ✅ Migrated: nt8 (NinjaTrader 8)
# ✅ Migrated: tradingview (TradingView)
# Migration complete: 5/5 brokers
```

**Seguridad:**
- Credenciales sensibles (passwords, API keys) mostradas como `***HIDDEN***` en UI
- Archivos de credenciales con permisos 600 (solo propietario)
- Validación de auto-provisioning antes de ejecutar

**Documentación:**
Todo está documentado EXCLUSIVAMENTE en este archivo (AETHELGARD_MANIFESTO.md).
NO crear guías separadas, READMEs adicionales, o documentos redundantes.

---

### Fase 5: Evolución Comercial 🎯 **FUTURA**

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

#### 5.2 Módulos bajo Demanda

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

#### 5.3 Sistema de Notificaciones

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

### Sistema de Deduplicación Inteligente

#### Problema que Resuelve

En trading algorítmico, **duplicar señales** es un riesgo crítico:
- 📉 **Sobre-exposición**: Abrir dos posiciones idénticas en el mismo símbolo
- ⚡ **Ruido del mercado**: Señales repetitivas en ventanas temporales cortas
- 💸 **Costos duplicados**: Spreads y comisiones innecesarias

#### Arquitectura Multi-Capa

Aethelgard implementa **3 capas de protección** anti-duplicados:

```
┌───────────────────────────────────────────────────────────────┐
│ CAPA 1: Signal Factory (Pre-Generación)                      │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ _is_duplicate_signal()                                    │ │
│ │ • Verifica si existe posición abierta                     │ │
│ │ • Consulta señales recientes (ventana dinámica)           │ │
│ │ • Descarta ANTES de generar la señal                      │ │
│ └───────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────┐
│ CAPA 2: OrderExecutor (Pre-Ejecución)                        │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ execute_signal() - Paso 2                                 │ │
│ │ • has_open_position(): Bloquea si hay posición activa     │ │
│ │ • has_recent_signal(): Bloquea si señal reciente existe   │ │
│ │ • Rechaza con código DUPLICATE_OPEN_POSITION o            │ │
│ │   DUPLICATE_RECENT_SIGNAL                                 │ │
│ └───────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────┐
│ CAPA 3: StorageManager (Persistencia)                        │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ has_open_position(symbol)                                 │ │
│ │ SELECT COUNT(*) FROM signals s                            │ │
│ │ LEFT JOIN trades t ON s.id = t.signal_id                  │ │
│ │ WHERE s.symbol = ? AND s.status = 'EXECUTED'              │ │
│ │ AND t.id IS NULL  -- Sin trade de cierre                  │ │
│ │                                                            │ │
│ │ has_recent_signal(symbol, signal_type, timeframe)         │ │
│ │ SELECT COUNT(*) FROM signals                              │ │
│ │ WHERE symbol = ? AND signal_type = ?                      │ │
│ │ AND timestamp >= ?  -- Ventana dinámica                   │ │
│ └───────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

#### Ventana de Deduplicación Adaptativa

**Problema**: Una ventana fija de 60 minutos es:
- ❌ **Demasiado larga** para timeframes de 1 minuto (scalping bloqueado)
- ❌ **Demasiado corta** para timeframes de 4 horas (permite duplicados prematuros)

**Solución**: Ventana **proporcional al timeframe** de la estrategia.

##### Función de Cálculo Dinámico

```python
def calculate_deduplication_window(timeframe: Optional[str]) -> int:
    """
    Calcula ventana de deduplicación basada en timeframe.
    
    Ejemplos:
        - "1m" or "M1" -> 10 minutos
        - "5m" or "M5" -> 20 minutos
        - "15m" or "M15" -> 45 minutos
        - "1h" or "H1" -> 120 minutos (2 horas)
        - "4h" or "H4" -> 480 minutos (8 horas)
        - "1D" or "D1" -> 1440 minutos (24 horas)
    """
```

##### Mapeo de Ventanas por Timeframe

| Timeframe | Ventana Deduplicación | Ratio | Uso Típico |
|-----------|----------------------|-------|------------|
| **1m / M1** | 10 minutos | 10x | Scalping ultra-rápido |
| **3m / M3** | 15 minutos | 5x | Scalping intensivo |
| **5m / M5** | 20 minutos | 4x | Scalping estándar |
| **15m / M15** | 45 minutos | 3x | Day trading corto plazo |
| **30m / M30** | 90 minutos | 3x | Intraday swing |
| **1h / H1** | 120 minutos (2h) | 2x | Swing intraday |
| **4h / H4** | 480 minutos (8h) | 2x | Swing multi-sesión |
| **1D / D1** | 1440 minutos (24h) | 1x | Position trading |

**Regla General**: 
- Timeframes de **minutos**: Ventana = `Timeframe × 5` (mínimo 10 min)
- Timeframes de **horas**: Ventana = `Timeframe × 2` (en minutos)
- Timeframes de **días**: Ventana = `Timeframe × 1440` (día completo)

#### Modelo de Signal con Timeframe

```python
class Signal(BaseModel):
    """Señal de trading con timeframe para deduplicación inteligente."""
    symbol: str
    signal_type: SignalType
    confidence: float
    connector_type: ConnectorType
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    volume: float = 0.01
    timestamp: datetime = Field(default_factory=datetime.now)
    strategy_id: Optional[str] = None
    timeframe: Optional[str] = "M5"  # Default: 5 minutos
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

#### Validación en OrderExecutor

```python
async def execute_signal(self, signal: Signal) -> bool:
    """Ejecuta señal con validación multi-capa de duplicados."""
    
    # Step 2a: Verificar posición abierta
    if self.storage.has_open_position(signal.symbol):
        logger.warning(
            f"Signal rejected: Open position already exists for {signal.symbol}. "
            f"Preventing duplicate operation."
        )
        self._register_failed_signal(signal, "DUPLICATE_OPEN_POSITION")
        return False
    
    # Step 2b: Verificar señal reciente (ventana dinámica)
    if self.storage.has_recent_signal(
        symbol=signal.symbol, 
        signal_type=signal_type_str, 
        timeframe=signal.timeframe
    ):
        window = calculate_deduplication_window(signal.timeframe) if signal.timeframe else 60
        logger.warning(
            f"Signal rejected: Recent {signal_type_str} signal for {signal.symbol} "
            f"already processed within last {window} minutes (timeframe: {signal.timeframe}). "
            f"Preventing duplicate."
        )
        self._register_failed_signal(signal, "DUPLICATE_RECENT_SIGNAL")
        return False
```

#### Ejemplos Prácticos

##### Ejemplo 1: Scalping en 1m

```python
# Señal 1: BUY EURUSD @ 10:00:00
signal_1 = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    timeframe="1m",
    entry_price=1.1050
)
executor.execute_signal(signal_1)  # ✅ EJECUTADA

# Señal 2: BUY EURUSD @ 10:05:00 (5 minutos después)
signal_2 = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    timeframe="1m",
    entry_price=1.1055
)
executor.execute_signal(signal_2)  # ❌ RECHAZADA (5 min < 10 min window)

# Señal 3: BUY EURUSD @ 10:12:00 (12 minutos después)
signal_3 = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    timeframe="1m",
    entry_price=1.1060
)
executor.execute_signal(signal_3)  # ✅ EJECUTADA (12 min > 10 min window)
```

##### Ejemplo 2: Swing Trading en 4h

```python
# Señal 1: SELL BTCUSD @ Lunes 08:00
signal_1 = Signal(
    symbol="BTCUSD",
    signal_type=SignalType.SELL,
    timeframe="4h",
    entry_price=50000
)
executor.execute_signal(signal_1)  # ✅ EJECUTADA

# Señal 2: SELL BTCUSD @ Lunes 14:00 (6 horas después)
signal_2 = Signal(
    symbol="BTCUSD",
    signal_type=SignalType.SELL,
    timeframe="4h",
    entry_price=49500
)
executor.execute_signal(signal_2)  # ❌ RECHAZADA (6h < 8h window)

# Señal 3: SELL BTCUSD @ Lunes 17:00 (9 horas después)
signal_3 = Signal(
    symbol="BTCUSD",
    signal_type=SignalType.SELL,
    timeframe="4h",
    entry_price=49000
)
executor.execute_signal(signal_3)  # ✅ EJECUTADA (9h > 8h window)
```

#### Override Manual de Ventana

Para casos especiales, puedes **forzar una ventana específica**:

```python
# Verificar con ventana personalizada (30 minutos)
is_duplicate = storage.has_recent_signal(
    symbol="EURUSD",
    signal_type="BUY",
    minutes=30,  # Override: ignora timeframe
    timeframe="1h"  # Normalmente sería 120 min
)
```

#### Beneficios del Sistema

✅ **Protección Inteligente**: Adapta la ventana al contexto temporal de la estrategia  
✅ **Scalpers Protegidos**: En 1m, solo bloquea 10 min (antes 60 min era excesivo)  
✅ **Swing Traders Seguros**: En 4h, ventana de 8h evita entradas prematuras  
✅ **Multi-Símbolo**: Permite operar diferentes pares simultáneamente  
✅ **Señales Opuestas**: BUY y SELL son independientes (no se bloquean mutuamente)  
✅ **Retrocompatible**: Señales sin timeframe usan default 60 minutos  
✅ **Production-Ready**: 26 tests validando todos los escenarios  

#### Tests de Deduplicación

**Test Suite 1** (`tests/test_signal_deduplication.py` - 6 tests):
1. ✅ **Detección de Posición Abierta**: `has_open_position()` detecta trades sin cierre
2. ✅ **Detección de Señal Reciente**: `has_recent_signal()` encuentra señales en ventana
3. ✅ **Rechazo por Posición Abierta**: Executor rechaza con `DUPLICATE_OPEN_POSITION`
4. ✅ **Rechazo por Señal Reciente**: Executor rechaza con `DUPLICATE_RECENT_SIGNAL`
5. ✅ **Permitir Diferentes Símbolos**: EURUSD y GBPUSD operan independientemente
6. ✅ **Bloquear Señales Opuestas**: Rechaza SELL si hay posición BUY abierta

**Test Suite 2** (`tests/test_dynamic_deduplication.py` - 13 tests):
1. ✅ **Cálculo Ventana 1m**: 10 minutos
2. ✅ **Cálculo Ventana 5m**: 20 minutos
3. ✅ **Cálculo Ventana 15m**: 45 minutos
4. ✅ **Cálculo Ventana 1h**: 120 minutos
5. ✅ **Cálculo Ventana 4h**: 480 minutos
6. ✅ **Cálculo Ventana 1D**: 1440 minutos
7. ✅ **Timeframe Desconocido**: Fallback a 60 minutos
8. ✅ **Respeto Ventana 1m**: Señal de 15 min atrás NO bloqueada (15 > 10)
9. ✅ **Respeto Ventana 4h**: Señal de 6h atrás SÍ bloqueada (6 < 8)
10. ✅ **Señales Expiradas**: Señal de 9h atrás en 4h NO bloqueada (9 > 8)
11. ✅ **Override Explícito**: `minutes` parameter sobrescribe cálculo
12. ✅ **Timeframes Diferentes**: Mismo símbolo, diferentes ventanas según TF
13. ✅ **Integración Executor**: Executor usa `signal.timeframe` automáticamente

**Ejecución Completa**:
```bash
# Suite deduplicación básica
pytest tests/test_signal_deduplication.py -v
# ====================== 6 passed in 3.32s ======================

# Suite ventana dinámica
pytest tests/test_dynamic_deduplication.py -v
# ====================== 13 passed in 1.28s ======================

# Suite executor (incluye validación duplicados)
pytest tests/test_executor.py -v
# ====================== 7 passed in 1.09s ======================

# Total: 26 tests validando sistema anti-duplicados
```

#### Códigos de Rechazo

| Código | Significado | Acción |
|--------|-------------|--------|
| `DUPLICATE_OPEN_POSITION` | Ya existe posición abierta | Esperar cierre antes de nueva entrada |
| `DUPLICATE_RECENT_SIGNAL` | Señal reciente en ventana | Esperar expiración de ventana |
| `REJECTED_LOCKDOWN` | RiskManager bloqueado | Sistema en modo seguridad |
| `REJECTED_CONNECTION` | Fallo de conexión con broker | Reintento o notificación |
| `INVALID_DATA` | Datos de señal inválidos | Validar entrada antes de enviar |

---

### Sistema de Trazabilidad Completa

#### Problema que Resuelve

En un sistema de trading multi-plataforma y multi-cuenta, es crítico saber:
- 🎯 **¿DÓNDE se ejecutó cada operación?** (MT5, NT8, Binance, etc.)
- 💰 **¿Es dinero REAL o DEMO?** (Performance real vs práctica)
- 📊 **¿Qué mercado?** (Forex, Crypto, Stocks, Futures)
- 🔍 **¿Qué cuenta específica?** (Auditoría y portfolio management)
- 📋 **¿ID de orden del broker?** (Reconciliación con statements)

**Antes**: Señales sin contexto → Imposible separar DEMO de REAL, Forex de Crypto  
**Ahora**: Trazabilidad completa → Análisis granular por plataforma/cuenta/mercado

#### Arquitectura de Datos

##### Modelo Signal Mejorado

```python
class Signal(BaseModel):
    """
    Señal de trading con trazabilidad completa.
    Soporta múltiples cuentas, plataformas y mercados simultáneos.
    """
    # Core signal data
    symbol: str
    signal_type: SignalType
    confidence: float
    connector_type: ConnectorType
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    volume: float = 0.01
    timestamp: datetime = Field(default_factory=datetime.now)
    strategy_id: Optional[str] = None
    timeframe: Optional[str] = "M5"
    
    # 🎯 Traceability fields (NEW)
    account_id: Optional[str] = None        # UUID de cuenta (FK a tabla accounts)
    account_type: Optional[str] = "DEMO"    # DEMO o REAL
    market_type: Optional[str] = "FOREX"    # FOREX, CRYPTO, STOCKS, FUTURES
    platform: Optional[str] = None          # MT5, NT8, BINANCE, PAPER
    order_id: Optional[str] = None          # ID de orden del broker
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

##### Esquema de Base de Datos

**Tabla `signals`** (18 columnas):
```sql
CREATE TABLE signals (
    -- Campos originales
    id TEXT PRIMARY KEY,
    symbol TEXT,
    signal_type TEXT,
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    timestamp TEXT,
    date TEXT,
    status TEXT,
    metadata TEXT,
    
    -- 🎯 Trazabilidad (7 campos nuevos)
    connector_type TEXT,    -- METATRADER5, NINJATRADER8, PAPER, etc.
    account_id TEXT,        -- UUID de cuenta
    account_type TEXT,      -- DEMO, REAL
    market_type TEXT,       -- FOREX, CRYPTO, STOCKS, FUTURES
    platform TEXT,          -- MT5, NT8, BINANCE, etc.
    order_id TEXT,          -- ID de orden del broker
    volume REAL             -- Volumen ejecutado
)
```

**Tabla `trades`** (23 columnas):
```sql
CREATE TABLE trades (
    -- Campos originales...
    id TEXT PRIMARY KEY,
    signal_id TEXT,
    symbol TEXT,
    entry_price REAL,
    exit_price REAL,
    pips REAL,
    profit_loss REAL,
    -- [más campos...]
    
    -- 🎯 Trazabilidad (8 campos nuevos)
    connector_type TEXT,
    account_id TEXT,
    account_type TEXT,
    market_type TEXT,
    platform TEXT,
    volume REAL,
    commission REAL,        -- Comisiones pagadas
    swap REAL              -- Swap overnight
)
```

#### Migración de Base de Datos

**Script**: `scripts/migrate_add_traceability.py`

```python
# Ejecutar migración
python scripts/migrate_add_traceability.py

# Output:
# ✅ Added connector_type to signals
# ✅ Added account_id to signals
# ✅ Added account_type to signals
# ✅ Added market_type to signals
# ✅ Added platform to signals
# ✅ Added order_id to signals
# ✅ Added volume to signals
# [... 8 columnas más en trades ...]
# ✅ Migration completed successfully!
```

**Características de la migración**:
- ✅ **No destructiva**: Preserva todos los datos existentes
- ✅ **Backward compatible**: Campos nuevos son opcionales (NULL)
- ✅ **Idempotente**: Se puede ejecutar múltiples veces sin errores
- ✅ **Verificación automática**: Muestra esquema actualizado

#### Casos de Uso

##### 1. Trading Multi-Cuenta (DEMO + REAL)

```python
# Cuenta DEMO para práctica y desarrollo
signal_demo = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    confidence=0.85,
    connector_type=ConnectorType.METATRADER5,
    entry_price=1.1050,
    volume=0.01,
    # Traceability
    account_id="mt5-demo-001",
    account_type="DEMO",
    market_type="FOREX",
    platform="MT5"
)

# Cuenta REAL con dinero real (después de validar en DEMO)
signal_real = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    confidence=0.92,  # Mayor confianza para REAL
    connector_type=ConnectorType.METATRADER5,
    entry_price=1.1050,
    volume=0.01,
    # Traceability
    account_id="mt5-real-001",
    account_type="REAL",
    market_type="FOREX",
    platform="MT5",
    order_id="12345678"  # ID del broker
)

# Análisis separado
"""
SELECT account_type, COUNT(*) as trades, AVG(profit_loss) as avg_pnl
FROM trades
GROUP BY account_type;

Results:
  DEMO: 150 trades, avg_pnl: +12.5 pips
  REAL: 50 trades, avg_pnl: +8.2 pips  ← Más conservador
"""
```

##### 2. Trading Multi-Mercado (Forex + Crypto)

```python
# Estrategia de Forex en MT5
signal_forex = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    connector_type=ConnectorType.METATRADER5,
    market_type="FOREX",
    platform="MT5",
    timeframe="M5",
    account_type="REAL"
)

# Estrategia de Crypto en simulador (PAPER)
signal_crypto = Signal(
    symbol="BTCUSD",
    signal_type=SignalType.BUY,
    connector_type=ConnectorType.PAPER,
    market_type="CRYPTO",
    platform="PAPER",
    timeframe="1h",
    account_type="DEMO"
)

# Comparación de performance
"""
SELECT market_type, 
       COUNT(*) as total_trades,
       SUM(CASE WHEN is_win THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
       AVG(profit_loss) as avg_pnl
FROM trades
GROUP BY market_type;

Results:
  FOREX: 200 trades, 58% win_rate, +10.5 pips avg
  CRYPTO: 80 trades, 52% win_rate, +150 USD avg
"""
```

##### 3. Trading Multi-Plataforma (MT5 + NT8 + Binance)

```python
# MetaTrader 5 para Forex
signal_mt5 = Signal(
    symbol="GBPUSD",
    connector_type=ConnectorType.METATRADER5,
    platform="MT5",
    market_type="FOREX",
    account_id="mt5-real-001"
)

# NinjaTrader 8 para Futuros
signal_nt8 = Signal(
    symbol="NQ",  # Nasdaq Futures
    connector_type=ConnectorType.NINJATRADER8,
    platform="NT8",
    market_type="FUTURES",
    account_id="nt8-demo-001"
)

# Paper Trading para Crypto (simulación)
signal_paper = Signal(
    symbol="BTCUSD",
    connector_type=ConnectorType.PAPER,
    platform="PAPER",
    market_type="CRYPTO",
    account_id="paper-sim-001"
)

# Ranking de plataformas
"""
SELECT platform, market_type,
       COUNT(*) as signals,
       COUNT(CASE WHEN status='executed' THEN 1 END) as executed,
       COUNT(CASE WHEN status='executed' THEN 1 END) * 100.0 / COUNT(*) as exec_rate
FROM signals
GROUP BY platform, market_type
ORDER BY exec_rate DESC;

Results:
  MT5   | FOREX   : 300 signals, 285 executed (95%)
  NT8   | FUTURES : 100 signals, 92 executed (92%)
  PAPER | CRYPTO  : 150 signals, 150 executed (100%)  ← Simulación sin fallos
"""
```

#### Implementación en StorageManager

**Método mejorado**: `save_signal()`

```python
def save_signal(self, signal) -> str:
    """
    Save signal with full traceability.
    Persists WHERE the operation was executed.
    """
    signal_id = str(uuid.uuid4())
    
    # Extract traceability
    connector_type = signal.connector_type.value if hasattr(signal.connector_type, 'value') else str(signal.connector_type)
    
    cursor.execute('''
        INSERT INTO signals (
            id, symbol, signal_type, confidence, 
            entry_price, stop_loss, take_profit, 
            timestamp, date, status, metadata,
            -- Traceability fields
            connector_type, account_id, account_type, 
            market_type, platform, order_id, volume
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        signal_id,
        signal.symbol,
        signal.signal_type.value,
        signal.confidence,
        signal.entry_price,
        signal.stop_loss,
        signal.take_profit,
        signal.timestamp.isoformat(),
        date.today().isoformat(),
        "executed",
        json.dumps(metadata),
        # Traceability values
        connector_type,
        getattr(signal, 'account_id', None),
        getattr(signal, 'account_type', 'DEMO'),
        getattr(signal, 'market_type', 'FOREX'),
        getattr(signal, 'platform', None),
        getattr(signal, 'order_id', None),
        getattr(signal, 'volume', 0.01)
    ))
    
    logger.debug(
        f"Signal saved: {signal_id} | {signal.symbol} {signal.signal_type} | "
        f"Platform: {getattr(signal, 'platform', 'N/A')} | "
        f"Account: {getattr(signal, 'account_type', 'DEMO')} | "
        f"Market: {getattr(signal, 'market_type', 'FOREX')}"
    )
    
    return signal_id
```

#### Scripts de Utilidad

##### 1. Análisis de Datos
**Script**: `scripts/check_duplicates.py`
```bash
python scripts/check_duplicates.py

# Output:
# 📊 Total signals: 950
# 🔍 Exact duplicate signals: 0
# ⚠️  Signals without connector info: 950  ← Pre-migración
# ⚠️  Signals without account info: 950
```

##### 2. Limpieza de Duplicados
**Script**: `scripts/clean_duplicates.py`
```bash
python scripts/clean_duplicates.py  # DRY RUN

# Output:
# 🔍 Found 5 groups of duplicate signals
#   EURUSD BUY @ 2026-01-28T10:00:00: 3 copies → keeping 1, deleting 2
#   GBPUSD SELL @ 2026-01-28T11:30:00: 2 copies → keeping 1, deleting 1
# ⚠️  DRY RUN: Would delete 3 duplicate signals

# Ejecutar limpieza real (descomentando):
# clean_duplicate_signals(dry_run=False)
```

##### 3. Ejemplo Completo
**Script**: `scripts/example_traceability.py`
```python
# Creates 4 signals:
# 1. MT5 DEMO - Forex EURUSD
# 2. MT5 REAL - Forex GBPUSD
# 3. PAPER - Crypto BTCUSD
# 4. NT8 DEMO - Futures NQ

# Run:
python -c "import sys; sys.path.insert(0, '.'); exec(open('scripts/example_traceability.py').read())"

# Output:
# ✅ MT5 DEMO Forex: 43720cc6...
# ✅ MT5 REAL Forex: d3ee24ea...
# ✅ PAPER Crypto: 5cadd4c2...
# ✅ NT8 Futures: 1bd1b56e...
# 📊 Signals by platform:
#   MT5 | FOREX | DEMO: 1 signals
#   MT5 | FOREX | REAL: 1 signals
#   NT8 | FUTURES | DEMO: 1 signals
#   PAPER | CRYPTO | DEMO: 1 signals
```

#### Queries de Análisis

##### Performance por Tipo de Cuenta
```sql
SELECT 
    account_type,
    COUNT(*) as total_trades,
    SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
    ROUND(SUM(CASE WHEN is_win THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
    ROUND(AVG(profit_loss), 2) as avg_pnl,
    ROUND(SUM(profit_loss), 2) as total_pnl
FROM trades
WHERE account_type IS NOT NULL
GROUP BY account_type
ORDER BY total_pnl DESC;

-- Results:
-- account_type | total_trades | wins | win_rate | avg_pnl | total_pnl
-- REAL         | 120          | 72   | 60.00%   | +15.5   | +1,860
-- DEMO         | 450          | 252  | 56.00%   | +12.3   | +5,535
```

##### Performance por Mercado
```sql
SELECT 
    market_type,
    platform,
    COUNT(*) as trades,
    ROUND(AVG(profit_loss), 2) as avg_pnl,
    ROUND(SUM(commission + COALESCE(swap, 0)), 2) as total_costs
FROM trades
WHERE market_type IS NOT NULL
GROUP BY market_type, platform
ORDER BY avg_pnl DESC;

-- Results:
-- market_type | platform | trades | avg_pnl | total_costs
-- CRYPTO      | PAPER    | 85     | +150.2  | 0.00       ← Sin costos
-- FOREX       | MT5      | 320    | +10.8   | -125.50    ← Spreads + swap
-- FUTURES     | NT8      | 75     | +8.5    | -45.00     ← Comisiones bajas
```

##### Señales Ejecutadas por Plataforma
```sql
SELECT 
    platform,
    COUNT(*) as total_signals,
    COUNT(CASE WHEN status = 'executed' THEN 1 END) as executed,
    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
    ROUND(COUNT(CASE WHEN status = 'executed' THEN 1 END) * 100.0 / COUNT(*), 2) as exec_rate
FROM signals
WHERE platform IS NOT NULL
GROUP BY platform
ORDER BY exec_rate DESC;

-- Results:
-- platform | total_signals | executed | rejected | exec_rate
-- PAPER    | 200           | 200      | 0        | 100.00%  ← Simulación perfecta
-- MT5      | 450           | 428      | 22       | 95.11%   ← Alta confiabilidad
-- NT8      | 150           | 135      | 15       | 90.00%   ← Buena ejecución
```

#### Beneficios del Sistema

✅ **Separación DEMO/REAL**: Performance de práctica vs dinero real aislados  
✅ **Multi-Mercado**: Comparar Forex, Crypto, Stocks independientemente  
✅ **Multi-Plataforma**: MT5, NT8, Binance en paralelo sin confusión  
✅ **Auditoría Completa**: Cada operación rastreable hasta cuenta específica  
✅ **Reconciliación**: order_id permite validar contra statements del broker  
✅ **Portfolio Management**: Vista consolidada de todas las cuentas  
✅ **Análisis Granular**: Filtrar por cualquier combinación de dimensiones  
✅ **Costos Reales**: Track de commission + swap para PnL exacto  

#### Próximos Pasos

**1. OrderExecutor Enhancement**
- Auto-popular `account_id` desde conector configurado
- Capturar `order_id` del broker tras ejecución exitosa
- Validar que account existe en DB antes de ejecutar

**2. ClosingMonitor Update**
- Persistir traceability completa en tabla `trades`
- Incluir `commission` y `swap` en cálculo de PnL neto

---

### Sistema de Score Dinámico y Gestión de Instrumentos

**Implementado:** Enero 2026 (Fase 2.3 - Nivel 1)

#### Problema que Resuelve

**Contexto Previo:**
- El score (0-100) SE CALCULABA pero NO se usaba como filtro de ejecución
- Solo determinaba `MembershipTier` (Elite/Premium/Free) de forma cosmética
- Todas las señales con condiciones técnicas válidas se ejecutaban, independiente de calidad
- No había distinción entre instrumentos: EURUSD (major, spread 1 pip) = USDTRY (exotic, spread 15 pips)

**Necesidad Identificada:**
- Filtrar setups de baja calidad que cumplen condiciones técnicas pero tienen probabilidad marginal
- Exigir scores más altos en instrumentos volátiles/exóticos (mayores costos de transacción)
- Poder desactivar categorías completas (ej: exóticas nocturnas, altcoins en bear market)
- Control granular por usuario/membresía (básicos solo majors, premium todo)

#### Arquitectura Implementada

##### 1. Configuración de Instrumentos (`config/instruments.json`)

```json
{
  "FOREX": {
    "majors": {
      "enabled": true,
      "instruments": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"],
      "min_score": 70,
      "max_spread_pips": 2.0,
      "risk_multiplier": 1.0
    },
    "minors": {
      "enabled": true,
      "instruments": ["EURGBP", "EURJPY", "GBPJPY"],
      "min_score": 75,
      "max_spread_pips": 4.0,
      "risk_multiplier": 0.9
    },
    "exotics": {
      "enabled": false,  // ⬅️ Desactivadas por defecto
      "instruments": ["USDTRY", "USDZAR", "USDMXN"],
      "min_score": 90,   // ⬅️ Solo setups excepcionales
      "max_spread_pips": 30.0,
      "risk_multiplier": 0.5
    }
  },
  "CRYPTO": {
    "tier1": {
      "enabled": true,
      "instruments": ["BTCUSDT", "ETHUSDT"],
      "min_score": 75
    },
    "altcoins": {
      "enabled": false,
      "min_score": 85
    }
  },
  "_global_settings": {
    "default_min_score": 80,
    "unknown_instrument_action": "reject"
  }
}
```

**Rationale de Scores:**
- **Majors (70)**: Alta liquidez, spreads 0.5-2 pips, ejecuciones limpias → umbral permisivo
- **Minors (75)**: Liquidez media, spreads 2-4 pips → umbral moderado
- **Exotics (90)**: Baja liquidez, spreads 10-30 pips, gaps nocturnos → solo setups excepcionales
- **Crypto Tier1 (75)**: BTC/ETH con alta capitalización → similar a minors
- **Altcoins (85)**: Manipulación frecuente, pumps/dumps → requiere alta convicción

##### 2. InstrumentManager (`core_brain/instrument_manager.py`)

**Responsabilidades:**
- Clasificación automática de símbolos (EURUSD → FOREX/majors)
- Validación de habilitación antes de operar
- Proveer score mínimo dinámico por categoría
- Gestionar multiplicadores de riesgo
- Fallback conservador para símbolos desconocidos

**API Principal:**
```python
class InstrumentManager:
    def get_config(symbol: str) -> InstrumentConfig
    def is_enabled(symbol: str) -> bool
    def get_min_score(symbol: str) -> float
    def get_risk_multiplier(symbol: str) -> float
    def validate_symbol(symbol: str, score: float) -> Dict
    def get_category_info(symbol: str) -> Tuple[str, str]
```

**Auto-Clasificación:**
```python
# USDSGD (no en config) → auto-detecta USD + SGD → FOREX/majors
# ADAUSDT (no en config) → auto-detecta USDT suffix → CRYPTO/altcoins
# ES (futures) → auto-detecta 2-letter code → FUTURES/indices
```

##### 3. Integración con OliverVelezStrategy

**Flujo de Validación (Modificado):**

```python
# oliver_velez.py
async def analyze(symbol, df, regime):
    # 1. Validar condiciones técnicas (SMA200, Elephant, SMA20)
    validation_results = {...}
    
    # 2. Calcular score (0-100) basado en régimen/proximidad/fuerza
    score = self._calculate_opportunity_score(...)
    
    # 3. NUEVO: Validar contra umbral dinámico por instrumento
    validation = self.instrument_manager.validate_symbol(symbol, score)
    
    if not validation["valid"]:
        logger.info(
            f"[{symbol}] Setup técnicamente válido pero RECHAZADO: "
            f"{validation['rejection_reason']}"
        )
        return None  # ⬅️ NO genera Signal
    
    # 4. Si aprueba: generar Signal
    logger.info(f"[{symbol}] Setup APROBADO. Score: {score:.1f}")
    return Signal(...)
```

**Ejemplo de Ejecución:**

```
# Setup EURUSD (major)
[EURUSD] Validando condiciones: trend=✅, elephant=✅, sma20=✅
[EURUSD] Score calculado: 72.5
[EURUSD] Min score requerido: 70.0 (FOREX/majors)
[EURUSD] Setup APROBADO. Score: 72.5 >= 70.0
✅ Signal generada

# Setup USDTRY (exotic)
[USDTRY] Validando condiciones: trend=✅, elephant=✅, sma20=✅
[USDTRY] Score calculado: 72.5
[USDTRY] Min score requerido: 90.0 (FOREX/exotics)
[USDTRY] Setup técnicamente válido pero RECHAZADO: Score 72.5 < 90.0
❌ Signal NO generada

# Setup DOGEUSDT (altcoin desactivada)
[DOGEUSDT] Validando condiciones: trend=✅, elephant=✅, sma20=✅
[DOGEUSDT] Setup RECHAZADO: Instrument DOGEUSDT is disabled
❌ Signal NO generada (ni siquiera calcula score)
```

#### Tests Implementados

**Cobertura:** 20/20 tests pasando

**Categorías de Tests:**
1. **Clasificación**: Majors, minors, exotics, crypto (tier1/altcoins)
2. **Auto-Clasificación**: USDSGD, AUDNZD, símbolos desconocidos
3. **Habilitación**: Filtrado de instrumentos desactivados
4. **Scores**: Umbrales por categoría, fallback defaults
5. **Validación Completa**: Aprobación/rechazo por score + habilitación
6. **Multiplicadores de Riesgo**: Position sizing ajustado
7. **Integración**: OliverVelezStrategy con InstrumentManager
8. **Edge Cases**: Config faltante, símbolos malformados, case-insensitive

**Archivo:** [tests/test_instrument_filtering.py](tests/test_instrument_filtering.py)

#### Cálculo del Score (Actual - Nivel 1)

**Fórmula Base (Oliver Vélez):**
```python
score = 60.0  # Base fija

# Componente 1: Régimen de Mercado (+20 puntos si TREND)
if regime == MarketRegime.TREND:
    score += 20.0

# Componente 2: Proximidad a SMA20 (máximo +10 puntos)
proximity_ratio = sma20_dist_pct / 1.5
score += (1 - proximity_ratio) * 10.0

# Componente 3: Fuerza de Vela (máximo +10 puntos)
strength_ratio = body_atr_ratio / 0.3
score += min(1.0, strength_ratio - 1.0) * 10.0

return min(100.0, max(0.0, score))
```

**Rangos Típicos:**
- Setup perfecto en TREND: 90-100 puntos
- Setup bueno en RANGE: 70-80 puntos
- Setup marginal: 60-70 puntos

**Limitaciones Identificadas (Nivel 1):**
- ❌ Base arbitraria (60 puntos sin significado estadístico)
- ❌ Pesos NO calibrados con backtesting
- ❌ No penaliza por spread/slippage
- ❌ No aprende de resultados históricos

**Mejoras Planificadas:**
- **Nivel 2** (Score Adaptativo): Eliminar base, penalizar por spread, pesos ajustados (40/30/30)
- **Nivel 3** (Calibración): Ajustar umbrales basados en win-rate histórico (1000+ trades)
- **Nivel 4** (ML): Modelo predictivo entrenado con datos reales (500+ trades)

#### Beneficios del Sistema

✅ **Control de Calidad**: Solo ejecutar setups con probabilidad aceptable  
✅ **Gestión de Costos**: Evitar exóticas con spreads prohibitivos (USDTRY 15 pips)  
✅ **Flexibilidad de Usuario**: Activar/desactivar categorías vía config  
✅ **Protección de Capital**: Risk multipliers reducidos en instrumentos volátiles  
✅ **SaaS Ready**: Membresías Basic (solo majors) vs Premium (todo)  
✅ **Auto-Adaptación**: Tuner puede ajustar min_score por categoría según win-rate  
✅ **Transparencia**: Logs detallados de por qué se rechaza cada setup  
✅ **Testing Robusto**: 20 tests validan toda la lógica de filtrado

#### Casos de Uso

**1. Trader Conservador**
```json
// Habilitar solo majors con umbral alto
"majors": {"enabled": true, "min_score": 80},  // Solo setups excelentes
"minors": {"enabled": false},
"exotics": {"enabled": false}
```

**2. Trader Agresivo**
```json
// Habilitar todo con umbrales bajos
"majors": {"enabled": true, "min_score": 65},
"minors": {"enabled": true, "min_score": 70},
"exotics": {"enabled": true, "min_score": 80}  // Rebajado de 90
```

**3. Especialista en Crypto**
```json
"FOREX": {"majors": {"enabled": false}, ...},  // Sin Forex
"CRYPTO": {
  "tier1": {"enabled": true, "min_score": 70},
  "altcoins": {"enabled": true, "min_score": 80}
}
```

**4. Horario Nocturno (Evitar Exóticas)**
```json
// En horario 00:00-08:00 UTC: desactivar exoticas
"exotics": {"enabled": false}  // Evitar gaps nocturnos
```

#### Migración a Base de Datos (Próxima Implementación)

**Problema con JSON:**
- ❌ No permite configuración por usuario (multi-tenant)
- ❌ No hay UI para editar configuraciones
- ❌ Sin auditoría: ¿quién cambió qué y cuándo?
- ❌ No escala: 1000 usuarios = 1000 archivos JSON?

**Solución: Arquitectura 3-Tablas con Pivot**

```sql
-- Tabla 1: Categorías Globales (seed data)
CREATE TABLE instrument_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,           -- FOREX, CRYPTO, STOCKS, FUTURES
    subcategory TEXT NOT NULL,      -- majors, minors, exotics, tier1, altcoins
    enabled_default BOOLEAN DEFAULT 1,
    min_score_default REAL DEFAULT 75.0,
    risk_multiplier_default REAL DEFAULT 1.0,
    max_spread REAL,
    priority INTEGER DEFAULT 2,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(market, subcategory)
);

-- Tabla 2: Instrumentos Individuales
CREATE TABLE instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,    -- EURUSD, BTCUSDT, etc.
    category_id INTEGER NOT NULL,   -- FK a instrument_categories
    enabled_default BOOLEAN DEFAULT 1,
    min_score_override REAL,        -- NULL = usar default de categoría
    risk_multiplier_override REAL,
    max_spread_override REAL,
    metadata TEXT,                  -- JSON para extensibilidad
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES instrument_categories(id)
);

-- Tabla 3: Configuración por Usuario (PIVOT TABLE)
CREATE TABLE user_instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,          -- UUID del usuario (FK a users)
    instrument_id INTEGER NOT NULL, -- FK a instruments
    enabled BOOLEAN DEFAULT 1,      -- Override por usuario
    min_score REAL,                 -- NULL = usar default de instrument
    risk_multiplier REAL,           -- NULL = usar default de instrument
    max_spread REAL,
    notes TEXT,                     -- Notas personales del usuario
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id),
    UNIQUE(user_id, instrument_id)  -- 1 config por usuario-instrumento
);

-- Índices para performance
CREATE INDEX idx_user_instruments_user ON user_instruments(user_id);
CREATE INDEX idx_user_instruments_enabled ON user_instruments(user_id, enabled);
CREATE INDEX idx_instruments_symbol ON instruments(symbol);
CREATE INDEX idx_instruments_category ON instruments(category_id);
```

**Flujo de Consulta (Cascading Defaults):**

```python
# Nivel 1: Configuración de Usuario (más específico)
SELECT ui.enabled, ui.min_score, ui.risk_multiplier
FROM user_instruments ui
JOIN instruments i ON ui.instrument_id = i.id
WHERE ui.user_id = ? AND i.symbol = ?

# Si no existe → Nivel 2: Default de Instrumento
SELECT i.enabled_default, i.min_score_override, i.risk_multiplier_override
FROM instruments i
WHERE i.symbol = ?

# Si min_score_override IS NULL → Nivel 3: Default de Categoría
SELECT ic.min_score_default, ic.risk_multiplier_default
FROM instrument_categories ic
WHERE ic.id = i.category_id

# Si no existe instrumento → Nivel 4: Auto-clasificar y usar default global
# (Fallback conservador: min_score = 80, disabled)
```

**Ejemplo de Configuración Multi-Usuario:**

```sql
-- Usuario 1 (Conservador): Solo majors, score alto
INSERT INTO user_instruments (user_id, instrument_id, enabled, min_score)
SELECT 'user-001', i.id, 1, 85.0
FROM instruments i
JOIN instrument_categories ic ON i.category_id = ic.id
WHERE ic.subcategory = 'majors';

-- Usuario 2 (Agresivo): Todo habilitado, scores bajos
INSERT INTO user_instruments (user_id, instrument_id, enabled, min_score)
SELECT 'user-002', i.id, 1, 
    CASE ic.subcategory
        WHEN 'majors' THEN 65.0
        WHEN 'minors' THEN 70.0
        WHEN 'exotics' THEN 80.0
    END
FROM instruments i
JOIN instrument_categories ic ON i.category_id = ic.id;

-- Usuario 3 (Especialista Crypto): Solo crypto, Forex deshabilitado
UPDATE user_instruments
SET enabled = 0
WHERE user_id = 'user-003' AND instrument_id IN (
    SELECT i.id FROM instruments i
    JOIN instrument_categories ic ON i.category_id = ic.id
    WHERE ic.market = 'FOREX'
);
```

**Beneficios de la Arquitectura Pivot:**

✅ **Multi-Tenant Native**: Cada usuario tiene configuración independiente  
✅ **Cascading Defaults**: Usuario → Instrument → Category → Global  
✅ **Auditoría Completa**: `updated_at` rastrea cambios por usuario  
✅ **UI Ready**: Dashboard puede mostrar sliders por instrumento  
✅ **Escalabilidad**: 10,000 usuarios × 100 instrumentos = consultas eficientes con índices  
✅ **Flexibilidad**: Usuarios pueden override scores sin afectar defaults globales  
✅ **Sin Duplicación**: Un solo registro de EURUSD, múltiples configs por usuario  
✅ **Migración Gradual**: Seed data de JSON → DB, luego agregar UI

**Próxima Implementación:**
1. Script de migración: `scripts/migrate_instruments_to_db.py`
2. Modificar `InstrumentManager` para leer de DB con `user_id`
3. Crear `StorageManager.get_user_instrument_config(user_id, symbol)`
4. Tests multi-usuario en `test_instrument_filtering.py`
5. Dashboard UI: Tab "Mis Instrumentos" con toggles + sliders

#### Próximos Pasos (Niveles 2-4)

**Nivel 2 (Score Adaptativo - Prioridad Media):**
1. Eliminar base arbitraria (60 puntos)
2. Ajustar pesos: regime 40%, proximidad 35%, fuerza 25%
3. Penalizar por spread: `score *= (1 - spread_pct / 10.0)`
4. Tests de regresión para validar nuevo cálculo

**Nivel 3 (Calibración con Backtesting - Futuro):**
1. Ejecutar 1000+ trades simulados en datos históricos
2. Graficar win-rate vs score (0-100)
3. Ajustar umbrales por categoría (identificar score óptimo)
4. Validar mejora en Sharpe Ratio vs sistema sin filtro

**Nivel 4 (Score Predictivo ML - Futuro Lejano):**
1. Recolectar 500+ trades REALES (no simulados)
2. Features: [regime, proximity, strength, spread, hour_of_day, volatility]
3. Target: 1 si trade ganó, 0 si perdió
4. Entrenar Random Forest / XGBoost
5. Score = `probability * 100` (0-100)

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
│   ├── config.json          # Configuración general (scanner, timeframes, CPU)
│   ├── dynamic_params.json  # RegimeClassifier: ADX, volatilidad, etc.
│   ├── instruments.json     # Instrumentos habilitados por mercado/categoría
│   ├── modules.json         # Módulos de estrategias
│   ├── data_providers.example.env  # Template para API keys de proveedores
│   ├── telegram.example.env        # Template para Telegram notifications
│   └── demo_accounts/       # Credenciales de cuentas demo
├── core_brain/
│   ├── scanner.py           # Escáner proactivo multi-timeframe (ScannerEngine, CPUMonitor)
│   ├── regime.py            # RegimeClassifier + load_ohlc
│   ├── server.py            # FastAPI + WebSockets
│   ├── tuner.py             # Auto-calibración
│   ├── risk_manager.py      # Gestión de riesgo agnóstica + Lockdown persistente
│   ├── executor.py          # Ejecución de órdenes con Factory Pattern + Resiliencia
│   ├── signal_factory.py    # Generación de señales (Oliver Vélez) + Multi-timeframe
│   ├── notificator.py       # Notificaciones Telegram
│   ├── module_manager.py    # Gestión de membresías
│   ├── monitor.py           # Health monitoring
│   ├── main_orchestrator.py # Orquestador resiliente con SessionStats
│   ├── instrument_manager.py# Gestión de instrumentos por mercado
│   ├── data_provider_manager.py # Sistema multi-proveedor con fallback
│   └── strategies/
│       ├── base_strategy.py # Clase base para estrategias
│       └── oliver_velez.py  # Estrategia Oliver Vélez Swing v2
├── connectors/
│   ├── data_provider_manager.py # Sistema multi-proveedor con fallback automático
│   ├── generic_data_provider.py # Yahoo Finance (gratis, sin auth)
│   ├── ccxt_provider.py         # CCXT (crypto exchanges, gratis)
│   ├── alphavantage_provider.py # Alpha Vantage (deprecated - removed)
│   ├── twelvedata_provider.py   # Twelve Data (800 req/día gratis)
│   ├── polygon_provider.py      # Polygon.io (requiere pago)
│   ├── iex_cloud_provider.py    # IEX Cloud (50k req/mes gratis)
│   ├── finnhub_provider.py      # Finnhub (60 req/min gratis)
│   ├── mt5_data_provider.py     # OHLC vía copy_rates_from_pos (sin gráficas)
│   ├── mt5_connector.py         # Conector MT5 para ejecución de órdenes
│   ├── mt5_discovery.py         # Auto-discovery de instalaciones MT5
│   ├── paper_connector.py       # Paper trading (simulación)
│   ├── auto_provisioning.py     # Auto-provisioning de cuentas demo
│   ├── bridge_mt5.py            # Bridge WebSocket MT5 → Aethelgard
│   ├── bridge_nt8.cs            # Bridge WebSocket NT8 → Aethelgard
│   └── webhook_tv.py            # Webhook TradingView → Aethelgard
├── data_vault/              # Persistencia SQLite
│   ├── storage.py           # StorageManager con multi-timeframe support
│   ├── aethelgard.db        # Base de datos principal
│   └── system_state.json    # Estado del sistema (backup)
├── models/                  # Modelos de datos (Signal, MarketRegime, etc.)
│   └── signal.py            # Signal model con timeframe support
├── tests/                   # Tests TDD (134 tests)
│   ├── test_scanner_multiframe.py      # Tests de scanner multi-timeframe (6)
│   ├── test_multiframe_deduplication.py # Tests deduplicación multi-frame (6)
│   ├── test_dynamic_deduplication.py   # Tests ventanas dinámicas (13)
│   ├── test_orchestrator.py            # Tests orquestador (11)
│   ├── test_orchestrator_recovery.py   # Tests resiliencia (10)
│   ├── test_risk_manager.py            # Tests risk manager (4)
│   ├── test_executor.py                # Tests executor (7)
│   ├── test_signal_factory.py          # Tests signal factory (3)
│   ├── test_data_provider_manager.py   # Tests data providers (10)
│   ├── test_broker_storage.py          # Tests broker storage (5)
│   ├── test_instrument_filtering.py    # Tests instrument manager (6)
│   └── verify_architecture_ready.py    # Validación arquitectura
├── scripts/
│   ├── migrations/          # Migraciones one-time de DB
│   │   ├── migrate_add_timeframe.py
│   │   ├── migrate_broker_schema.py
│   │   ├── migrate_credentials_to_db.py
│   │   └── seed_brokers_platforms.py
│   └── utilities/           # Scripts recurrentes
│       ├── check_system.py
│       ├── check_duplicates.py
│       ├── clean_duplicates.py
│       ├── setup_mt5_demo.py
│       └── simulate_trades.py
├── docs/
│   ├── TIMEFRAMES_CONFIG.md # Guía configuración timeframes
│   ├── DATA_PROVIDERS.md    # Guía proveedores de datos
│   └── MT5_INSTALLATION.md  # Guía instalación MT5
├── ui/
│   └── dashboard.py         # Dashboard Streamlit
├── utils/
│   └── encryption.py        # Encriptación de credenciales
├── main.py                  # Entrypoint principal
├── start.py                 # Startup con health checks
├── run_scanner.py           # Entrypoint del escáner proactivo
└── AETHELGARD_MANIFESTO.md  # ÚNICA FUENTE DE VERDAD
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
- **Yahoo como Red de Seguridad**: Si todos los proveedores fallan o ninguno está configurado, el sistema automáticamente usa Yahoo Finance de forma temporal (sin guardar el cambio en DB)
- **Configuración por Prioridad**: Define el orden de uso en base de datos (tabla `data_providers`)
- **Activación/Desactivación**: Control granular de cada proveedor desde Dashboard
- **Dashboard Integrado**: Gestión visual de proveedores y API keys

### Arquitectura de Brokers y Cuentas

Aethelgard separa conceptualmente **Brokers** (catálogo de proveedores) de **Broker Accounts** (cuentas específicas del usuario):

#### Brokers (Catálogo):
- **Tabla**: `brokers`
- **Propósito**: Definir qué brokers están disponibles en el sistema
- **Propiedades**: `broker_id`, `name`, `type`, `auto_provision_available`, etc.
- **NO tiene columna `enabled`**: Los brokers son solo metadatos, no se habilitan/deshabilitan

#### Broker Accounts (Cuentas del Usuario):
- **Tabla**: `broker_accounts`
- **Propósito**: Cuentas de trading configuradas por el usuario
- **Propiedades**: `account_id`, `broker_id`, `account_name`, `login`, `enabled`, `account_type` (demo/real)
- **SÍ tiene columna `enabled`**: Las cuentas se habilitan/deshabilitan individualmente

**Ejemplo**:
```python
# Broker en catálogo (siempre "disponible")
binance_broker = {
    "broker_id": "binance",
    "name": "Binance",
    "auto_provision_available": True
}

# Cuenta del usuario (puede habilitarse/deshabilitarse)
mi_cuenta_binance = {
    "account_id": "uuid-123",
    "broker_id": "binance",
    "account_name": "Mi Cuenta Demo",
    "enabled": True,  # ← enabled SOLO aquí
    "account_type": "demo"
}
```

### Configuración de Timeframes

El sistema permite configurar qué timeframes se escanean por cada instrumento:

#### Timeframes Disponibles

| Timeframe | Período | Uso Recomendado | Ventana Dedup | Default |
|-----------|---------|-----------------|---------------|---------|
| M1 | 1 minuto | Scalping agresivo | 10 min | ❌ Disabled |
| M5 | 5 minutos | Scalping moderado | 20 min | ✅ Enabled |
| M15 | 15 minutos | Day trading | 45 min | ✅ Enabled |
| H1 | 1 hora | Day/Swing trading | 120 min | ✅ Enabled |
| H4 | 4 horas | Swing trading | 480 min | ✅ Enabled |
| D1 | Diario | Position trading | 1440 min | ✅ Enabled |

#### Ejemplo de Configuración

**[config/config.json](config/config.json)**:
```json
{
  "scanner": {
    "timeframes": [
      {"timeframe": "M1", "enabled": false},
      {"timeframe": "M5", "enabled": true},
      {"timeframe": "M15", "enabled": true},
      {"timeframe": "H1", "enabled": true},
      {"timeframe": "H4", "enabled": true},
      {"timeframe": "D1", "enabled": true}
    ],
    "scan_mode": "STANDARD",
    "cpu_limit_pct": 80.0
  }
}
```

#### Perfiles Predefinidos

**Scalper** (rápido, alta frecuencia):
```json
"timeframes": [
  {"timeframe": "M1", "enabled": true},
  {"timeframe": "M5", "enabled": true},
  {"timeframe": "M15", "enabled": false}
]
```

**Swing Trader** (lento, baja frecuencia):
```json
"timeframes": [
  {"timeframe": "H1", "enabled": true},
  {"timeframe": "H4", "enabled": true},
  {"timeframe": "D1", "enabled": true}
]
```

**Multi-Estrategia** (cobertura total):
```json
"timeframes": [
  {"timeframe": "M5", "enabled": true},
  {"timeframe": "H1", "enabled": true},
  {"timeframe": "H4", "enabled": true},
  {"timeframe": "D1", "enabled": true}
]
```

**📚 Documentación completa**: [docs/TIMEFRAMES_CONFIG.md](docs/TIMEFRAMES_CONFIG.md)

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

## 🧪 Tests y Calidad de Código

### Suite de Tests (134/134 passing)

Aethelgard mantiene una cobertura de tests del 100% de funcionalidades críticas:

**Core Brain (47 tests):**
- `test_orchestrator.py` (11 tests): Ciclo completo, frecuencia dinámica, shutdown
- `test_orchestrator_recovery.py` (10 tests): Resiliencia, SessionStats, crash recovery
- `test_risk_manager.py` (4 tests): Position sizing, lockdown, régimen adaptativo
- `test_executor.py` (7 tests): Ejecución de órdenes, validación, factory pattern
- `test_signal_factory.py` (3 tests): Generación de señales, Oliver Vélez
- `test_monitor.py` (3 tests): Health monitoring, metrics
- `test_tuner_edge.py` (4 tests): Auto-calibración, edge detection
- `test_regime_classifier.py` (5 tests): Clasificación de régimen, histéresis

**Scanner & Multi-Timeframe (19 tests):**
- `test_scanner_multiframe.py` (6 tests): Escaneo multi-timeframe, configuración
- `test_multiframe_deduplication.py` (6 tests): Deduplicación por (symbol, timeframe)
- `test_dynamic_deduplication.py` (13 tests): Ventanas dinámicas, timeframes
- `test_signal_deduplication.py` (6 tests): Prevención de duplicados

**Data & Storage (38 tests):**
- `test_data_provider_manager.py` (10 tests): Multi-proveedor, fallback Yahoo
- `test_data_providers.py` (10 tests): Proveedores individuales
- `test_broker_storage.py` (5 tests): Gestión de cuentas, brokers
- `test_instrument_filtering.py` (6 tests): InstrumentManager, validación
- Storage tests (7 tests): Persistencia, recuperación

**Integration Tests:**
- `verify_architecture_ready.py`: Validación de arquitectura agnóstica
- End-to-end workflow tests

### Metodología TDD

Todos los componentes críticos se desarrollan siguiendo Test-Driven Development:
1. Escribir test que falla
2. Implementar código mínimo para pasar
3. Refactorizar manteniendo tests verdes
4. Documentar en manifesto

### Ejecución de Tests

```bash
# Suite completa
pytest tests/ -v

# Tests específicos
pytest tests/test_scanner_multiframe.py -v
pytest tests/test_orchestrator_recovery.py -v

# Con coverage
pytest tests/ --cov=core_brain --cov-report=html
```

---

## 📚 Documentación Técnica

### Guías de Usuario

- **[TIMEFRAMES_CONFIG.md](docs/TIMEFRAMES_CONFIG.md)**: Configuración de timeframes activos
  - Casos de uso por perfil de trader (scalper, swing, multi-estrategia)
  - Impacto en rendimiento y CPU
  - Mejores prácticas y troubleshooting

- **[DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md)**: Gestión de proveedores de datos
  - Configuración de API keys
  - Sistema de fallback automático
  - Comparativa de proveedores

- **[MT5_INSTALLATION.md](docs/MT5_INSTALLATION.md)**: Instalación y configuración de MetaTrader 5
  - Setup de cuenta demo
  - Configuración de conectores
  - Troubleshooting común

### Migraciones de Base de Datos

**Ubicación**: `scripts/migrations/`

- `migrate_add_timeframe.py`: Agrega columna timeframe a tabla signals
- `migrate_broker_schema.py`: Separa brokers de broker_accounts
- `migrate_credentials_to_db.py`: Migra credenciales a DB encriptado
- `seed_brokers_platforms.py`: Pobla catálogo de brokers

**Ejecución**:
```bash
python scripts/migrations/migrate_add_timeframe.py
```

### Scripts Utilitarios

**Ubicación**: `scripts/utilities/`

- `check_system.py`: Diagnóstico completo del sistema
- `check_duplicates.py`: Detecta datos duplicados
- `clean_duplicates.py`: Limpia duplicados de DB
- `setup_mt5_demo.py`: Configuración automática de MT5 demo
- `simulate_trades.py`: Simulación de trades para testing

---

## 🔄 Actualización del Manifiesto

**Última Actualización**: 29 de Enero 2026
- ✅ Implementado sistema multi-proveedor de datos con 6 proveedores
- ✅ Fallback automático a Yahoo cuando no hay proveedores configurados
- ✅ Suite de tests 100% funcional (147/147 passing)
- ✅ Arquitectura de brokers migrada a DB (brokers + broker_accounts)
- ✅ Dashboard con gestión de proveedores, brokers y cuentas
- ✅ Correcciones de API deprecated en StorageManager
- ✅ **Deduplicación multi-timeframe**: Permite señales simultáneas del mismo instrumento en diferentes timeframes
- ✅ **Scanner filtrado**: Solo escanea instrumentos habilitados en `instruments.json`
- ✅ **Scanner multi-timeframe**: Escanea todos los timeframes activos configurables por el usuario
- ✅ **Performance Optimization**: Cache de proveedores elimina 750+ consultas DB por ciclo (3x faster)
- ✅ **RegimeClassifier Cache**: Cache de parámetros elimina 120 lecturas de archivo en startup
- ✅ **Symbol Normalization**: Compatibilidad transparente con Yahoo Finance (símbolos =X)
- ✅ **Multi-Timeframe Confluence**: Sistema EDGE para reforzar señales con alineación de temporalidades

### Cambios Críticos Recientes

#### Multi-Timeframe Confluence System with EDGE (30/01/2026)

**Mejora Implementada**: Sistema de confluencia inteligente que refuerza/penaliza señales basándose en alineación con timeframes superiores. **Aprende automáticamente** los pesos óptimos mediante EdgeTuner.

**Características**:

1. **Análisis Automático de Confluencia**:
   - **Bullish Signal + Timeframes Aligned TREND**: Incrementa `confidence` hasta +45%
   - **Bullish Signal + Counter-Trend Higher TFs**: Penaliza hasta -30%
   - **Range/Neutral**: Sin efecto (preserva señal original)

2. **Pesos Configurables por Timeframe** ([config/dynamic_params.json](config/dynamic_params.json)):
   ```json
   "multi_timeframe_confluence": {
     "weights": {
       "M15": 15.0,  // Confirmación rápida
       "H1": 20.0,   // Mayor peso (tendencia intermedia)
       "H4": 15.0,   // Swing trading
       "D1": 10.0    // Tendencia macro
     }
   }
   ```

3. **Integración con EDGE (Auto-Learning)**:
   - EdgeTuner ejecuta backtests con diferentes combinaciones de pesos
   - Optimiza basándose en `win_rate` de señales ajustadas
   - Guarda pesos óptimos en `dynamic_params.json`
   - El sistema aprende qué temporalidades son más predictivas

4. **Metadatos Completos de Confluencia**:
   ```python
   signal.metadata = {
     "confluence_analysis": {
       "aligned_timeframes": ["H1_TREND", "H4_TREND"],
       "counter_timeframes": [],
       "neutral_timeframes": ["M15_RANGE"],
       "total_bonus": 35.0,
       "final_confidence": 85.0,  # Original: 50.0
       "weights_used": {"H1": 20.0, "H4": 15.0}
     }
   }
   ```

5. **Modo A/B Testing**:
   ```json
   "confluence": {
     "enabled": true  // false = desactivar para comparar resultados
   }
   ```

**Flujo de Procesamiento**:
```
Scanner (multi-TF) → SignalFactory → Genera señales
                                    ↓
                         _apply_confluence() agrupa por símbolo
                                    ↓
                   MultiTimeframeConfluenceAnalyzer.analyze_confluence()
                                    ↓
                   Ajusta confidence según alineación
                                    ↓
                   Retorna señales con metadata completa
```

**Beneficios**:
- **+25% Win Rate** (proyección): Filtra señales contra-tendencia en timeframes superiores
- **Transparencia**: Metadata muestra exactamente por qué se ajustó cada señal
- **Auto-Calibración**: Sistema aprende sin intervención humana
- **Escalable**: Añadir nuevos timeframes solo requiere configuración

**Tests Agregados**:
- [test_confluence.py](tests/test_confluence.py) (8 tests):
  - Refuerzo bullish con timeframes alineados
  - Penalización con timeframes opuestos
  - Pesos diferenciales (H1 > M15)
  - Carga de pesos desde dynamic_params.json
  - Actualización de pesos desde EdgeTuner
  - Modo disabled preserva señal original

**Archivos Nuevos**:
- [core_brain/confluence.py](core_brain/confluence.py): Motor de análisis de confluencia

**Archivos Modificados**:
- [core_brain/signal_factory.py](core_brain/signal_factory.py): Integración con `_apply_confluence()`
- [config/config.json](config/config.json): Flag `confluence.enabled`
- [config/dynamic_params.json](config/dynamic_params.json): Pesos por timeframe

#### Symbol Normalization - Yahoo Finance Compatibility (30/01/2026)

**Problema Detectado**: Yahoo Finance requiere símbolos forex con sufijo `=X` (ej: `EURUSD=X`), pero [instruments.json](config/instruments.json) usa formato estándar (`EURUSD`). Esto generaba warnings: `"Symbol AUDUSD=X not found in configuration"`.

**Solución Implementada**:

1. **Normalización Transparente en InstrumentManager**:
   ```python
   def get_config(self, symbol: str) -> Optional[InstrumentConfig]:
       # Normalize Yahoo Finance symbols (EURUSD=X -> EURUSD)
       normalized_symbol = symbol.upper().replace("=X", "")
       
       if normalized_symbol in self.symbol_cache:
           return self.symbol_cache[normalized_symbol]
       
       config = self._auto_classify(normalized_symbol)
       if config:
           self.symbol_cache[normalized_symbol] = config
           return config
       
       logger.warning(f"Symbol {symbol} not found in configuration")
       return None
   ```

2. **Ventajas de esta Solución**:
   - **Configuración Limpia**: [instruments.json](config/instruments.json) mantiene formato estándar sin sufijos
   - **Compatibilidad Universal**: Acepta tanto `EURUSD` como `EURUSD=X`
   - **Cache Compartido**: Ambos formatos comparten misma entrada en cache
   - **Transparente**: Resto del sistema no afectado

3. **Test de Validación**:
   ```python
   def test_yahoo_finance_symbol_normalization(self):
       # Verifica que EURUSD=X se normaliza a EURUSD
       config_yahoo = self.manager.get_config("EURUSD=X")
       config_standard = self.manager.get_config("EURUSD")
       assert config_yahoo == config_standard
       assert config_yahoo.symbol == "EURUSD"
   ```

**Resultado**: 0 warnings, sistema funciona con cualquier proveedor de datos sin modificar configuraciones.

**Archivos Modificados**:
- [core_brain/instrument_manager.py](core_brain/instrument_manager.py): Normalización de símbolos
- [tests/test_instrument_filtering.py](tests/test_instrument_filtering.py): Test de validación (21/21 passing)

#### RegimeClassifier Parameter Cache (30/01/2026)

**Problema Detectado**: Con multi-timeframe scanning (24 símbolos × 5 timeframes = 120 instancias), cada `RegimeClassifier` cargaba parámetros desde [dynamic_params.json](config/dynamic_params.json) en startup, generando:
- **120 lecturas de archivo** del mismo JSON
- **120 mensajes de log INFO** "Parámetros cargados desde config/dynamic_params.json"

**Solución Implementada**:

1. **Singleton Pattern para Parámetros**:
   ```python
   class RegimeClassifier:
       _params_cache: Dict[str, Dict] = {}  # ✅ Shared cache across all instances
       
       def _load_params_from_config(self, config_path: str, force_reload: bool = False) -> Dict:
           if not force_reload and config_path in RegimeClassifier._params_cache:
               return RegimeClassifier._params_cache[config_path]
           
           # Load from file only if not cached
           with open(config_path, "r") as f:
               all_params = json.load(f)
           
           regime_params = all_params.get("regime_classifier", {})
           RegimeClassifier._params_cache[config_path] = regime_params
           logger.debug(f"Parámetros cargados desde {config_path}")  # ✅ Changed to DEBUG
           return regime_params
       
       @staticmethod
       def reload_params() -> None:
           """Invalidate cache to force reload (called by EdgeTuner)"""
           RegimeClassifier._params_cache.clear()
   ```

2. **Integración con EdgeTuner**:
   - Cuando EdgeTuner optimiza parámetros y guarda nuevos valores en `dynamic_params.json`
   - Llama a `RegimeClassifier.reload_params()` para invalidar cache
   - Próxima instancia carga valores frescos automáticamente

3. **Mejora de Performance**:
   - **ANTES**: 120 lecturas de archivo en startup
   - **DESPUÉS**: 1 lectura de archivo, compartida entre todas las instancias
   - **Log Cleanliness**: INFO → DEBUG (solo visible en modo verbose)

**Resultado**: Startup limpio, sin mensajes repetidos, performance mejorada.

**Archivos Modificados**:
- [core_brain/regime.py](core_brain/regime.py): Cache de parámetros + método reload
- [tests/test_regime_cache.py](tests/test_regime_cache.py): Validación de cache (5/5 passing)

#### Performance Optimization - Provider Cache (30/01/2026)

**Problema Detectado**: El sistema cargaba 6 proveedores de datos desde SQLite en **cada llamada** a `fetch_ohlc()`, generando 750+ consultas DB por ciclo de scanner.

**Solución Implementada**:

1. **Singleton Pattern para Configuración**:
   ```python
   # ANTES: DB load on every call
   async def get_active_providers(self) -> List[DataProvider]:
       return self._load_configuration()  # ❌ 750+ DB queries
   
   # DESPUÉS: Cached configuration
   async def get_active_providers(self, force_reload: bool = False) -> List[DataProvider]:
       if force_reload or not self._cached_providers:
           self._cached_providers = self._load_configuration()
       return self._cached_providers  # ✅ 1 DB query on startup
   ```

2. **Cache Invalidation Method**:
   ```python
   def reload_providers(self):
       """Invalida cache cuando usuario modifica configuración."""
       self._cached_providers = None
       self._instances.clear()
   ```

3. **Impacto Medido**:
   - **ANTES**: ~10s para 100 fetches (750+ DB queries)
   - **DESPUÉS**: ~1s para 100 fetches (1 DB query inicial)
   - **Performance Gain**: **3x más rápido**

**Tests Agregados**:
- [test_provider_cache.py](tests/test_provider_cache.py) (5 tests):
  - Carga única en inicialización
  - Reutilización de instancias
  - Invalidación de cache
  - Cache compartido entre instancias
  - Medición de rendimiento

**Archivos Modificados**:
- [core_brain/data_provider_manager.py](core_brain/data_provider_manager.py): Parámetro `force_reload`, método `reload_providers()`

#### Logging Configuration System (30/01/2026)

**Mejora Implementada**: Control granular de logs por módulo para evitar console spam.

**Características**:

1. **Configuración en [config.json](config/config.json)**:
   ```json
   "logging": {
     "global_level": "INFO",
     "module_levels": {
       "core_brain.strategies.oliver_velez": "INFO",
       "core_brain.data_provider_manager": "WARNING"
     },
     "performance_mode": false
   }
   ```

2. **Cambios en Estrategias**:
   - `logger.info` → `logger.debug` para análisis detallados
   - Solo resultados críticos (señales generadas) en INFO
   - Análisis técnicos completos disponibles en DEBUG

**Beneficio**: Console legible sin perder capacidad de debugging.

### Cambios Críticos Recientes

#### Multi-Timeframe Scanning System (29/01/2026)

**Mejora Implementada**: El scanner ahora escanea múltiples timeframes simultáneamente por cada símbolo.

**Características**:

1. **Configuración de Timeframes Activos** ([config.json](config/config.json#L13-L20)):
   ```json
   "timeframes": [
     {"timeframe": "M1", "enabled": false},
     {"timeframe": "M5", "enabled": true},
     {"timeframe": "M15", "enabled": true},
     {"timeframe": "H1", "enabled": true},
     {"timeframe": "H4", "enabled": true},
     {"timeframe": "D1", "enabled": true}
   ]
   ```
   - Usuario puede activar/desactivar timeframes individualmente
   - Por defecto: M5, M15, H1, H4, D1 activos
   - M1 desactivado (demasiado ruido)

2. **Arquitectura de Clasificadores**:
   - Un clasificador por cada combinación (symbol, timeframe)
   - Ejemplo: EURUSD con 5 timeframes = 5 clasificadores independientes
   - Clave interna: `"symbol|timeframe"` (ej: `"EURUSD|M5"`)

3. **Procesamiento Paralelo**:
   - ThreadPoolExecutor procesa todas las combinaciones simultáneamente
   - Control de CPU respeta límite configurado
   - Priorización por régimen (TREND cada 1s, RANGE cada 10s)

4. **Flujo de Datos**:
   ```
   Scanner → Dict["symbol|timeframe"] → {
     "regime": MarketRegime,
     "df": DataFrame,
     "symbol": str,
     "timeframe": str
   } → SignalFactory → Signals con timeframe específico
   ```

**Beneficios**:
- **Scalping + Swing simultáneos**: Opera M5 para scalping y H4 para swing en el mismo instrumento
- **Confirmación multi-temporalidad**: Detecta alineación de tendencias cross-timeframe
- **Flexibilidad total**: Usuario controla qué timeframes analizar

**Tests Agregados**:
- [test_scanner_multiframe.py](tests/test_scanner_multiframe.py) (6 tests)
- Validación de carga de configuración
- Validación de clasificadores por combinación
- Validación de procesamiento independiente

**Archivos Modificados**:
- [config/config.json](config/config.json): Array de timeframes con flags enabled
- [core_brain/scanner.py](core_brain/scanner.py#L120-L145): Multi-timeframe support
- [core_brain/signal_factory.py](core_brain/signal_factory.py#L93-L134): Timeframe en signals

#### Signal Deduplication Strategy (29/01/2026)

**Problema Resuelto**: El sistema generaba señales duplicadas y escaneaba instrumentos no configurados.

**Solución Implementada**:

1. **Deduplicación por (symbol, signal_type, timeframe)**: 
   - Clave única: `(symbol, signal_type, timeframe)`
   - Permite scalping en M5 y swing trading en H4 simultáneamente
   - Ventana de deduplicación dinámica según timeframe (M5=20min, H4=480min)

2. **Scanner filtrado por InstrumentManager**:
   - El scanner solo procesa instrumentos habilitados en `config/instruments.json`
   - Elimina demanda innecesaria a proveedores de datos
   - MainOrchestrator inicializa scanner con `InstrumentManager.get_enabled_symbols()`

3. **Schema Update**:
   - Agregada columna `timeframe` a tabla `signals` (SQLite)
   - Migración: `scripts/migrations/migrate_add_timeframe.py`
   - Default value: `M5`

**Tests Agregados**:
- `tests/test_multiframe_deduplication.py` (6 tests)
- Validación de señales en diferentes timeframes
- Validación de ventanas de deduplicación dinámicas

**Archivos Modificados**:
- `data_vault/storage.py`: `has_recent_signal()` ahora considera timeframe
- `core_brain/main_orchestrator.py`: Scanner usa `InstrumentManager.get_enabled_symbols()`
- `core_brain/signal_factory.py`: Documentación actualizada de deduplicación

---

## 🔧 **2026-01-31: Implementación de Métodos Faltantes - Broker Storage**

**Contexto**: Los tests de `test_broker_storage.py` identificaron métodos faltantes en `StorageManager` que impedían la funcionalidad completa de gestión de brokers.

**Métodos Implementados**:

### 1. `get_broker(broker_id: str) -> Optional[Dict]`
- **Propósito**: Obtener un broker específico del catálogo por su ID
- **Retorno**: Diccionario con campos del broker + campos calculados (`broker_id`, `auto_provisioning`)
- **Campos complejos**: Listas/dicts se exponen como strings JSON para compatibilidad con tests de serialización

### 2. `get_account(account_id: str) -> Optional[Dict]`  
- **Propósito**: Obtener una cuenta de broker específica por su ID
- **Retorno**: Diccionario con todos los campos de la cuenta desde tabla `broker_accounts`

### 3. `get_broker_accounts(enabled_only: bool = False) -> List[Dict]`
- **Propósito**: Obtener cuentas de broker con filtro opcional por estado habilitado
- **Parámetros**: 
  - `enabled_only`: Si `True`, retorna solo cuentas con `enabled = 1`
- **Retorno**: Lista de diccionarios con datos de cuentas

### 4. Modificaciones a `save_broker_account()`
- **Firma**: `save_broker_account(self, *args, **kwargs) -> str`
- **Compatibilidad**: Acepta múltiples formatos de llamada:
  - Diccionario: `save_broker_account({'broker_id': 'xm', 'login': '12345'})`
  - Parámetros nombrados: `save_broker_account(broker_id='xm', login='12345')`
  - Argumentos posicionales: `save_broker_account('xm', 'api', 'Demo Account', True)`
- **Funcionalidad adicional**: 
  - Genera `account_id` automáticamente si no se proporciona
  - Guarda credenciales automáticamente si se incluye `password`
  - Retorna el `account_id` generado

### 5. Modificaciones a `get_credentials()`
- **Firma**: `get_credentials(self, account_id: str, credential_type: Optional[str] = None)`
- **Funcionalidad**: 
  - Sin `credential_type`: retorna diccionario completo de credenciales
  - Con `credential_type`: retorna solo esa credencial específica (ej: `'password'`)

### 6. Actualización de tabla `broker_accounts`
**Nuevos campos agregados**:
- `broker_id TEXT`: ID del broker al que pertenece la cuenta
- `account_name TEXT`: Nombre descriptivo de la cuenta  
- `account_number TEXT`: Número/login de la cuenta

**Schema actual**:
```sql
CREATE TABLE broker_accounts (
    id TEXT PRIMARY KEY,
    broker_id TEXT,
    platform_id TEXT NOT NULL,
    account_name TEXT,
    account_number TEXT,
    login TEXT NOT NULL,
    password TEXT,
    server TEXT,
    type TEXT DEFAULT 'demo',
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Resultados**:
- ✅ **8/8 tests de broker storage PASAN**
- ✅ Funcionalidad de brokers operativa en Dashboard UI
- ✅ Compatibilidad backward con código existente
- ✅ Tests reflejan funcionalidad real del sistema
- ✅ **0 warnings de deprecación** (sqlite3 datetime adapter corregido)

### 7. Corrección de Warnings de Deprecación (Python 3.12+)
**Problema**: Warnings de sqlite3 sobre adaptadores de datetime deprecated en Python 3.12+
**Solución implementada**:
```python
import sqlite3
from datetime import datetime

# Registrar adaptadores para datetime
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("timestamp", lambda s: datetime.fromisoformat(s.decode()))
```
**Ubicación**: `data_vault/storage.py` (líneas 1-6)
**Resultado**: ✅ Eliminados todos los warnings de deprecación en tests

---

## 🔍 HERRAMIENTAS DE VALIDACIÓN ARQUITECTURA

### Architecture Audit Script
**Archivo:** `scripts/architecture_audit.py`  
**Uso:** `python scripts/architecture_audit.py`

**Detecta:**
- ✅ Métodos duplicados en clases
- ✅ Abuso de context managers en _get_conn()
- ✅ Métodos sobreescritos accidentalmente

**Ejecutar ANTES de cada commit** (parte del checklist de desarrollo).

### QA Guard
**Archivo:** `scripts/qa_guard.py`  
**Uso:** `python scripts/qa_guard.py`

**Valida:**
- Sintaxis de Python en todos los archivos
- Imports válidos
- Tipos de dato correctos
- Complejidad ciclomática

### Code Quality Analyzer
**Archivo:** `scripts/code_quality_analyzer.py`  
**Uso:** `python scripts/code_quality_analyzer.py`

**Detecta:**
- Copy-paste (>80% similitud)
- Complejidad ciclomática alta

### Validación Completa
**Archivo:** `scripts/validate_all.py`  
**Uso:** `python scripts/validate_all.py`

**Incluye:**
- Architecture Audit
- QA Guard
- Code Quality
- Tests críticos (Deduplicación + Risk Manager)

### Limpieza de Deuda Técnica (Opción B) ✅ COMPLETADO
**Fecha:** 2026-02-02

**Resultados:**
- ✅ 0 métodos duplicados
- ✅ 0 abusos de context managers en `_get_conn()`
- ✅ Complejidad dentro de límites
- ✅ `validate_all.py` PASS

---

Este documento debe actualizarse cuando:
- Se complete una fase del roadmap
- Se añada una nueva estrategia
- Se modifique la arquitectura fundamental
- Se cambien las reglas de autonomía

**Mantenedor**: Equipo de desarrollo Aethelgard  
**Revisión**: Mensual o tras cambios significativos  
**Tools**: `scripts/architecture_audit.py`, `scripts/qa_guard.py`

---

*Este manifiesto es la Única Fuente de Verdad del proyecto Aethelgard. Cualquier decisión de diseño o implementación debe alinearse con los principios y arquitectura documentados aquí.*
