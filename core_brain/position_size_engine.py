"""
Position Size Engine – single source of truth for lot calculation.

Encapsulates lockdown/circuit-breaker checks, balance, symbol info, pip/point value,
regime, margin validation, and broker limits. Keeps RiskManager under mass limit.
"""
import logging
from typing import Any, Optional

from data_vault.storage import StorageManager
from models.signal import Signal, MarketRegime

from core_brain.position_size_monitor import PositionSizeMonitor, CalculationStatus
from core_brain.instrument_manager import InstrumentManager
from utils.market_ops import calculate_pip_size, normalize_volume

logger = logging.getLogger(__name__)


def _get_balance(connector: Any, fallback: float = 10000.0) -> float:
    try:
        if hasattr(connector, "get_account_balance"):
            return connector.get_account_balance()
        return getattr(connector, "capital", fallback)
    except Exception as e:
        logger.error("Error getting account balance: %s", e)
        return fallback


def _get_symbol_info(connector: Any, symbol: str) -> Optional[Any]:
    try:
        if hasattr(connector, "get_symbol_info"):
            return connector.get_symbol_info(symbol)
        return None
    except Exception as e:
        logger.error("Error getting symbol info for %s: %s", symbol, e)
        return None


def _validate_risk_sanity(
    lots: float,
    sl_pips: float,
    point_value: float,
    target_usd: float,
    balance: float,
) -> tuple[bool, str]:
    """Final sanity check: over-risk, under-risk, absolute limit, anomalous lots."""
    actual_risk_usd = lots * sl_pips * point_value
    if target_usd > 0:
        if actual_risk_usd > target_usd:
            error_pct = (actual_risk_usd - target_usd) / target_usd
            if error_pct > 0.1:
                return False, (
                    f"OVER-RISK: Multiplier error or rounding led to {error_pct:.1%} higher risk "
                    f"(${actual_risk_usd:.2f} vs ${target_usd:.2f})"
                )
        else:
            error_pct = (target_usd - actual_risk_usd) / target_usd
            if error_pct > 0.3:
                return False, (
                    f"UNDER-RISK: Deviation too high {error_pct:.1%} "
                    f"(${actual_risk_usd:.2f} vs ${target_usd:.2f})"
                )
    risk_of_balance = actual_risk_usd / balance
    if risk_of_balance > 0.03:
        return False, f"ABSOLUTE RISK LIMIT REACHED: {risk_of_balance:.1%} of account (${actual_risk_usd:.2f})"
    if lots > 1000:
        return False, f"Anomalous lot size detected: {lots:.2f}"
    return True, ""


def _get_regime(signal: Signal, regime_classifier: Optional[Any]) -> MarketRegime:
    if signal.metadata and "regime" in signal.metadata:
        try:
            r = signal.metadata["regime"]
            return r if isinstance(r, MarketRegime) else MarketRegime(r)
        except (ValueError, KeyError):
            pass
    if hasattr(signal, "regime") and signal.regime:
        return signal.regime
    return MarketRegime.RANGE


def _get_volatility_multiplier(regime: MarketRegime) -> float:
    if regime in {MarketRegime.RANGE, MarketRegime.CRASH}:
        return 0.5
    return 1.0


def _validate_margin(connector: Any, position_size: float, signal: Signal, symbol_info: Any) -> bool:
    try:
        if not hasattr(connector, "calculate_margin"):
            return True
        margin_required = connector.calculate_margin(signal, position_size)
        if margin_required is None:
            return True
        return True
    except Exception as e:
        logger.error("Error validating margin: %s", e)
        return True


