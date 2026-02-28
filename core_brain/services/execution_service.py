import logging
import time
import asyncio
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from models.signal import Signal, SignalType
from data_vault.storage import StorageManager
from utils.market_ops import normalize_price, calculate_pip_size

logger = logging.getLogger(__name__)

class ExecutionResponse(BaseModel):
    """Modelo Pydantic para el resultado de una ejecución."""
    success: bool
    order_id: Optional[str] = None
    real_price: Optional[Decimal] = None
    slippage_pips: Decimal = Decimal("0")
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    status: str

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
            return self._fail_response("No se pudo obtener el precio actual para validación pre-ejecución", start_time, status="PRICE_FETCH_ERROR")

        theoretical_price = Decimal(str(signal.entry_price))
        pre_exec_slippage = self._calculate_pips(signal.symbol, theoretical_price, current_tick_price, signal.signal_type, connector)
        
        # Límite de slippage desde metadatos o default
        slippage_limit = Decimal(str(signal.metadata.get("slippage_limit", self.default_slippage_limit)))
        
        if abs(pre_exec_slippage) > slippage_limit:
            reason = f"Veto Pre-Ejecución: Slippage estimado {pre_exec_slippage:.2f} pips > limite {slippage_limit} pips"
            logger.warning(f"[{trace_id}] {reason}")
            
            # Shadow Log del Veto (Pre-ejecución)
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "VETO_SLIPPAGE", tenant_id, trace_id,
                metadata={"veto_limit": float(slippage_limit)}
            )
            
            return self._fail_response(reason, start_time, status="VETO_SLIPPAGE")

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
                return self._fail_response(f"Broker rejected: {error_msg}", start_time, status="BROKER_REJECTED")

        except Exception as e:
            logger.error(f"[{trace_id}] Error crítico en ExecutionService: {e}", exc_info=True)
            await self._log_shadow_async(
                signal_id, signal.symbol, theoretical_price, current_tick_price, 
                pre_exec_slippage, start_time, "CRITICAL_ERROR", tenant_id, trace_id,
                metadata={"exception": str(e)}
            )
            return self._fail_response(f"Internal Execution Error: {str(e)}", start_time, status="CRITICAL_ERROR")

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

    def _fail_response(self, message: str, start_time: float, status: str = "FAILED") -> ExecutionResponse:
        """Helper para generar respuestas de fallo estandarizadas."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ExecutionResponse(
            success=False,
            error_message=message,
            latency_ms=latency_ms,
            status=status
        )
