"""
Risk Manager Module
Manages position sizing, risk allocation, and lockdown mode.
Delegates validation to RiskPolicyEnforcer and lot calculation to PositionSizeEngine.
"""
import logging
import uuid
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from typing import Any, Dict, Optional

from data_vault.storage import StorageManager
from models.signal import Signal, MarketRegime

from core_brain.position_size_monitor import PositionSizeMonitor
from core_brain.risk_policy_enforcer import RiskPolicyEnforcer
from core_brain.position_size_engine import PositionSizeEngine
from core_brain.instrument_manager import InstrumentManager
from core_brain.services.liquidity_service import LiquidityService
from core_brain.services.confluence_service import ConfluenceService
from core_brain.services.sentiment_service import SentimentService
from core_brain.services.coherence_service import CoherenceService

logger = logging.getLogger(__name__)


class AssetNotNormalizedError(Exception):
    """Raised when an asset is not found in usr_assets_cfg."""
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.message = f"CRITICAL: Asset {symbol} is NOT normalized in usr_assets_cfg. Trade aborted for safety."
        super().__init__(self.message)


def _resolve_storage(storage: Optional[StorageManager]) -> StorageManager:
    if storage is not None:
        return storage
    logger.warning("RiskManager initialized without explicit storage! Falling back to default.")
    return StorageManager()


def _resolve_instrument_manager(
    instrument_manager: Optional[InstrumentManager],
    storage: StorageManager,
) -> InstrumentManager:
    if instrument_manager is not None:
        return instrument_manager
    logger.warning("RiskManager initialized without explicit InstrumentManager!")
    return InstrumentManager(storage=storage)


