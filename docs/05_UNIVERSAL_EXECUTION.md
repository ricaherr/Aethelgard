# Dominio 05: UNIVERSAL_EXECUTION (EMS, Conectores FIX)

## 🎯 Propósito
Garantizar una ejecución de órdenes de alta fidelidad y baja latencia mediante una infraestructura de conectividad agnóstica y un control estricto del slippage.

## � SHADOW Mode: Strategy Testing & High-Fidelity Simulation

### Propósito
El modo SHADOW permite a nuevas estrategias ejecutarse con seguridad total usando cuentas DEMO de brokers reales, acumulando métricas auténticas para calibración antes de transicionar a modo LIVE con capital real.

### Arquitectura: MT5 DEMO Routing
```
Strategy en SHADOW
      ↓
CircuitBreakerGate valida 4 Pillars (Market Structure, Risk, Liquidity, Confluence)
      ↓
Executor inyecta account_type='DEMO' en signal.metadata
      ↓
MT5Connector.execute_signal()
      ↓
Detecta account_type='DEMO' → Usa MT5 DEMO account (real broker, paper account)
      ↓
Ejecución con slippage/spread/comisiones reales (sin riesgo financiero)
      ↓
TradeClosureListener registra: execution_mode='SHADOW', account_type='DEMO'
      ↓
StrategyRanker evalúa PF, WR, Trade Count después de 50+ trades
```

### Flujo Completo: SHADOW → LIVE Promotion
```
1. Nueva estrategia → execution_mode='SHADOW'
2. Señales validadas → CircuitBreaker (4 Pillars) → Si PASAN, continúa
3. Executor inyecta account_type='DEMO' en metadata
4. MT5 ejecuta en DEMO account (real price action, cero riesgo)
5. 50+ trades acumuladas → Métricas auténticas (PF, WR, DD)
6. StrategyRanker verifica criterios:
   - ✅ PF > 1.5 (profit factor)
   - ✅ WR > 50% (win rate)
   - ✅ Completed Last 50 >= 50 trades
7. SI TODOS CUMPLEN → execution_mode='LIVE' (promueve a account REAL)
8. SI NO → Permanece en SHADOW hasta cumplir
```

### Ventajas: MT5 DEMO vs Simulación Pura
| Aspecto | MT5 DEMO ✅ | Simulación Pura ❌ |
|---------|-----------|-----------|
| **Slippage Real** | Simulado por broker | Ficticio |
| **Spread Realista** | Real del broker | Estático |
| **Comisiones** | Broker fees reales | N/A |
| **Latencia Red** | Real de red | Simulado |
| **Validación de Órdenes** | Broker válida límites | Siempre ejecuta |
| **Calibración Métricas** | Datos auténticos | Datos de prueba |
| **Confianza del Usuario** | Alta | Baja |

### Provisioning Automático
- **MainOrchestrator** ejecuta `ensure_optimal_demo_accounts()` al inicio
- Auto-crea cuentas DEMO en brokers con soporte automático (MT5, Binance, Tradovate)
- Almacena en `sys_broker_accounts` con `account_type='demo'`
- Disponibles automáticamente para estrategias SHADOW

### Auditoría & Feedback
- **Tabla `trades`**: Registra `execution_mode` (LIVE/SHADOW) + `account_type` (REAL/DEMO)
- **ExecutionFeedbackCollector**: Rastrea patrones de fallo específicos por modo
- **StrategyRanker**: Consulta trades SHADOW explícitamente para evaluación de promoción
- **Trazabilidad**: Cada trade incluye `execution_mode` para auditoría regulatoria

