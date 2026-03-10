import logging
import time
import asyncio
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, Union
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

from models.signal import Signal, SignalType
from data_vault.storage import StorageManager
from utils.market_ops import normalize_price, calculate_pip_size

logger = logging.getLogger(__name__)


class ExecutionFailureReason(str, Enum):
    """
    Enumeration of execution failure causes.
    Used by ExecutionService to report specific failure reasons to MainOrchestrator.
    Part of DOMINIO-05 (UNIVERSAL_EXECUTION) and DOMINIO-10 (INFRA_RESILIENCY).
    
    Reference: DEVELOPMENT_GUIDELINES.md Rule 1.3 (Enums not strings)
    """
    PRICE_FETCH_ERROR = "PRICE_FETCH_ERROR"  # _get_current_price returned None
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"  # No bid/ask available
    VETO_SLIPPAGE = "VETO_SLIPPAGE"  # Slippage exceeded limit
    VETO_SPREAD = "VETO_SPREAD"  # Spread exceeded limit
    VETO_VOLATILITY = "VETO_VOLATILITY"  # Volatility too high (Z-Score > 3.0)
    CONNECTION_ERROR = "CONNECTION_ERROR"  # Broker connection failed
    ORDER_REJECTED = "ORDER_REJECTED"  # Broker rejected order (validation error)
    TIMEOUT = "TIMEOUT"  # Execution timeout
    UNKNOWN = "UNKNOWN"  # Unknown cause (fallback)


class ExecutionResponse(BaseModel):
    """
    High-fidelity execution response with rich failure information.
    
    Implements DOMINIO-05 (UNIVERSAL_EXECUTION) with detailed failure reasons
    for downstream feedback loop integration (DOMINIO-10 INFRA_RESILIENCY).
    
    Attributes:
        success: Execution succeeded or failed
        order_id: Order ID from broker (success only)
        real_price: Actual execution price (success only)
        slippage_pips: Actual slippage in pips
        latency_ms: Execution latency in milliseconds
        error_message: Human-readable error description (failure only)
        status: Status code string (SUCCESS, PRICE_FETCH_ERROR, VETO_SLIPPAGE, etc.)
        failure_reason: Structured reason enum for programmatic handling (NEW - Improvement)
        failure_context: Additional context about failure (NEW - Improvement)
    """
    success: bool
    order_id: Optional[str] = None
    real_price: Optional[Decimal] = None
    slippage_pips: Decimal = Decimal("0")
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    status: str
    failure_reason: Optional[ExecutionFailureReason] = None  # ← NEW: Structured reason
    failure_context: Dict[str, Any] = Field(default_factory=dict)  # ← NEW: Failure context

