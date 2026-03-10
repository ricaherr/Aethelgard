# Dominio 05: UNIVERSAL_EXECUTION (EMS, Conectores FIX)

## 🎯 Propósito
Garantizar una ejecución de órdenes de alta fidelidad y baja latencia mediante una infraestructura de conectividad agnóstica y un control estricto del slippage.

## 🚀 Componentes Críticos
*   **Execution Service (High-Fidelity)**: Motor de orquestación que implementa protecciones de precio y Shadow Reporting en tiempo real.
*   **Connectivity Orchestrator**: Gestión centralizada de sesiones y estados de conexión con múltiples brokers.
*   **Adaptive Slippage Controller**: Algoritmo que realiza un "Veto Técnico" si la diferencia entre el precio teórico y el precio de mercado actual supera el límite configurado (default: 2.0 pips).
*   **Shadow Reporting System**: Registro persistente en `execution_shadow_logs` que mide la latencia y el slippage real de cada orden para auditoría institucional. **Esta capa protege al usuario detectando manipulaciones de precio por parte del broker o ineficiencias de enrutamiento, permitiendo un veto técnico automático si el slippage real excede los límites históricos de confianza.**
*   **Source Fidelity Guard**: Prohíbe el arbitraje de datos entre proveedores para garantizar la integridad operativa.

## 🔌 Conectores y Proveedores de Datos
Aethelgard utiliza un sistema de **fallback automático** para garantizar la disponibilidad de datos de mercado.

*   **Yahoo Finance**: Principal proveedor gratuito para Forex, Stocks y Commodities.
*   **CCXT**: Puente universal para más de 100 exchanges de Criptomonedas.
*   **Alpha Vantage / Twelve Data / Polygon**: Proveedores con API Key para alta frecuencia y datos institucionales.
*   **MetaTrader 5 (MT5)**: Conexión nativa de alta fidelidad. El `ExecutionService` utiliza directamente las primitivas de MT5 para garantizar latencia mínima.

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