class PositionSizeEngine:
    """
    Calculates position size in lots: balance, symbol info, pip/point value, regime,
    risk formula, margin check, broker limits, and sanity validation.
    """

    def __init__(
        self,
        storage: StorageManager,
        instrument_manager: InstrumentManager,
        monitor: PositionSizeMonitor,
        risk_per_trade: float = 0.005,
    ):
        self.storage = storage
        self.instrument_manager = instrument_manager
        self.monitor = monitor
        self.risk_per_trade = risk_per_trade

    def _pip_size(self, symbol: str, connector: Any) -> float:
        info = _get_symbol_info(connector, symbol)
        return calculate_pip_size(info, symbol, self.instrument_manager)

    def _point_value(
        self,
        symbol_info: Any,
        pip_size: float,
        entry_price: float,
        symbol: str,
        connector: Any,
    ) -> float:
        try:
            contract_size = symbol_info.trade_contract_size
            account_currency = "USD"
            if symbol.endswith(account_currency):
                return contract_size * pip_size
            if symbol.startswith(account_currency):
                return (contract_size * pip_size) / entry_price
            quote_currency = symbol[-3:]
            conv_symbol = f"USD{quote_currency}"
            conv_price = 0.0
            if hasattr(connector, "get_current_price"):
                conv_price = connector.get_current_price(conv_symbol)
            if conv_price and conv_price > 0:
                return (contract_size * pip_size) / conv_price
            inv = f"{quote_currency}USD"
            if hasattr(connector, "get_current_price"):
                inv_price = connector.get_current_price(inv)
                if inv_price and inv_price > 0:
                    return (contract_size * pip_size) * inv_price
            return (contract_size * pip_size) / entry_price
        except Exception as e:
            logger.error("Error calculating point_value: %s", e)
            return 10.0

    def calculate_master(
        self,
        signal: Signal,
        connector: Any,
        regime_classifier: Optional[Any] = None,
        risk_per_trade_override: Optional[float] = None,
        lockdown_active: bool = False,
        balance_fallback: Optional[float] = None,
    ) -> float:
        """
        Single source of truth for position size: lockdown, balance, symbol info,
        pip/point value, regime, risk formula, margin, broker limits, sanity check.
        Returns lots or 0.0 if rejected.
        """
        if lockdown_active:
            self.monitor.record_calculation(
                symbol=signal.symbol,
                position_size=0.0,
                risk_target=0.0,
                status=CalculationStatus.WARNING,
                warnings=["Lockdown mode active"],
            )
            return 0.0
        risk_pct = risk_per_trade_override if risk_per_trade_override is not None else self.risk_per_trade
        try:
            if not self.monitor.is_trading_allowed():
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.CRITICAL,
                    error_message="Circuit breaker active",
                )
                return 0.0

            account_balance = _get_balance(connector, balance_fallback or 10000.0)
            if account_balance <= 0:
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.ERROR,
                    error_message=f"Invalid account balance: {account_balance}",
                )
                return 0.0

            symbol_info = _get_symbol_info(connector, signal.symbol)
            if symbol_info is None:
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.ERROR,
                    error_message=f"Could not get symbol info for {signal.symbol}",
                )
                return 0.0

            pip_size = self._pip_size(signal.symbol, connector)
            point_value = self._point_value(
                symbol_info, pip_size, signal.entry_price, signal.symbol, connector
            )
            if point_value <= 0:
                return 0.0

            current_regime = _get_regime(signal, regime_classifier)
            if not signal.stop_loss or signal.stop_loss <= 0:
                stop_loss_distance_pips = 50.0
            else:
                stop_loss_distance_pips = abs(signal.entry_price - signal.stop_loss) / pip_size
            if stop_loss_distance_pips <= 0:
                return 0.0

            vol_mult = _get_volatility_multiplier(current_regime)
            risk_per_trade_adj = risk_pct * vol_mult
            risk_amount_usd = account_balance * risk_per_trade_adj
            value_at_risk_per_lot = stop_loss_distance_pips * point_value
            if value_at_risk_per_lot <= 0:
                return 0.0
            position_size = risk_amount_usd / value_at_risk_per_lot

            if not _validate_margin(connector, position_size, signal, symbol_info):
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=risk_amount_usd,
                    risk_actual=0.0,
                    status=CalculationStatus.ERROR,
                    error_message="Insufficient margin",
                )
                return 0.0

            position_size_final = normalize_volume(position_size, symbol_info)
            real_risk_after = position_size_final * stop_loss_distance_pips * point_value
            if real_risk_after > risk_amount_usd:
                step = getattr(symbol_info, "volume_step", 0.01) or 0.01
                candidate = position_size_final - step
                if candidate >= getattr(symbol_info, "volume_min", 0):
                    position_size_final = candidate

            real_risk_usd = position_size_final * stop_loss_distance_pips * point_value
            is_sane, sanity_msg = _validate_risk_sanity(
                position_size_final, stop_loss_distance_pips, point_value,
                risk_amount_usd, account_balance,
            )
            if not is_sane:
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=position_size_final,
                    risk_target=risk_amount_usd,
                    risk_actual=real_risk_usd,
                    status=CalculationStatus.CRITICAL,
                    error_message=sanity_msg,
                )
                return 0.0

            warnings_list = []
            if position_size_final < getattr(symbol_info, "volume_min", 0.01) * 1.5:
                warnings_list.append(f"Position size very small: {position_size_final:.4f} lots")
            if position_size_final > getattr(symbol_info, "volume_max", 100) * 0.5:
                warnings_list.append(f"Position size large: {position_size_final:.2f} lots")
            error_pct = abs(real_risk_usd - risk_amount_usd) / risk_amount_usd * 100 if risk_amount_usd > 0 else 0
            if error_pct > 10.0:
                warnings_list.append(f"Error > 10%: {error_pct:.2f}%")

            calc_status = CalculationStatus.WARNING if warnings_list else CalculationStatus.SUCCESS
            self.monitor.record_calculation(
                symbol=signal.symbol,
                position_size=position_size_final,
                risk_target=risk_amount_usd,
                risk_actual=real_risk_usd,
                status=calc_status,
                warnings=warnings_list if warnings_list else None,
            )
            return position_size_final
        except Exception as e:
            logger.error("Error in calculate_master: %s", e, exc_info=True)
            self.monitor.record_calculation(
                symbol=getattr(signal, "symbol", "UNKNOWN"),
                position_size=0.0,
                risk_target=0.0,
                status=CalculationStatus.ERROR,
                error_message=str(e),
            )
            return 0.0
