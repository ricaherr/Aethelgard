"""
Trading Service - Core business logic for signal processing and positions.
Micro-ETI 3.1: Extracted from server.py to centralize trading operations.

This service owns:
- Signal processing pipeline (validate → classify → persist → notify)
- Open position enrichment (MT5 + DB metadata)
- Account balance resolution (MT5 → cache → default)
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from models.signal import Signal, ConnectorType, MarketRegime
from core_brain.notificator import get_notifier
from core_brain.module_manager import get_module_manager, MembershipLevel
from utils.market_ops import classify_asset_type, calculate_r_multiple

logger = logging.getLogger(__name__)


class TradingService:
    """
    Centralized trading business logic.

    Injected dependencies:
        storage: StorageManager instance
        regime_classifier: RegimeClassifier instance
        socket_service: SocketService instance (for broadcasting thoughts)
    """

    def __init__(self, storage, regime_classifier=None, socket_service=None):
        self._storage = storage
        self._regime_classifier = regime_classifier
        self._socket_service = socket_service
        self._mt5_connector_instance = None
        self._last_regime_by_symbol: Dict[str, MarketRegime] = {}

    # ========== MT5 Connector ==========

    def get_mt5_connector(self) -> Optional[Any]:
        """Lazy-load MT5 connector for balance/position queries."""
        if self._mt5_connector_instance is None:
            try:
                from connectors.mt5_connector import MT5Connector
                self._mt5_connector_instance = MT5Connector()
                if not self._mt5_connector_instance.connect():
                    logger.warning("MT5Connector created but connection failed")
                    self._mt5_connector_instance = None
                    return None
            except Exception as e:
                logger.warning(f"Could not load MT5Connector: {e}")
                return None

        # Verify connection is still active
        if self._mt5_connector_instance and not self._mt5_connector_instance.is_connected:
            try:
                self._mt5_connector_instance.connect()
            except Exception as e:
                logger.debug(f"Reconnection attempt failed: {e}")

        return self._mt5_connector_instance

    # ========== Balance Helpers ==========

    def get_account_balance(self) -> float:
        """
        Get real account balance from MT5 or cached value.

        Returns:
            Account balance (USD) from MT5 if connected, otherwise cached or default.
        """
        # Try to get from MT5 directly
        mt5 = self.get_mt5_connector()
        if mt5:
            try:
                balance = mt5.get_account_balance()
                self._storage.update_system_state({
                    "account_balance": balance,
                    "balance_source": "MT5_LIVE",
                    "balance_last_update": datetime.now().isoformat()
                })
                return balance
            except Exception as e:
                logger.debug(f"Could not get MT5 balance: {e}")

        # Fallback to cached balance in DB
        try:
            state = self._storage.get_system_state()
            cached_balance = state.get("account_balance")
            if cached_balance:
                return float(cached_balance)
        except Exception as e:
            logger.debug(f"Could not get cached balance: {e}")

        # Final fallback (initial capital)
        logger.warning("Using default balance 10000.0 - MT5 not connected")
        self._storage.update_system_state({
            "account_balance": 10000.0,
            "balance_source": "DEFAULT",
            "balance_last_update": datetime.now().isoformat()
        })
        return 10000.0

    def get_balance_metadata(self) -> Dict[str, Any]:
        """
        Get balance metadata (source, last update timestamp).

        Returns:
            Dict with source ('MT5_LIVE' | 'CACHED' | 'DEFAULT') and last_update timestamp.
        """
        try:
            state = self._storage.get_system_state()
            return {
                "source": state.get("balance_source", "UNKNOWN"),
                "last_update": state.get("balance_last_update", datetime.now().isoformat()),
                "is_live": state.get("balance_source") == "MT5_LIVE"
            }
        except Exception as e:
            logger.debug(f"Could not get balance metadata: {e}")
            return {
                "source": "UNKNOWN",
                "last_update": datetime.now().isoformat(),
                "is_live": False
            }

    def get_max_account_risk_pct(self) -> float:
        """
        Load max_account_risk_pct from StorageManager (SSOT).

        Returns:
            float: Max account risk percentage (default 5.0%).
        """
        settings = self._storage.get_risk_settings()
        return settings.get('max_account_risk_pct', 5.0)

    # ========== Broadcasting ==========

    async def _broadcast_thought(self, message: str, module: str = "CORE", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
        """Broadcast a thought to all connected UI clients."""
        if not self._socket_service:
            return
        payload = {
            "message": message,
            "module": module,
            "level": level
        }
        if metadata:
            payload["metadata"] = metadata
        await self._socket_service.emit_event("BREIN_THOUGHT", payload)

    # ========== Open Positions ==========

    async def get_open_positions(self) -> Dict[str, Any]:
        """
        Get open positions enriched with risk metadata.

        Combines real-time MT5 positions with DB-stored metadata.
        Uses StorageManager.get_position_metadata() instead of raw SQL.
        Uses classify_asset_type() and calculate_r_multiple() from market_ops.

        Returns:
            Dict with positions list, total_risk_usd, and count.
        """
        positions_list = []
        total_risk = 0.0

        mt5 = self.get_mt5_connector()
        if mt5:
            if mt5.connect():
                # Update cached balance when we connect to MT5
                try:
                    current_balance = mt5.get_account_balance()
                    self._storage.update_system_state({
                        "account_balance": current_balance,
                        "balance_source": "MT5_LIVE",
                        "balance_last_update": datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.debug(f"Could not update cached balance: {e}")

                # Get open positions from MT5
                mt5_positions = mt5.get_open_positions()

                if mt5_positions:
                    for mt5_pos in mt5_positions:
                        ticket = mt5_pos['ticket']

                        # Get metadata from DB via StorageManager (no raw SQL)
                        meta = self._storage.get_position_metadata(ticket)

                        if meta:
                            risk = meta.get('initial_risk_usd', 0.0)
                            regime = meta.get('entry_regime', 'NEUTRAL')
                            entry_time = meta.get('entry_time', mt5_pos.get('time', ''))
                            timeframe = meta.get('timeframe')
                            strategy = meta.get('strategy')
                        else:
                            risk = 0.0
                            regime = "NEUTRAL"
                            entry_time = mt5_pos.get('time', '')
                            timeframe = None
                            strategy = None

                        symbol = mt5_pos['symbol']
                        current_profit = mt5_pos.get('profit', 0.0)

                        position_data = {
                            "ticket": ticket,
                            "symbol": symbol,
                            "entry_price": mt5_pos.get('price_open', 0.0),
                            "sl": mt5_pos.get('sl', 0.0),
                            "tp": mt5_pos.get('tp', 0.0),
                            "volume": mt5_pos.get('volume', 0.0),
                            "profit_usd": current_profit,
                            "initial_risk_usd": risk,
                            "r_multiple": calculate_r_multiple(current_profit, risk),
                            "entry_regime": regime or "NEUTRAL",
                            "entry_time": str(entry_time),
                            "asset_type": classify_asset_type(symbol),
                            "timeframe": timeframe,
                            "strategy": strategy
                        }

                        positions_list.append(position_data)
                        total_risk += risk

        return {
            "positions": positions_list,
            "total_risk_usd": round(total_risk, 2),
            "count": len(positions_list)
        }

    # ========== Signal Processing ==========

    async def process_signal(self, message: dict, client_id: str, connector_type: ConnectorType) -> None:
        """
        Process an incoming trading signal through the full pipeline:
        1. Validate and create Signal model
        2. Classify market regime
        3. Detect regime changes and log full state
        4. Save to database
        5. Send response to client
        6. Check for strategy-specific notifications (Oliver Vélez)
        """
        try:
            # Initial thought
            await self._broadcast_thought(
                f"Analizando nueva señal para {message.get('symbol', 'Unknown')}...",
                module="SCANNER"
            )

            # Ensure connector is in message
            message["connector_type"] = connector_type

            # Create Signal model
            signal = Signal(**message)

            # Get previous regime for this symbol
            previous_regime = self._last_regime_by_symbol.get(signal.symbol)

            # Classify market regime
            regime = self._regime_classifier.classify(signal.price)
            signal.regime = regime
            await self._broadcast_thought(
                f"Régimen detectado: {regime.value} para {signal.symbol}",
                module="REGIME"
            )

            # Detect regime change and log full state
            metrics = None
            if previous_regime is None or regime != previous_regime:
                metrics = self._regime_classifier.get_metrics()

                state_data = {
                    'symbol': signal.symbol,
                    'timestamp': signal.timestamp.isoformat(),
                    'regime': regime.value,
                    'previous_regime': previous_regime.value if previous_regime else None,
                    'price': signal.price,
                    'adx': metrics.get('adx'),
                    'volatility': metrics.get('volatility'),
                    'sma_distance': metrics.get('sma_distance'),
                    'bias': metrics.get('bias'),
                    'atr_pct': metrics.get('atr_pct'),
                    'volatility_shock_detected': metrics.get('volatility_shock_detected', False),
                    'adx_period': self._regime_classifier.adx_period,
                    'sma_period': self._regime_classifier.sma_period,
                    'adx_trend_threshold': self._regime_classifier.adx_trend_threshold,
                    'adx_range_threshold': self._regime_classifier.adx_range_threshold,
                    'adx_range_exit_threshold': self._regime_classifier.adx_range_exit_threshold,
                    'volatility_shock_multiplier': self._regime_classifier.volatility_shock_multiplier,
                    'shock_lookback': self._regime_classifier.shock_lookback,
                    'min_volatility_atr_period': self._regime_classifier.min_volatility_atr_period,
                    'persistence_candles': self._regime_classifier.persistence_candles
                }

                # Save market state
                try:
                    self._storage.log_market_state(state_data)
                    logger.info(
                        f"Cambio de régimen detectado: {signal.symbol} "
                        f"{previous_regime.value if previous_regime else 'N/A'} -> {regime.value}"
                    )
                except Exception as e:
                    logger.error(f"Error guardando estado de mercado: {e}")

                # Send regime change notification
                notifier = get_notifier()
                if notifier:
                    membership = MembershipLevel.BASIC
                    try:
                        await notifier.notify_regime_change(
                            symbol=signal.symbol,
                            previous_regime=previous_regime,
                            new_regime=regime,
                            price=signal.price,
                            membership=membership,
                            metrics=metrics
                        )
                    except Exception as e:
                        logger.error(f"Error enviando notificación de cambio de régimen: {e}")

                # Update previous regime
                self._last_regime_by_symbol[signal.symbol] = regime

            # Save to database
            signal_id = self._storage.save_signal(signal)

            logger.info(
                f"Señal procesada: {signal.symbol} {signal.signal_type.value} "
                f"@ {signal.price} - Régimen: {regime.value} (ID: {signal_id})"
            )

            # Send confirmation to client
            response = {
                "type": "signal_processed",
                "signal_id": signal_id,
                "regime": regime.value,
                "timestamp": datetime.now().isoformat()
            }

            if self._socket_service:
                await self._socket_service.send_personal_message(response, client_id)

            # Check for Oliver Vélez signal and send notification
            module_manager = get_module_manager()
            notifier = get_notifier()

            is_oliver_velez = (
                signal.strategy_id and "oliver_velez" in signal.strategy_id.lower()
            ) or (
                module_manager.is_module_enabled("oliver_velez") and
                regime in [MarketRegime.TREND, MarketRegime.RANGE]
            )

            if is_oliver_velez:
                await self._broadcast_thought(
                    f"Validando parámetros de Oliver Vélez para {signal.symbol}...",
                    module="STRATEGY"
                )

            if is_oliver_velez and notifier:
                membership = MembershipLevel.BASIC
                try:
                    # Get metrics if not already fetched
                    if metrics is None:
                        metrics = self._regime_classifier.get_metrics()

                    strategy_details = {
                        "Régimen": regime.value,
                        "ADX": f"{metrics.get('adx', 0):.2f}" if metrics else "N/A",
                        "Volatilidad": f"{metrics.get('volatility', 0):.4f}" if metrics else "N/A"
                    }
                    await notifier.notify_oliver_velez_signal(
                        signal=signal,
                        membership=membership,
                        strategy_details=strategy_details
                    )
                except Exception as e:
                    logger.error(f"Error enviando notificación de señal Oliver Vélez: {e}")

        except Exception as e:
            logger.error(f"Error procesando señal de {client_id}: {e}")
            raise


# ========== Singleton ==========

_trading_service_instance = None


def get_trading_service(storage: Optional[Any] = None, regime_classifier: Optional[Any] = None, socket_service: Optional[Any] = None) -> TradingService:
    """Lazy-load TradingService singleton."""
    global _trading_service_instance
    if _trading_service_instance is None:
        if storage is None:
            from data_vault.storage import StorageManager
            storage = StorageManager()
        _trading_service_instance = TradingService(
            storage=storage,
            regime_classifier=regime_classifier,
            socket_service=socket_service
        )
    return _trading_service_instance