## 📊 Shadow Reporting System
Extension del Sistema de Reporte para SHADOW mode:
```python
# Reporte automático de SHADOW trades
- execution_mode='SHADOW'
- account_type='DEMO'
- Slippage, Spread, Commission (reales)
- Latency metrics
- Broker validation results
```
*   **Adaptive Slippage Controller**: Algoritmo que realiza un "Veto Técnico" si la diferencia entre el precio teórico y el precio de mercado actual supera el límite configurado (default: 2.0 pips).
*   **Shadow Reporting System**: Registro persistente en `execution_shadow_logs` que mide la latencia y el slippage real de cada orden para auditoría institucional. **Esta capa protege al usuario detectando manipulaciones de precio por parte del broker o ineficiencias de enrutamiento, permitiendo un veto técnico automático si el slippage real excede los límites históricos de confianza.**
*   **Source Fidelity Guard**: Prohíbe el arbitraje de datos entre proveedores para garantizar la integridad operativa.

## 🔌 Conectores y Proveedores de Datos
Aethelgard utiliza un sistema de **fallback automático** para garantizar la disponibilidad de datos de mercado. La prioridad es FOREX-first con cTrader como conector primario.

### cTrader Open API (Prioridad: 100 — PRIMARIO FOREX)
Conector WebSocket nativo asyncio sin dependencia de DLL. Habilitado vía `sys_data_providers` (SSOT).

**Credenciales** (`sys_data_providers.additional_config` para `name="ctrader"`):

| Campo | Descripción |
|---|---|
| `access_token` | OAuth2 Bearer Token (Spotware Developer Portal) |
| `account_number` | Número de cuenta visible en el broker (ej. 9920997) |
| `ctid_trader_account_id` | ID interno Spotware (ej. 46662210) — distinto al account_number |
| `client_id` | Application client ID del portal openapi.ctrader.com |
| `client_secret` | Application client secret |
| `account_type` | `"DEMO"` o `"LIVE"` |

**Protocolo WebSocket — Flujo de autenticación y datos OHLC:**
```
websockets → wss://demo.ctraderapi.com:5035/
  │
  ├─ PROTO_OA_APPLICATION_AUTH_REQ  (clientId + clientSecret)
  │    └─ PROTO_OA_APPLICATION_AUTH_RES ✓
  │
  ├─ PROTO_OA_ACCOUNT_AUTH_REQ  (accessToken + ctidTraderAccountId)
  │    └─ PROTO_OA_ACCOUNT_AUTH_RES ✓
  │
  ├─ PROTO_OA_SYMBOLS_LIST_REQ  (cache en memoria: "EURUSD" → symbolId)
  │    └─ PROTO_OA_SYMBOLS_LIST_RES ✓
  │
  └─ PROTO_OA_GET_TRENDBARS_REQ  (symbolId + period + count)
       └─ PROTO_OA_GET_TRENDBARS_RES → pd.DataFrame(time,open,high,low,close,volume)
```

**Decodificación de precios (formato Spotware):**
Los precios en `ProtoOATrendbar` están codificados en puntos (×100000). Cada barra usa delta-encoding respecto al mínimo:
```python
price_divisor = 10 ** digits  # digits=5 para FOREX
low   = trendbar.low / price_divisor
open  = (trendbar.low + trendbar.deltaOpen) / price_divisor
close = (trendbar.low + trendbar.deltaClose) / price_divisor
high  = (trendbar.low + trendbar.deltaHigh) / price_divisor
```

**REST de ejecución** (`api.spotware.com`):
```
Base URL: https://api.spotware.com
Auth:     ?oauth_token={access_token}  (query param, NO header Bearer)
Account:  ctidTraderAccountId (NO accountNumber)

POST /connect/tradingaccounts/{ctid}/orders     → execute_order
GET  /connect/tradingaccounts/{ctid}/positions  → get_positions
GET  /connect/tradingaccounts             → lista cuentas + ctid lookup
```

**Dependencias**: `websockets` (ya instalado) + `ctrader-open-api` + `protobuf`
**Implementación**: `connectors/ctrader_connector.py` | **Tests**: `tests/test_ctrader_connector.py`
**Trace_ID**: `CTRADER-WS-PROTO-2026-03-21`

---

