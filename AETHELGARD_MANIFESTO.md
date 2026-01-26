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
┌─────────────────────────────────────────────────────────────────┐
│                      CORE BRAIN (Hub)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Server     │  │   Regime     │  │   Storage    │           │
│  │  (FastAPI)   │  │ Classifier   │  │  (SQLite)    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Tuner      │  │   Strategies │  │   Scanner    │           │
│  │ (Auto-Calib) │  │   (Modular)  │  │ (Proactivo)  │           │
│  └──────────────┘  └──────────────┘  └──────┬───────┘           │
└─────────────────────────────────────────────┼───────────────────┘
         │              │              │      │
         │ WebSocket    │ WebSocket    │ HTTP │ DataProvider
         │              │              │      │ (OHLC)
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐ │
    │   NT8   │    │   MT5   │    │   TV    │ │    ┌─────────────┐
    │ Bridge  │    │ Bridge  │    │Webhook  │ └────│ MT5 Data    │
    └─────────┘    └─────────┘    └─────────┘      │ Provider    │
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

### 2. Feedback Loop Obligatorio

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

### Fase 3: Feedback Loop y Aprendizaje por Refuerzo 🔜 **SIGUIENTE**

**Objetivo**: Implementar ciclo completo de feedback y aprendizaje básico.

#### 3.1 Feedback Loop de Resultados

**Tareas:**
- Sistema de seguimiento de trades ejecutados
- Evaluación automática de resultados (5, 10, 20 velas)
- Cálculo de métricas de rendimiento por estrategia
- Análisis de correlación régimen → resultado

#### 3.2 Aprendizaje por Refuerzo Básico

**Tareas:**
- Modelo simple de Q-Learning o Policy Gradient
- Recompensas basadas en PNL y precisión de régimen
- Actualización de políticas de estrategia según resultados
- Validación en datos históricos antes de aplicar en vivo

#### 3.3 Dashboard de Métricas

**Tareas:**
- Visualización de rendimiento por régimen
- Gráficos de evolución de parámetros
- Análisis de win rate por estrategia
- Alertas de drift o degradación

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

### Risk Manager - Gestión de Riesgo Dinámica ✅ IMPLEMENTADO (Enero 2026)

**Estado**: ✅ Implementado y testeado en `core_brain/risk_manager.py`

Módulo de gestión de riesgo que implementa position sizing dinámico, reducción de riesgo en regímenes volátiles y protección mediante lockdown mode.

#### Características Principales

**1. Position Sizing Adaptivo**
- **Base Risk**: 1% del capital por operación en condiciones normales (TREND, NEUTRAL)
- **Reduced Risk**: 0.5% del capital en regímenes de alta incertidumbre (RANGE, CRASH)
- Cálculo automático de tamaño de posición basado en distancia al stop loss

**2. Lockdown Mode**
- Activación automática tras 3 pérdidas consecutivas
- Bloqueo total de nuevas operaciones hasta revisión manual
- Reset automático del contador tras operación ganadora

**3. Tracking de Capital**
- Actualización en tiempo real del capital disponible
- Registro de todas las operaciones (ganadoras/perdedoras)
- Cálculo de pérdidas consecutivas

#### Métodos Principales

```python
RiskManager.calculate_position_size()  # Calcula tamaño de posición
RiskManager.get_current_risk_pct()     # Obtiene % de riesgo por régimen
RiskManager.record_trade_result()      # Registra resultado de operación
RiskManager.can_trade()                # Verifica si trading está permitido
RiskManager.unlock()                   # Desbloqueo manual del lockdown
RiskManager.get_status()               # Estado completo del risk manager
```

#### Reglas de Riesgo

| Régimen | Risk % | Lógica |
|---------|--------|--------|
| **TREND** | 1.0% | Condiciones óptimas, riesgo base |
| **NEUTRAL** | 1.0% | Riesgo base |
| **RANGE** | 0.5% | Alta incertidumbre, riesgo reducido |
| **CRASH** | 0.5% | Volatilidad extrema, riesgo reducido |

**Fórmula Position Sizing**:
```
Risk Amount = Capital × (Risk % / 100)
Position Size = Risk Amount / |Entry Price - Stop Loss|
```

#### Protección Lockdown

**Activación**:
- 3 pérdidas consecutivas → Lockdown activado
- `can_trade()` retorna `False`
- `calculate_position_size()` retorna `0`

**Desactivación**:
- 1 operación ganadora → Reset automático del contador
- `unlock()` manual → Reset completo del estado

#### Tests Implementados (21/21 ✅)

**Test Suite** (`tests/test_risk_manager.py`):
- ✅ Inicialización con parámetros por defecto y personalizados
- ✅ Cálculo de position size en todos los regímenes
- ✅ Reducción de riesgo en RANGE/CRASH (0.5%)
- ✅ Validación de stop loss inválido
- ✅ Activación de lockdown tras 3 pérdidas
- ✅ Reset de contador tras victoria
- ✅ Bloqueo de trading en lockdown mode
- ✅ Desbloqueo manual
- ✅ Actualización de capital tras operaciones
- ✅ Validación de estado y reportes

**Archivos**:
- `core_brain/risk_manager.py`: Implementación completa (180 líneas)
- `tests/test_risk_manager.py`: Suite TDD completa (21 tests)

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
│   └── tuner.py             # Auto-calibración
├── connectors/
│   ├── mt5_data_provider.py # OHLC vía copy_rates_from_pos (sin gráficas)
│   ├── bridge_mt5.py        # Bridge WebSocket MT5 → Aethelgard
│   └── ...
├── data_vault/              # Persistencia SQLite
├── models/                  # Modelos de datos (Signal, MarketRegime, etc.)
├── run_scanner.py           # Entrypoint del escáner proactivo
├── test_scanner_mock.py     # Test del escáner con mock (sin MT5)
├── strategies/              # Estrategias modulares (por crear)
│   ├── trend_following.py
│   ├── range_trading.py
│   └── risk_manager.py
└── dashboard/               # Dashboard web (Fase 4)
```

### Convenciones de Código

- **Python**: PEP 8, asíncrono (asyncio/FastAPI)
- **C#**: Estilo NinjaScript profesional
- **Tipado**: Type Hints y modelos Pydantic obligatorios
- **Documentación**: Comentarios claros en funciones críticas

### Principios de Diseño

1. **Agnosticismo**: Core Brain nunca depende de librerías específicas de plataforma
2. **Modularidad**: Estrategias en archivos independientes
3. **Resiliencia**: Manejo de errores y reconexión automática
4. **Trazabilidad**: Todo se registra en `data_vault` para aprendizaje

---

## 🔄 Actualización del Manifiesto

Este documento debe actualizarse cuando:
- Se complete una fase del roadmap
- Se añada una nueva estrategia
- Se modifique la arquitectura fundamental
- Se cambien las reglas de autonomía

**Mantenedor**: Equipo de desarrollo Aethelgard  
**Revisión**: Mensual o tras cambios significativos

---

*Este manifiesto es la Única Fuente de Verdad del proyecto Aethelgard. Cualquier decisión de diseño o implementación debe alinearse con los principios y arquitectura documentados aquí.*