class RiskManager:
    """
    Orchestrates risk: delegates policy validation to RiskPolicyEnforcer and
    position size calculation to PositionSizeEngine. Owns lockdown state and legacy APIs.
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        initial_capital: float = 10000.0,
        instrument_manager: Optional[InstrumentManager] = None,
        monitor: Optional[PositionSizeMonitor] = None,
        config_path: Optional[str] = None,
        risk_settings_path: Optional[str] = None,
        connectors: Optional[Dict[str, Any]] = None,  # MISIÓN A: Inyección de conectores
    ):
        self.storage = _resolve_storage(storage)
        self.capital = initial_capital
        self.instrument_manager = _resolve_instrument_manager(instrument_manager, self.storage)
        self.monitor = monitor or PositionSizeMonitor()
        self.connectors = connectors or {}  # MISIÓN A: Almacenar conectores para cancelación de órdenes

        self.liquidity_service = LiquidityService(storage=self.storage)
        self.confluence_service = ConfluenceService(storage=self.storage)
        self.sentiment_service = SentimentService(storage=self.storage)
        self.coherence_service = CoherenceService(storage=self.storage)

        risk_settings = self.storage.get_risk_settings()
        dynamic_params = self.storage.get_dynamic_params()
        if not isinstance(risk_settings, dict):
            risk_settings = {}
        if not isinstance(dynamic_params, dict):
            dynamic_params = {}
        if config_path or risk_settings_path:
            logger.warning("Legacy file paths deprecated (SSOT DB-first).")
        if not risk_settings or not dynamic_params:
            logger.debug(
                "[SSOT] Risk/dynamic config not in DB. "
                "Using safe defaults (initialize from UI/API or ensure seed data loaded)."
            )
            risk_settings = risk_settings or {}
            dynamic_params = dynamic_params or {}

        self.risk_per_trade = dynamic_params.get("risk_per_trade", 0.005)
        self.max_consecutive_losses = risk_settings.get(
            "max_consecutive_losses", dynamic_params.get("max_consecutive_losses", 3)
        )
        self.max_account_risk_pct = risk_settings.get("max_account_risk_pct", 5.0)
        self.max_r_per_trade = Decimal(str(risk_settings.get("max_r_per_trade", 2.0)))

        sys_config = self.storage.get_sys_config()
        self.lockdown_mode = sys_config.get("lockdown_mode", False)
        lockdown_date = sys_config.get("lockdown_date")
        lockdown_balance = sys_config.get("lockdown_balance")

        if self.lockdown_mode:
            should_reset, reason = self._should_reset_lockdown(
                lockdown_date, lockdown_balance, initial_capital
            )
            if should_reset:
                self.lockdown_mode = False
                self.storage.update_sys_config({
                    "lockdown_mode": False,
                    "lockdown_date": None,
                    "lockdown_balance": None,
                    "consecutive_losses": 0,
                })
                logger.info("Lockdown deactivated: %s", reason)
        self.consecutive_losses = 0

        self._enforcer = RiskPolicyEnforcer(
            storage=self.storage,
            liquidity_service=self.liquidity_service,
            confluence_service=self.confluence_service,
            sentiment_service=self.sentiment_service,
            coherence_service=self.coherence_service,
            max_r_per_trade=self.max_r_per_trade,
            risk_per_trade=self.risk_per_trade,
            max_account_risk_pct=self.max_account_risk_pct,
            instrument_manager=self.instrument_manager,
        )
        self._engine = PositionSizeEngine(
            storage=self.storage,
            instrument_manager=self.instrument_manager,
            monitor=self.monitor,
            risk_per_trade=self.risk_per_trade,
        )
        logger.info(
            "RiskManager initialized: Capital=$%.2f, Risk=%.2f%%, Lockdown=%s",
            initial_capital, self.risk_per_trade * 100, self.lockdown_mode,
        )

    def can_take_new_trade(self, signal: Signal, connector: Any) -> tuple[bool, str]:
        """Validates if a new trade can be taken. Delegates to RiskPolicyEnforcer with Trace_ID."""
        try:
            trace_id = getattr(signal, "trace_id", None) or f"RPV-{uuid.uuid4().hex[:8].upper()}"
            return self._enforcer.validate(signal, connector, trace_id=trace_id)
        except Exception as e:
            logger.error("Error validating account risk: %s", e)
            return False, f"Risk validation error: {str(e)}"

    def calculate_position_size_master(
        self,
        signal: Signal,
        connector: Any,
        regime_classifier: Optional[Any] = None,
    ) -> float:
        """Single source of truth for position size. Delegates to PositionSizeEngine."""
        return self._engine.calculate_master(
            signal,
            connector,
            regime_classifier=regime_classifier,
            lockdown_active=self.lockdown_mode,
            balance_fallback=self.capital,
        )

    def calculate_position_size(
        self,
        symbol: str,
        risk_amount_usd: float,
        stop_loss_dist: float,
    ) -> float:
        """Legacy: Universal Trading Foundation lot calculation (Decimal, ROUND_DOWN)."""
        trace_id = f"NORM-{uuid.uuid4().hex[:8]}"
        logger.info("[%s] Starting Universal Risk Calculation for %s", trace_id, symbol)
        profile = self.storage.get_asset_profile(symbol, trace_id=trace_id)
        if not profile:
            logger.critical("[%s] %s not in usr_assets_cfg!", trace_id, symbol)
            raise AssetNotNormalizedError(symbol)
        try:
            d_risk = Decimal(str(risk_amount_usd))
            d_sl = Decimal(str(stop_loss_dist))
            d_cs = Decimal(str(profile["contract_size"]))
            d_step = Decimal(str(profile["lot_step"]))
            if d_sl <= 0:
                return 0.0
            risk_per_lot = d_sl * d_cs
            raw_lots = d_risk / risk_per_lot
            final_lots = (raw_lots / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step
            result = float(final_lots)
            logger.info("[%s] Result %s: %.4f lots", trace_id, symbol, result)
            return result
        except Exception as e:
            logger.error("[%s] Error for %s: %s", trace_id, symbol, e, exc_info=True)
            return 0.0

    def calculate_position_size_deprecated(
        self,
        account_balance: float,
        stop_loss_distance: float,
        point_value: float,
        current_regime: Optional[MarketRegime] = None,
    ) -> float:
        """Deprecated. Use calculate_position_size_master()."""
        if self.lockdown_mode or not current_regime:
            return 0.0
        if stop_loss_distance <= 0 or point_value <= 0:
            return 0.0
        vol_mult = 0.5 if current_regime in {MarketRegime.RANGE, MarketRegime.CRASH} else 1.0
        risk_adj = self.risk_per_trade * vol_mult
        risk_usd = account_balance * risk_adj
        var_per_lot = stop_loss_distance * point_value
        if var_per_lot <= 0:
            return 0.0
        return round(risk_usd / var_per_lot, 2)

    def record_trade_result(self, is_win: bool, pnl: float) -> None:
        self.capital += pnl
        if is_win:
            self.consecutive_losses = 0
            if self.lockdown_mode:
                self._deactivate_lockdown()
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self._activate_lockdown()

    def _activate_lockdown(self) -> None:
        if not self.lockdown_mode:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            self.lockdown_mode = True
            self.storage.update_sys_config({
                "lockdown_mode": True,
                "lockdown_date": now,
                "lockdown_balance": self.capital,
                "consecutive_losses": self.consecutive_losses,
            })
            logger.error("LOCKDOWN ACTIVATED: %s consecutive losses at %s", self.consecutive_losses, now)

    def _deactivate_lockdown(self) -> None:
        if self.lockdown_mode:
            self.lockdown_mode = False
            self.consecutive_losses = 0
            self.storage.update_sys_config({
                "lockdown_mode": False,
                "lockdown_date": None,
                "lockdown_balance": None,
                "consecutive_losses": 0,
            })
            logger.info("Lockdown DEACTIVATED.")

    def _should_reset_lockdown(
        self,
        lockdown_date: Optional[str],
        lockdown_balance: Optional[float],
        current_balance: float,
    ) -> tuple[bool, str]:
        from datetime import datetime, timezone
        from utils.time_utils import to_utc_datetime
        if not lockdown_date:
            return True, "No lockdown date (stale)"
        try:
            if isinstance(lockdown_date, datetime):
                lockdown_time = lockdown_date.astimezone(timezone.utc) if lockdown_date.tzinfo else lockdown_date.replace(tzinfo=timezone.utc)
            else:
                lockdown_time = to_utc_datetime(lockdown_date)
        except (ValueError, TypeError):
            return True, "Invalid lockdown date"
        if lockdown_balance and current_balance >= lockdown_balance * 1.02:
            return True, f"Balance recovered from lockdown level"
        try:
            conn = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(close_time) FROM usr_trades WHERE close_time > ?", (lockdown_time.isoformat(),))
            row = cursor.fetchone()
            last_trade = row[0] if row and row[0] else None
            conn.close()
            if last_trade:
                from utils.time_utils import to_utc_datetime
                last_dt = to_utc_datetime(last_trade)
                hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                if hours >= 24:
                    return True, f"System rested {hours:.1f}h"
            else:
                hours = (datetime.now(timezone.utc) - lockdown_time).total_seconds() / 3600
                if hours >= 24:
                    return True, f"System rested {hours:.1f}h since lockdown"
        except Exception as e:
            logger.error("Error checking lockdown reset: %s", e)
        return False, "Lockdown active - waiting recovery or 24h rest"

    def is_locked(self) -> bool:
        return self.lockdown_mode

    def is_lockdown_active(self) -> bool:
        return self.lockdown_mode

    # ────────────────────────────────────────────────────────────────────────────
    # DEFENSIVE PROTOCOL METHODS (HU 4.6: Anomaly Sentinel)
    # ────────────────────────────────────────────────────────────────────────────

    async def activate_lockdown(
        self,
        symbol: Optional[str] = None,
        reason: str = "Anomaly detected",
        trace_id: Optional[str] = None,
    ) -> bool:
        """
        Activa el Lockdown Mode preventivo cuando se detecta una anomalía sistémica.
        
        Args:
            symbol: Símbolo afectado (opcional)
            reason: Razón de la activación (para logging)
            trace_id: ID de trazabilidad
            
        Returns:
            True si el lockdown se activó exitosamente
        """
        try:
            self.lockdown_mode = True
            self.storage.update_sys_config({
                "lockdown_mode": True,
                "lockdown_date": datetime.now().isoformat(),
                "lockdown_reason": reason,
                "lockdown_symbol": symbol or "MULTI",
                "lockdown_trace_id": trace_id or "N/A",
                "consecutive_losses": self.consecutive_losses,
            })
            logger.critical(
                f"[RISK_MANAGER] LOCKDOWN ACTIVATED. Symbol: {symbol}, "
                f"Reason: {reason}. Trace_ID: {trace_id}"
            )
            return True
        except Exception as e:
            logger.error(f"[RISK_MANAGER] Error activating lockdown: {e}")
            return False

    async def cancel_pending_usr_orders(
        self,
        symbol: Optional[str] = None,
        reason: str = "Lockdown Mode Activated",
    ) -> Dict[str, int]:
        """
        Cancela todas las órdenes pendientes para un símbolo o globalmente.
        MISIÓN A: Integración real con conectores para cancelación de órdenes en sys_brokers.
        
        Args:
            symbol: Símbolo a afectar (None = todas las órdenes)
            reason: Razón de la cancelación
            
        Returns:
            Dict con número de órdenes canceladas: {'cancelled': int, 'failed': int, 'status': str}
        """
        try:
            cancelled_count = 0
            failed_count = 0
            
            logger.warning(
                f"[ANOMALY_SENTINEL] Initiating order cancellation for {symbol or 'ALL'}. "
                f"Reason: {reason}"
            )
            
            # No hay conectores inyectados - modo degradado (sin conexión directa a broker)
            if not self.connectors:
                logger.warning(
                    f"[ANOMALY_SENTINEL] No connectors injected. Returning pending_integration status."
                )
                return {
                    "cancelled": 0,
                    "failed": 0,
                    "status": "pending_integration",
                    "message": "No connectors available for real order cancellation"
                }
            
            # Iterar sobre conectores disponibles (MT5, NT8, etc.)
            for connector_type, connector in self.connectors.items():
                if not connector:
                    continue
                
                try:
                    # Verificar si el conector tiene el método get_pending_usr_orders
                    if not hasattr(connector, 'get_pending_usr_orders'):
                        logger.debug(f"Connector {connector_type} does not support get_pending_usr_orders")
                        continue
                    
                    # Obtener órdenes pendientes
                    pending_usr_orders = connector.get_pending_usr_orders(symbol=symbol)
                    
                    if pending_usr_orders is None or not pending_usr_orders:
                        logger.info(f"No pending usr_orders found on {connector_type} for {symbol or 'ALL'}")
                        continue
                    
                    # Cancelar cada orden
                    for order in pending_usr_orders:
                        order_ticket = order.get('ticket')
                        if not order_ticket:
                            failed_count += 1
                            continue
                        
                        try:
                            # Llamar a cancel_order en el conector
                            result = connector.cancel_order(order_ticket, reason=reason)
                            
                            if result.get('success', False):
                                cancelled_count += 1
                                logger.warning(
                                    f"[ANOMALY_SENTINEL] ✅ Order {order_ticket} cancelled via {connector_type}"
                                )
                            else:
                                failed_count += 1
                                logger.warning(
                                    f"[ANOMALY_SENTINEL] Failed to cancel order {order_ticket}: "
                                    f"{result.get('error', 'Unknown error')}"
                                )
                        except Exception as e:
                            failed_count += 1
                            logger.error(f"[ANOMALY_SENTINEL] Error cancelling order {order_ticket}: {e}")
                
                except Exception as e:
                    logger.error(f"[ANOMALY_SENTINEL] Error processing connector {connector_type}: {e}")
            
            status = "success" if failed_count == 0 else "partial"
            logger.warning(
                f"[ANOMALY_SENTINEL] Order cancellation complete. "
                f"Cancelled: {cancelled_count}, Failed: {failed_count}"
            )
            
            return {
                "cancelled": cancelled_count,
                "failed": failed_count,
                "status": status,
                "message": f"Cancelled {cancelled_count} usr_orders, {failed_count} failed"
            }
        
        except Exception as e:
            logger.error(f"[ANOMALY_SENTINEL] Error in cancel_pending_usr_orders: {e}")
            return {
                "cancelled": 0,
                "failed": 0,
                "status": "error",
                "error": str(e)
            }

    async def adjust_stops_to_breakeven(
        self,
        symbol: Optional[str] = None,
        reason: str = "Anomaly Detected - Protective Measure",
    ) -> Dict[str, int]:
        """
        Ajusta todos los Stop Loss a Breakeven para proteger capital en anomalías.
        MISIÓN A: Integración real con conectores para modificación de stops.
        
        Args:
            symbol: Símbolo a afectar (None = todas las posiciones)
            reason: Razón del ajuste
            
        Returns:
            Dict con número de posiciones ajustadas: {'adjusted': int, 'failed': int, 'status': str}
        """
        try:
            adjusted_count = 0
            failed_count = 0
            
            logger.warning(
                f"[ANOMALY_SENTINEL] Initiating SL→Breakeven for {symbol or 'ALL'}. "
                f"Reason: {reason}"
            )
            
            # No hay conectores inyectados - modo degradado
            if not self.connectors:
                logger.warning(
                    f"[ANOMALY_SENTINEL] No connectors injected. Returning pending_integration status."
                )
                return {
                    "adjusted": 0,
                    "failed": 0,
                    "status": "pending_integration",
                    "message": "No connectors available for real stop modification"
                }
            
            # Iterar sobre conectores disponibles (MT5, NT8, etc.)
            for connector_type, connector in self.connectors.items():
                if not connector:
                    continue
                
                try:
                    # Verificar si el conector tiene el método get_open_positions
                    if not hasattr(connector, 'get_open_positions'):
                        logger.debug(f"Connector {connector_type} does not support get_open_positions")
                        continue
                    
                    # Obtener posiciones abiertas
                    usr_positions = connector.get_open_positions()
                    
                    if usr_positions is None or not usr_positions:
                        logger.info(f"No open usr_positions found on {connector_type} for {symbol or 'ALL'}")
                        continue
                    
                    # Filtrar por símbolo si es necesario
                    if symbol:
                        usr_positions = [p for p in usr_positions if p.get('symbol') == symbol]
                    
                    # Ajustar cada posición
                    for position in usr_positions:
                        ticket = position.get('ticket')
                        current_price = position.get('price_current') or position.get('current_price')
                        pos_type = position.get('type')  # 0=BUY, 1=SELL
                        
                        if not ticket or current_price is None:
                            failed_count += 1
                            continue
                        
                        try:
                            # Verificar si el conector tiene modify_order
                            if not hasattr(connector, 'modify_order'):
                                logger.debug(f"Connector {connector_type} does not support modify_order")
                                failed_count += 1
                                continue
                            
                            # Breakeven SL = entry price (proteja la ganancia actual)
                            new_sl = current_price  # Breakeven = precio actual
                            
                            # Llamar a modify_order en el conector
                            result = connector.modify_order(
                                ticket=ticket,
                                sl=new_sl,
                                reason=reason
                            )
                            
                            if result.get('success', False) or isinstance(result, dict) and 'error' not in result:
                                adjusted_count += 1
                                logger.warning(
                                    f"[ANOMALY_SENTINEL] ✅ Position {ticket} SL adjusted to Breakeven ({new_sl}) "
                                    f"via {connector_type}"
                                )
                            else:
                                failed_count += 1
                                logger.warning(
                                    f"[ANOMALY_SENTINEL] Failed to modify position {ticket}: "
                                    f"{result.get('error', 'Unknown error')}"
                                )
                        except Exception as e:
                            failed_count += 1
                            logger.error(f"[ANOMALY_SENTINEL] Error modifying position {ticket}: {e}")
                
                except Exception as e:
                    logger.error(f"[ANOMALY_SENTINEL] Error processing connector {connector_type}: {e}")
            
            status = "success" if failed_count == 0 else "partial"
            logger.warning(
                f"[ANOMALY_SENTINEL] SL→Breakeven complete. "
                f"Adjusted: {adjusted_count}, Failed: {failed_count}"
            )
            
            return {
                "adjusted": adjusted_count,
                "failed": failed_count,
                "status": status,
                "message": f"Adjusted {adjusted_count} usr_positions, {failed_count} failed"
            }
        
        except Exception as e:
            logger.error(f"[ANOMALY_SENTINEL] Error in adjust_stops_to_breakeven: {e}")
            return {
                "adjusted": 0,
                "failed": 0,
                "status": "error",
                "error": str(e)
            }

    def get_status(self) -> Dict:
        return {
            "capital": self.capital,
            "consecutive_losses": self.consecutive_losses,
            "is_locked": self.lockdown_mode,
            "dynamic_risk_per_trade": self.risk_per_trade,
            "max_consecutive_losses": self.max_consecutive_losses,
        }

    def validate_signal(self, signal: Signal) -> bool:
        if self.lockdown_mode:
            signal.status = "VETADO"
            return False
        if self.consecutive_losses >= self.max_consecutive_losses:
            signal.status = "VETADO"
            return False
        return True
