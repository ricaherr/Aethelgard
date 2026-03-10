import logging
import time
import asyncio
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, Union
from datetime import datetime, timezone
from dataclasses import dataclass
from pydantic import BaseModel, Field

from models.signal import Signal, SignalType
from data_vault.storage import StorageManager
from core_brain.execution_feedback import ExecutionFailureReason
from connectors.base_connector import BaseConnector
from utils.market_ops import normalize_price, calculate_pip_size

logger = logging.getLogger(__name__)


@dataclass
class LiquidityValidationResult:
    """
    Encapsulates liquidity validation result from _get_current_price().
    
    Implements DOMINIO-05 market quality assurance. Rich failure information
    enables cause-specific signal suppression in SignalFactory (DOMINIO-10).
    
    Attributes:
        is_valid: Market has sufficient liquidity (bid > 0, ask > 0, spread > 0)
        price: Mid price (ask for BUY, bid for SELL) or None if invalid
        bid: Bid price from tick
        ask: Ask price from tick
        spread: Absolute spread (ask - bid) in price units
        spread_pips: Spread in pips (for multi-asset normalization)
        failure_reason: Why validation failed (LIQUIDITY_INSUFFICIENT, PRICE_FETCH_ERROR, etc.)
        failure_details: Additional context ({symbol, bid, ask, spread, reason})
    """
    is_valid: bool
    price: Optional[Decimal] = None
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    spread: Optional[Decimal] = None
    spread_pips: Optional[Decimal] = None
    failure_reason: Optional[ExecutionFailureReason] = None
    failure_details: Dict[str, Any] = None
    
    def __post_init__(self) -> None:
        if self.failure_details is None:
            self.failure_details = {}


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
        connector: BaseConnector
    ) -> ExecutionResponse:
        """
        Ejecuta una señal con protección de slippage y Shadow Reporting.
        Orquesta 3 fases: validación pre-ejecución, envío de orden, manejo de resultados.
        """
        start_time = time.perf_counter()
        trace_id = signal.trace_id or f"EXEC-{uuid.uuid4().hex[:8].upper()}"
        tenant_id = getattr(self.storage, 'tenant_id', 'default')
        signal_id = signal.metadata.get('signal_id', 'unknown')
        theoretical_price = Decimal(str(signal.entry_price))
        
        # Phase 1: Pre-execution validation (liquidity + slippage veto)
        validation_response = await self._validate_pre_execution(
            signal, connector, start_time, trace_id, tenant_id, signal_id
        )
        if validation_response is not None:
            return validation_response  # Validation failed -> return early
        
        # Phase 2: Send order to broker
        execution_response = await self._send_execution_order(
            signal, connector, start_time, trace_id, tenant_id, signal_id
        )
        return execution_response

    async def _validate_pre_execution(
        self,
        signal: Signal,
        connector: BaseConnector,
        start_time: float,
        trace_id: str,
        tenant_id: str,
        signal_id: str
    ) -> Optional[ExecutionResponse]:
        """
        Phase 1: Validates liquidity and pre-execution slippage.
        Returns ExecutionResponse with failure if validation fails, None if validation passes.
        """
        theoretical_price = Decimal(str(signal.entry_price))
        
        # Liquidity validation
        liquidity_result = await self._validate_liquidity(signal.symbol, signal.signal_type, connector)
        
        if not liquidity_result.is_valid:
            error_msg = f"Liquidity validation failed for {signal.symbol}"
            real_price = liquidity_result.price or Decimal("0")
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, real_price,
                Decimal("0"), start_time, "LIQUIDITY_FAILURE", tenant_id, trace_id,
                metadata=liquidity_result.failure_details
            )
            return ExecutionResponse(
                success=False,
                error_message=error_msg,
                status=liquidity_result.failure_reason.value,
                failure_reason=liquidity_result.failure_reason,
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    **liquidity_result.failure_details
                }
            )
        
        # Extract validated prices
        current_tick_price = liquidity_result.price
        bid_price = liquidity_result.bid
        ask_price = liquidity_result.ask
        spread = liquidity_result.spread
        spread_pips = liquidity_result.spread_pips

        # Check slippage against limit
        pre_exec_slippage = self._calculate_pips(signal.symbol, theoretical_price, current_tick_price, signal.signal_type, connector)
        slippage_limit = Decimal(str(signal.metadata.get("slippage_limit", self.default_slippage_limit)))
        
        if abs(pre_exec_slippage) > slippage_limit:
            reason_msg = f"Veto Pre-Ejecución: Slippage estimado {pre_exec_slippage:.2f} pips > limite {slippage_limit} pips"
            logger.warning(f"[{trace_id}] {reason_msg}")
            
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "VETO_SLIPPAGE", tenant_id, trace_id,
                metadata={
                    "veto_limit": float(slippage_limit),
                    "bid": float(bid_price),
                    "ask": float(ask_price),
                    "spread": float(spread),
                    "spread_pips": float(spread_pips)
                }
            )
            
            return ExecutionResponse(
                success=False,
                error_message=reason_msg,
                status="VETO_SLIPPAGE",
                failure_reason=ExecutionFailureReason.VETO_SLIPPAGE,
                failure_context={
                    "trace_id": trace_id,
                    "symbol": signal.symbol,
                    "theoretical_price": float(theoretical_price),
                    "current_price": float(current_tick_price),
                    "bid": float(bid_price),
                    "ask": float(ask_price),
                    "spread": float(spread),
                    "spread_pips": float(spread_pips),
                    "slippage_pips": float(pre_exec_slippage),
                    "limit_pips": float(slippage_limit),
                    "signal_type": str(signal.signal_type)
                }
            )
        
        # Store validated data in signal metadata for Phase 2
        signal.metadata['_validated_price'] = float(current_tick_price)
        signal.metadata['_pre_exec_slippage'] = float(pre_exec_slippage)
        return None  # Validation passed

    async def _send_execution_order(
        self,
        signal: Signal,
        connector: BaseConnector,
        start_time: float, 
        trace_id: str,
        tenant_id: str,
        signal_id: str
    ) -> ExecutionResponse:
        """
        Phase 2: Sends order to broker and handles result/errors.
        Returns ExecutionResponse with success or failure details.
        """
        theoretical_price = Decimal(str(signal.entry_price))
        current_tick_price = Decimal(str(signal.metadata.get('_validated_price', signal.entry_price)))
        pre_exec_slippage = Decimal(str(signal.metadata.get('_pre_exec_slippage', 0)))
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, connector.execute_order, signal)
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if result.get('success'):
                real_price = Decimal(str(result.get('price', current_tick_price)))
                final_slippage = self._calculate_pips(signal.symbol, theoretical_price, real_price, signal.signal_type, connector)
                
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

    async def _validate_liquidity(
        self,
        symbol: str,
        signal_type: SignalType,
        connector: BaseConnector
    ) -> LiquidityValidationResult:
        """
        Comprehensive liquidity validation with detailed failure diagnosis.
        
        Validates:
        1. Connector returns tick data (not None)
        2. Both bid and ask are present and > 0
        3. Spread is positive (ask > bid)
        4. Spread is reasonable (<50 pips for FX)
        
        Returns:
            LiquidityValidationResult with:
            - is_valid: True if market has sufficient liquidity
            - price: Mid price (ask for BUY, bid for SELL) or None if invalid
            - bid/ask/spread/spread_pips: Market structure details
            - failure_reason + failure_details: Specific cause and context (if invalid)
        """
        try:
            # Step 1: Get tick from connector
            tick = connector.get_last_tick(symbol)
            
            if tick is None:
                return LiquidityValidationResult(
                    is_valid=False,
                    failure_reason=ExecutionFailureReason.PRICE_FETCH_ERROR,
                    failure_details={
                        "symbol": symbol,
                        "reason": "connector.get_last_tick() returned None",
                        "cause": "Connector temporarily unavailable or symbol not in Market Watch"
                    }
                )
            
            # Step 2: Extract bid/ask
            bid_raw = tick.get('bid')
            ask_raw = tick.get('ask')
            
            # Step 3: Validate both exist and are > 0 (not just not None)
            if bid_raw is None or ask_raw is None:
                missing = "bid" if bid_raw is None else "ask"
                return LiquidityValidationResult(
                    is_valid=False,
                    bid=Decimal(str(bid_raw)) if bid_raw is not None else None,
                    ask=Decimal(str(ask_raw)) if ask_raw is not None else None,
                    failure_reason=ExecutionFailureReason.LIQUIDITY_INSUFFICIENT,
                    failure_details={
                        "symbol": symbol,
                        "reason": f"Market missing {missing} - Insufficient liquidity",
                        "bid": float(bid_raw) if bid_raw is not None else None,
                        "ask": float(ask_raw) if ask_raw is not None else None,
                        "cause": "One-sided market (only bid OR ask available)"
                    }
                )
            
            # Convert to Decimal
            bid = Decimal(str(bid_raw))
            ask = Decimal(str(ask_raw))
            
            # Step 4: Validate bid and ask are positive
            if bid <= 0 or ask <= 0:
                return LiquidityValidationResult(
                    is_valid=False,
                    bid=bid,
                    ask=ask,
                    failure_reason=ExecutionFailureReason.LIQUIDITY_INSUFFICIENT,
                    failure_details={
                        "symbol": symbol,
                        "reason": f"Invalid prices: bid={float(bid)}, ask={float(ask)}",
                        "bid": float(bid),
                        "ask": float(ask),
                        "cause": "Zero or negative price - Market halted/closed"
                    }
                )
            
            # Step 5: Validate spread (ask > bid)
            spread = ask - bid
            if spread <= 0:
                return LiquidityValidationResult(
                    is_valid=False,
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    failure_reason=ExecutionFailureReason.VETO_SPREAD,
                    failure_details={
                        "symbol": symbol,
                        "reason": f"Inverted market: ask ({float(ask)}) <= bid ({float(bid)})",
                        "bid": float(bid),
                        "ask": float(ask),
                        "spread": float(spread),
                        "cause": "Market data corruption or halted trading"
                    }
                )
            
            # Step 6: Calculate spread in pips (for symbol with PIP_SIZE)
            pip_size = Decimal(str(calculate_pip_size(symbol_info=None, symbol=symbol)))
            spread_pips = spread / pip_size if pip_size != 0 else Decimal("0")
            
            # Step 7: Warn if spread is unusually wide (>10 pips for FX)
            # NOTE: This is a warning, not a veto - execution can proceed
            # ExecutionResponse can set failure_reason=VETO_SPREAD if threshold exceeded
            
            # Step 8: Extract appropriate price
            if signal_type == SignalType.BUY:
                price = ask  # Buy at ask
            else:
                price = bid  # Sell at bid
            
            # SUCCESS
            return LiquidityValidationResult(
                is_valid=True,
                price=price,
                bid=bid,
                ask=ask,
                spread=spread,
                spread_pips=spread_pips,
                failure_reason=None,
                failure_details={
                    "symbol": symbol,
                    "bid": float(bid),
                    "ask": float(ask),
                    "spread": float(spread),
                    "spread_pips": float(spread_pips),
                    "signal_type": str(signal_type),
                    "price_for_execution": float(price)
                }
            )
            
        except (TypeError, ValueError, AttributeError) as e:
            logger.error(f"Error validating liquidity for {symbol}: {e}", exc_info=True)
            return LiquidityValidationResult(
                is_valid=False,
                failure_reason=ExecutionFailureReason.PRICE_FETCH_ERROR,
                failure_details={
                    "symbol": symbol,
                    "reason": f"Liquidity validation error: {str(e)}",
                    "error_type": type(e).__name__,
                    "cause": "Invalid tick data format from connector"
                }
            )

    def _calculate_pips(self, symbol: str, price_a: Decimal, price_b: Decimal, signal_type: SignalType, connector: BaseConnector) -> Decimal:
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