class ExecutionService:
    """
    Servicio de Ejecución de Alta Fidelidad (HU 5.1).
    Responsable de la normalización, control de slippage adaptativo y shadow reporting.
    """

    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage
        # Slippage default: 2.0 pips (Veto si se excede antes de enviar)
        self.default_slippage_limit = Decimal("2.0")
        logger.info("ExecutionService (High-Fidelity) inicializado.")

    async def execute_with_protection(
        self, 
        signal: Signal, 
        connector: Any
    ) -> ExecutionResponse:
        """
        Ejecuta una señal con protección de slippage y Shadow Reporting.
        """
        start_time = time.perf_counter()
        trace_id = signal.trace_id or f"EXEC-{uuid.uuid4().hex[:8].upper()}"
        tenant_id = getattr(self.storage, 'tenant_id', 'default')
        signal_id = signal.metadata.get('signal_id', 'unknown')
        
        # 1. Pre-Execution Slippage Veto
        current_tick_price = await self._get_current_price(signal.symbol, signal.signal_type, connector)
        
        if current_tick_price is None:
            # DOMINIO-05: Report specific failure reason for feedback loop
            return ExecutionResponse(
                success=False,
                error_message="No se pudo obtener el precio actual para validación pre-ejecución",
                status="PRICE_FETCH_ERROR",
                failure_reason=ExecutionFailureReason.PRICE_FETCH_ERROR,  # ← Specific reason
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    "reason": "connector.get_last_tick() returned None",
                    "provider": "MT5/DataProvider"
                }
            )

        theoretical_price = Decimal(str(signal.entry_price))
        pre_exec_slippage = self._calculate_pips(signal.symbol, theoretical_price, current_tick_price, signal.signal_type, connector)
        
        # Límite de slippage desde metadatos o default
        slippage_limit = Decimal(str(signal.metadata.get("slippage_limit", self.default_slippage_limit)))
        
        if abs(pre_exec_slippage) > slippage_limit:
            reason_msg = f"Veto Pre-Ejecución: Slippage estimado {pre_exec_slippage:.2f} pips > limite {slippage_limit} pips"
            logger.warning(f"[{trace_id}] {reason_msg}")
            
            # Shadow Log del Veto (Pre-ejecución)
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "VETO_SLIPPAGE", tenant_id, trace_id,
                metadata={"veto_limit": float(slippage_limit)}
            )
            
            # DOMINIO-05: Report specific failure reason for feedback loop
            return ExecutionResponse(
                success=False,
                error_message=reason_msg,
                status="VETO_SLIPPAGE",
                failure_reason=ExecutionFailureReason.VETO_SLIPPAGE,  # ← Specific reason
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    "theoretical_price": float(theoretical_price),
                    "current_price": float(current_tick_price),
                    "slippage_pips": float(pre_exec_slippage),
                    "limit_pips": float(slippage_limit)
                }
            )

        # 2. Ejecución Real vía Connector
        try:
            # Los conectores de Aethelgard son mayormente síncronos en su librería base (MT5), 
            # pero aquí los manejamos asincrónicamente donde sea posible.
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, connector.execute_order, signal)
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if result.get('success'):
                real_price = Decimal(str(result.get('price', current_tick_price)))
                final_slippage = self._calculate_pips(signal.symbol, theoretical_price, real_price, signal.signal_type, connector)
                
                # 3. Shadow Reporting (Éxito)
                await self._log_shadow_async(
                    signal_id, signal.symbol, theoretical_price, real_price, 
                    final_slippage, start_time, "SUCCESS", tenant_id, trace_id,
                    metadata={"ticket": result.get('ticket')}
                )
                
                return ExecutionResponse(
                    success=True,
                    order_id=str(result.get('ticket') or result.get('order_id')),
                    real_price=real_price,
                    slippage_pips=final_slippage,
                    latency_ms=latency_ms,
                    status="SUCCESS"
                )
            else:
                error_msg = result.get('error', 'Rechazo genérico del broker')
                await self._log_shadow_async(
                    signal_id, signal.symbol, theoretical_price, current_tick_price, 
                    pre_exec_slippage, start_time, "BROKER_REJECTED", tenant_id, trace_id,
                    metadata={"broker_error": error_msg}
                )
                return self._fail_response(
                    f"Broker rejected: {error_msg}",
                    start_time,
                    status="BROKER_REJECTED",
                    failure_reason=ExecutionFailureReason.ORDER_REJECTED,
                    failure_context={
                        "trace_id": trace_id,
                        "symbol": signal.symbol,
                        "broker_error": error_msg,
                        "reason": "Broker order validation failed"
                    }
                )

        except asyncio.TimeoutError as e:
            logger.error(f"[{trace_id}] Timeout en ExecutionService: {e}", exc_info=True)
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "TIMEOUT", tenant_id, trace_id,
                metadata={"exception": str(e), "error_type": "TimeoutError"}
            )
            return self._fail_response(
                f"Execution timeout: {str(e)}",
                start_time,
                status="TIMEOUT",
                failure_reason=ExecutionFailureReason.TIMEOUT,
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    "error_type": "asyncio.TimeoutError",
                    "reason": "Order execution exceeded timeout limit"
                }
            )
        except (ConnectionError, OSError) as e:
            logger.error(f"[{trace_id}] Conexión perdida en ExecutionService: {e}", exc_info=True)
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "CONNECTION_ERROR", tenant_id, trace_id,
                metadata={"exception": str(e), "error_type": type(e).__name__}
            )
            return self._fail_response(
                f"Connection error: {str(e)}",
                start_time,
                status="CONNECTION_ERROR",
                failure_reason=ExecutionFailureReason.CONNECTION_ERROR,
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    "error_type": type(e).__name__,
                    "reason": "Broker connection failed"
                }
            )
        except Exception as e:
            logger.error(f"[{trace_id}] Error crítico en ExecutionService: {e}", exc_info=True)
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "CRITICAL_ERROR", tenant_id, trace_id,
                metadata={"exception": str(e), "error_type": type(e).__name__}
            )
            return self._fail_response(
                f"Internal Execution Error: {str(e)}",
                start_time,
                status="CRITICAL_ERROR",
                failure_reason=ExecutionFailureReason.UNKNOWN,
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    "error_type": type(e).__name__,
                    "reason": "Unexpected error during execution"
                }
            )

    async def _get_current_price(self, symbol: str, signal_type: SignalType, connector: Any) -> Optional[Decimal]:
        """Obtiene el precio bid/ask actual del conector de forma agnóstica."""
        try:
            # Usamos el nuevo método de la interfaz BaseConnector
            tick = connector.get_last_tick(symbol)
            if tick and tick.get('ask') is not None and tick.get('bid') is not None:
                price = tick['ask'] if signal_type == SignalType.BUY else tick['bid']
                return Decimal(str(price))
            
            return None
        except Exception as e:
            logger.error(f"Error obteniendo precio actual para {symbol}: {e}")
            return None

    def _calculate_pips(self, symbol: str, price_a: Decimal, price_b: Decimal, signal_type: SignalType, connector: Any) -> Decimal:
        """Calcula la diferencia en pips entre dos precios."""
        diff = price_b - price_a
        
        # En BUY, si real > teórico es slippage negativo para el trader (positivo en valor absoluto)
        if signal_type == SignalType.SELL:
            diff = -diff
            
        # Obtenemos symbol_info del conector si es posible
        symbol_info = None
        if hasattr(connector, 'get_symbol_info'):
            symbol_info = connector.get_symbol_info(symbol)
            
        pip_size_val = calculate_pip_size(symbol_info=symbol_info, symbol=symbol)
        
        pip_size = Decimal(str(pip_size_val))
        if pip_size == 0:
            return Decimal("0")
            
        return diff / pip_size

    async def _log_shadow_async(
        self, 
        signal_id: str, 
        symbol: str, 
        theoretical: Decimal, 
        real: Decimal, 
        slippage: Decimal, 
        start_time: float, 
        status: str, 
        tenant_id: str, 
        trace_id: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Helper asíncrono para registro de Shadow Log sin bloquear el flujo principal."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.storage.log_execution_shadow,
                signal_id, 
                symbol, 
                theoretical, 
                real, 
                slippage, 
                latency_ms, 
                status, 
                tenant_id, 
                trace_id, 
                metadata
            )
        except Exception as e:
            logger.error(f"Error guardando Shadow Log: {e}")

    def _fail_response(
        self,
        message: str,
        start_time: float,
        status: str = "FAILED",
        failure_reason: Optional[ExecutionFailureReason] = None,
        failure_context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResponse:
        """Helper para generar respuestas de fallo estandarizadas con razón estructurada."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ExecutionResponse(
            success=False,
            error_message=message,
            latency_ms=latency_ms,
            status=status,
            failure_reason=failure_reason or ExecutionFailureReason.UNKNOWN,
            failure_context=failure_context or {}
        )
