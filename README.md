# Aethelgard - Sistema de Trading Algorítmico Agnóstico

Framework de inteligencia financiera multi-estrategia basado en clasificación de régimen de mercado.

## Arquitectura

Aethelgard está diseñado como un sistema modular que permite integrar múltiples plataformas de trading y estrategias de manera independiente.

### Componentes Principales

#### 1. Core Brain (`core_brain/`)
- **`server.py`**: Servidor FastAPI con WebSockets que gestiona múltiples conexiones simultáneas
- **`regime.py`**: Clasificador de régimen de mercado (TREND, RANGE, CRASH, NEUTRAL)

#### 2. Conectores (`connectors/`)
- **`bridge_nt8.cs`**: Bridge para NinjaTrader 8 (C#)
- **`bridge_mt5.py`**: Bridge para MetaTrader 5 (Python)
- **`webhook_tv.py`**: Webhook para recibir alertas de TradingView

#### 3. Data Vault (`data_vault/`)
- **`storage.py`**: Sistema de persistencia SQLite para señales y feedback loop

#### 4. Models (`models/`)
- **`signal.py`**: Modelos de datos para señales y resultados

## Instalación

### Requisitos
- Python 3.8+
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
venv\Scripts\activate
```

3. Instalar dependencias
```bash
pip install -r requirements.txt
```

## Uso

### Iniciar el servidor principal

```bash
python -m core_brain.server
```

El servidor estará disponible en `http://localhost:8000`

### Conectar MetaTrader 5

```bash
python connectors/bridge_mt5.py
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

## Base de Datos

SQLite se inicializa automáticamente en `data_vault/aethelgard.db`

Tablas:
- `signals`: Almacena todas las señales recibidas
- `signal_results`: Almacena resultados y feedback

## Desarrollo

El código está diseñado para ser modular y extensible. Cada componente puede funcionar de manera independiente.

## Licencia

[Especificar licencia]
