"""
Risk Policy Enforcer – satellite validation for can_take_new_trade.

Runs R-unit, liquidity, confluence, sentiment, and account-risk checks.
Every veto is logged with Trace_ID for full audit trail.
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from data_vault.storage import StorageManager
from models.signal import Signal

from core_brain.services.liquidity_service import LiquidityService
from core_brain.services.confluence_service import ConfluenceService
from core_brain.services.sentiment_service import SentimentService
from utils.market_ops import calculate_pip_size

logger = logging.getLogger(__name__)


def _get_connector_balance(connector: Any) -> float:
    """Get account balance from connector with fallback."""
    try:
        if hasattr(connector, "get_account_balance"):
            return connector.get_account_balance()
        return getattr(connector, "capital", 10000.0)
    except Exception as e:
        logger.error("Error getting account balance: %s", e)
        return 10000.0


def _calculate_r_unit(
    signal: Signal, account_balance: float, storage: StorageManager
) -> Decimal:
    """Calculate R-unit risk using Decimal. R = |Entry - SL| * contract_size / balance * 100."""
    try:
        d_entry = Decimal(str(signal.entry_price))
        d_sl = Decimal(str(signal.stop_loss))
        d_balance = Decimal(str(account_balance))
        if d_balance <= 0:
            return Decimal("0")
        profile = storage.get_asset_profile(signal.symbol) if hasattr(storage, "get_asset_profile") else None
        contract_size = Decimal(str(profile["contract_size"])) if profile else Decimal("100000")
        sl_distance = abs(d_entry - d_sl)
        return (sl_distance * contract_size / d_balance) * Decimal("100")
    except Exception as e:
        logger.error("Error calculating R-unit for %s: %s", signal.symbol, e)
        return Decimal("0")


def _build_rejection_audit(
    signal: Signal,
    r_calculated: Decimal,
    r_limit: Decimal,
    tenant_id: str = "unknown",
) -> Dict[str, Any]:
    """Build RejectionAudit dict for Safety Governor veto."""
    return {
        "trace_id": f"GOV-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": signal.symbol,
        "r_calculated": r_calculated,
        "r_limit": r_limit,
        "reason": "RISK_LIMIT_EXCEEDED",
        "tenant_id": tenant_id,
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
    }


class RiskPolicyEnforcer:
    """
    Runs all policy validations for a new trade (R-unit, liquidity, confluence, sentiment, account risk).
    Call validate() with a trace_id so every veto leaves an audit trail.
    """

    def __init__(
        self,
        storage: StorageManager,
        liquidity_service: LiquidityService,
        confluence_service: ConfluenceService,
        sentiment_service: SentimentService,
        max_r_per_trade: Decimal,
        risk_per_trade: float,
        max_account_risk_pct: float,
        instrument_manager: Optional[Any] = None,
    ):
        self.storage = storage
        self.liquidity_service = liquidity_service
        self.confluence_service = confluence_service
        self.sentiment_service = sentiment_service
        self.max_r_per_trade = max_r_per_trade
        self.risk_per_trade = risk_per_trade
        self.max_account_risk_pct = max_account_risk_pct
        self.instrument_manager = instrument_manager

    def _get_pip_size(self, symbol: str, connector: Any) -> float:
        """Pip size for symbol via connector and optional instrument_manager."""
        symbol_info = None
        if hasattr(connector, "get_symbol_info"):
            symbol_info = connector.get_symbol_info(symbol)
        return calculate_pip_size(symbol_info, symbol, self.instrument_manager)

    def validate(
        self,
        signal: Signal,
        connector: Any,
        trace_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Run full policy validation. Returns (allowed, reason).
        If trace_id is provided, veto logs include [TAG][Trace_ID: trace_id].
        """
        tid = trace_id or getattr(signal, "trace_id", None) or f"RPV-{uuid.uuid4().hex[:8].upper()}"
        account_balance = _get_connector_balance(connector)
        if account_balance <= 0:
            return False, f"Invalid account balance: ${account_balance}"

        current_confidence = float(getattr(signal, "confidence", 0.5))

        # 1. Safety Governor — R-unit veto
        if signal.entry_price and signal.stop_loss and signal.stop_loss > 0:
            r_unit = _calculate_r_unit(signal, account_balance, self.storage)
            if r_unit > self.max_r_per_trade:
                audit = _build_rejection_audit(
                    signal, r_unit, self.max_r_per_trade, getattr(self.storage, "tenant_id", "unknown")
                )
                reason = (
                    f"[SAFETY_GOV] VETO: R={r_unit:.4f}R > limit={self.max_r_per_trade}R. "
                    f"Audit-ID: {audit['trace_id']}"
                )
                logger.warning("[%s][Trace_ID: %s] %s", signal.symbol, tid, reason)
                return False, reason

        # 2. Liquidity / institutional footprint
        try:
            if hasattr(connector, "fetch_ohlc"):
                ohlcv_df = connector.fetch_ohlc(signal.symbol, signal.timeframe or "M5", count=30)
            elif hasattr(connector, "get_market_data"):
                ohlcv_df = connector.get_market_data(signal.symbol, signal.timeframe or "M5", count=30)
            else:
                ohlcv_df = None
            if ohlcv_df is not None and not ohlcv_df.empty:
                records = ohlcv_df.to_dict("records")
                formatted = []
                for row in records:
                    formatted.append({
                        "high": row.get("high", row.get("High", 0)),
                        "low": row.get("low", row.get("Low", 0)),
                        "open": row.get("open", row.get("Open", 0)),
                        "close": row.get("close", row.get("Close", 0)),
                        "volume": row.get("tick_volume", row.get("volume", row.get("Volume", 0))),
                    })
                pip_size = self._get_pip_size(signal.symbol, connector)
                is_high_prob, context_msg = self.liquidity_service.is_in_high_probability_zone(
                    symbol=signal.symbol,
                    price=signal.entry_price,
                    side=signal.signal_type.value,
                    ohlcv_data=formatted,
                    pip_size=pip_size,
                )
                if not is_high_prob:
                    logger.warning("[%s] [CONTEXT_WARNING] %s", signal.symbol, context_msg)
                else:
                    logger.info("[%s] [CONTEXT_OK] %s", signal.symbol, context_msg)
        except Exception as e:
            logger.error("[%s] Error evaluating Liquidity Zones: %s", signal.symbol, e)

        # 3. Confluence (inter-market veto) with trace_id
        try:
            is_confirmed, confluence_msg, penalty = self.confluence_service.validate_confluence(
                symbol=signal.symbol,
                side=signal.signal_type.value,
                connector=connector,
                timeframe=signal.timeframe or "M5",
                trace_id=tid,
            )
            if not is_confirmed:
                minimum_required = 0.85
                if current_confidence < minimum_required:
                    reason = (
                        f"[CONFLUENCE_VETO][Trace_ID: {tid}] {confluence_msg} "
                        f"(Confidence {current_confidence:.2f} < {minimum_required})"
                    )
                    logger.warning("[%s] %s", signal.symbol, reason)
                    return False, reason
                logger.info(
                    "[%s] [CONFLUENCE_WARNING] %s - Proceeding (confidence %.2f)",
                    signal.symbol, confluence_msg, current_confidence,
                )
            else:
                logger.info("[%s] [CONFLUENCE_OK] %s", signal.symbol, confluence_msg)
        except Exception as e:
            logger.error("[%s] Error in Confluence check: %s", signal.symbol, e)

        # 4. Sentiment (macro veto) with trace_id
        try:
            if not isinstance(signal.metadata, dict):
                signal.metadata = {}
            sentiment_events = signal.metadata.get("sentiment_events", []) or []
            if not isinstance(sentiment_events, list):
                sentiment_events = []
            is_allowed, sentiment_msg, snapshot = self.sentiment_service.evaluate_trade_veto(
                symbol=signal.symbol,
                side=signal.signal_type.value,
                confidence=current_confidence,
                events=sentiment_events,
                trace_id=tid,
            )
            signal.metadata["institutional_sentiment"] = snapshot
            if not is_allowed:
                logger.warning("[%s] %s", signal.symbol, sentiment_msg)
                return False, sentiment_msg
            logger.info("[%s] [SENTIMENT_OK] %s", signal.symbol, sentiment_msg)
        except Exception as e:
            logger.error("[%s] Error in Sentiment check: %s", signal.symbol, e)

        # 5. Account risk (open positions + new signal)
        try:
            open_positions = getattr(connector, "get_open_positions", lambda: [])()
        except AttributeError:
            open_positions = []
        current_risk_usd = 0.0
        for pos in open_positions:
            try:
                sym = pos.get("symbol", "")
                vol = pos.get("volume", 0.0)
                entry = pos.get("entry_price", pos.get("price_open", 0.0))
                sl = pos.get("stop_loss", pos.get("sl", 0.0))
                if sl > 0 and hasattr(connector, "get_symbol_info"):
                    info = connector.get_symbol_info(sym)
                    if info:
                        diff = abs(entry - sl)
                        cs = getattr(info, "trade_contract_size", 100000)
                        pt = getattr(info, "point", 0.00001)
                        current_risk_usd += (diff / pt * pt) * cs * vol
            except Exception as e:
                logger.warning("Error calculating risk for position: %s", e)
        signal_risk_usd = account_balance * self.risk_per_trade
        total_risk_usd = current_risk_usd + signal_risk_usd
        total_risk_pct = (total_risk_usd / account_balance) * 100
        if total_risk_pct > self.max_account_risk_pct:
            reason = (
                f"Account risk would exceed {self.max_account_risk_pct}% "
                f"(current: {current_risk_usd / account_balance * 100:.1f}% "
                f"+ signal: {signal_risk_usd / account_balance * 100:.1f}% = {total_risk_pct:.1f}%)"
            )
            logger.warning("[%s] Signal rejected: %s", signal.symbol, reason)
            return False, reason
        logger.info(
            "[%s] Risk check passed: Total risk %.1f%% / %.1f%%",
            signal.symbol, total_risk_pct, self.max_account_risk_pct,
        )
        return True, ""