*   **MetaTrader 5 (MT5)**: Conexión nativa de alta fidelidad (prioridad 70). Alternativa FOREX cuando cTrader no está disponible. Requiere instalación local del terminal MT5.
*   **Yahoo Finance**: Fallback gratuito para Stocks y Commodities. Prioridad 50.
*   **CCXT**: Puente universal para más de 100 exchanges de Criptomonedas.
*   **Alpha Vantage / Twelve Data / Polygon**: Proveedores con API Key para alta frecuencia y datos institucionales.

## � Failure Reason Reporting (HIGH-FIDELITY FEEDBACK)
Implementación de DOMINIO-10 (INFRA_RESILIENCY) que proporciona razones estructuradas para fallos de ejecución.

### ExecutionFailureReason Enum
Detección de fallo específica con programmatic handling en MainOrchestrator y SignalFactory:

```python
class ExecutionFailureReason(str, Enum):
    PRICE_FETCH_ERROR = "PRICE_FETCH_ERROR"          # _get_current_price devolvió None
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"  # Sin bid/ask disponible
    VETO_SLIPPAGE = "VETO_SLIPPAGE"                 # Slippage excedió límite (>2.0 pips default)
    VETO_SPREAD = "VETO_SPREAD"                     # Spread excedió límite
    VETO_VOLATILITY = "VETO_VOLATILITY"             # Volatility demasiado alto (Z-Score > 3.0)
    CONNECTION_ERROR = "CONNECTION_ERROR"           # Fallo de conexión con broker
    ORDER_REJECTED = "ORDER_REJECTED"               # Broker rechazó orden (validación)
    TIMEOUT = "TIMEOUT"                             # Timeout en ejecución
    UNKNOWN = "UNKNOWN"                             # Causa desconocida (fallback)
```

### ExecutionResponse Extension
Respuesta de ejecución enriquecida con contexto de fallo:

```python
class ExecutionResponse(BaseModel):
    success: bool                                    # Éxito o fallo
    order_id: Optional[str] = None                  # ID del broker
    real_price: Optional[Decimal] = None            # Precio real de ejecución
    slippage_pips: Decimal = Decimal("0")           # Slippage en pips
    latency_ms: float = 0.0                         # Latencia en ms
    error_message: Optional[str] = None             # Descripción legible
    status: str                                     # Código de estado
    failure_reason: Optional[ExecutionFailureReason] = None  # ← NUEVO
    failure_context: Dict[str, Any] = Field(default_factory=dict)  # ← NUEVO
```

### Flujo de Feedback Inteligente
1. **ExecutionService** retorna `ExecutionFailureReason` específico en cada fallo
2. **Executor** guarda la última `ExecutionResponse` en `self.last_execution_response`
3. **MainOrchestrator** extrae `failure_reason` de la respuesta guardada
4. **ExecutionFeedbackCollector** registra fallo con razón específica (NO blind UNKNOWN)
5. **SignalFactory** suprime signals basado en patrones de fallo específicos

**Ejemplo**: Si múltiples fallos de VETO_SLIPPAGE ocurren en BTC/USD, la siguiente señal de BTC/USD es suprimida automáticamente hasta que las condiciones de mercado mejoren.
## 🔍 LiquidityValidationResult (BUG #2 FIX - Comprehensive Market Liquidity Validation)

### Problema Identificado
`_get_current_price()` retornaba `None` silenciosamente sin validar:
- Market halted (bid=0, ask=0)
- One-sided market (solo bid o solo ask disponible)
- Inverted market (bid > ask)
- Detalles específicos del POR QUÉ falló

### Solución: Dataclass de Validación Estructurada

