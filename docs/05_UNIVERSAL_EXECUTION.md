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