```python
@dataclass
class LiquidityValidationResult:
    """Validación exhaustiva de liquidez del mercado (DOMINIO-05 + BUG #2 Fix)."""
    is_valid: bool                              # ✅/❌ Mercado tiene liquidez suficiente
    price: Optional[Decimal]                    # Precio mid (ask para BUY, bid para SELL) o None
    bid: Optional[Decimal]                      # Precio de compra actual
    ask: Optional[Decimal]                      # Precio de venta actual
    spread: Optional[Decimal]                   # Spread absoluto (ask - bid) en unidades de precio
    spread_pips: Optional[Decimal]              # Spread normalizado en pips
    failure_reason: Optional[ExecutionFailureReason]  # PRICE_FETCH_ERROR, LIQUIDITY_INSUFFICIENT, VETO_SPREAD
    failure_details: Dict[str, Any]             # {bid, ask, spread, reason, cause} para diagnostico
```

### Validación de 7 Pasos (_validate_liquidity() método)

| Paso | Validación | ❌ Fallo | ✅ Éxito |
|------|-----------|--------|--------|
| 1 | `tick = connector.get_last_tick(symbol)` | `PRICE_FETCH_ERROR` | Continúa |
| 2 | `bid is not None AND ask is not None` | `LIQUIDITY_INSUFFICIENT` | Continúa |
| 3 | `bid > 0 AND ask > 0` | `LIQUIDITY_INSUFFICIENT` | Continúa |
| 4 | `spread = ask - bid > 0` | `VETO_SPREAD` | Continúa |
| 5 | `convert to Decimal` | `PRICE_FETCH_ERROR` | Continue |
| 6 | `spread_pips = spread / pip_size` | Calculate | Continúa |
| 7 | `price = ask (BUY) o bid (SELL)` | N/A | **SUCCESS** → Retorna `is_valid=True` |

**Resultado de Éxito**: `LiquidityValidationResult(is_valid=True, price=1.0925, bid=1.0920, ask=1.0925, spread=0.0005, spread_pips=5.0)`

**Resultado de Fallo** (ejemplo LIQUIDITY_INSUFFICIENT):
```python
LiquidityValidationResult(
    is_valid=False,
    failure_reason=ExecutionFailureReason.LIQUIDITY_INSUFFICIENT,
    failure_details={
        "symbol": "BTC/USDT",
        "bid": None,
        "ask": 45000.5,
        "reason": "Market missing bid - Insufficient liquidity",
        "cause": "One-sided market (only ask available)"
    }
)
```

### Impacto en DOMINIO-10 (ExecutionFeedbackCollector)

**Antes (Ciego)**: "BTC/USD 3x failed" → Suprimir (frequency-based)  
**Después (Inteligente)**: "BTC/USD 3x LIQUIDITY_INSUFFICIENT" → Suprimir BUY cuando liquid empeora

failure_context enriquecido incluye:
- `bid`, `ask`, `spread`, `spread_pips`
- `reason`: "Market one-sided" o "Missing bid/ask"
- `cause`: "Connector unavailable" o "Market halted"
## �📟 Guía Técnica de Instalación (MT5)
1.  **Descarga**: Se recomienda usar la versión directa del broker (Pepperstone, IC Markets, XM).
2.  **Instalación**: Usar rutas por defecto y cerrar la terminal tras la instalación.
3.  **Configuración**: Ejecutar `python scripts/setup_mt5_demo.py` para vincular credenciales a la DB de Aethelgard.
4.  **Verificación**: `python scripts/validate_all.py` para validar latencia, Slippage Control y Shadow Reporting.

## 🖥️ UI/UX REPRESENTATION
*   **Shadow Audit Terminal**: Dashboard que visualiza el slippage promedio por activo y sesión.
*   **Execution Veto History**: Registro visual de órdenes no ejecutadas por exceso de slippage.
*   **Efficiency Badge**: Etiqueta visual en cada trade cerrado que indica el % de ejecución eficiente (Slippage vs Teórico).

## 📈 Roadmap del Dominio
- [x] Implementación de ExecutionService con Veto Adaptativo (HU 5.1).
- [x] Shadow Reporting y Telemetría de Slippage.
- [ ] Despliegue del núcleo QuickFIX para Prime Brokers.
- [ ] Implementación del Feedback Loop de infraestructura (The Pulse).
- [x] Agnosticismo de activos y Normalización SSOT (Unidades R).

