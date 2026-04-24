"""
ConnectorFactory — builds broker connectors from sys_broker_account records.

Lives inside connectors/ so it is the ONLY place that knows about concrete
connector classes (MT5Connector, CTraderConnector, etc.).  Business logic
modules (core_brain, scripts) must import only this factory, never specific
connector classes directly.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_PLATFORM_BUILDERS: dict[str, Any] = {}


def _builder_for(platform_id: str) -> Callable[[Callable[..., Optional[Any]]], Callable[..., Optional[Any]]]:
    """Decorator that registers a connector builder by platform_id."""
    def decorator(fn: Callable[..., Optional[Any]]) -> Callable[..., Optional[Any]]:
        _PLATFORM_BUILDERS[platform_id] = fn
        return fn
    return decorator


@_builder_for("mt5")
def _build_mt5(account: dict) -> Optional[Any]:
    try:
        from connectors.mt5_connector import MT5Connector
        connector = MT5Connector(account_id=account.get("account_id"))
        if connector.connect_blocking():
            return connector
        logger.warning(
            "[ConnectorFactory] MT5 connect_blocking() returned False for account_id=%s",
            account.get("account_id"),
        )
    except ImportError:
        logger.debug("[ConnectorFactory] MT5Connector not importable — MetaTrader5 library missing")
    except Exception as exc:
        logger.warning("[ConnectorFactory] Failed to build MT5 connector: %s", exc)
    return None


@_builder_for("ctrader")
def _build_ctrader(account: dict) -> Optional[Any]:
    try:
        from connectors.ctrader_connector import CTraderConnector
        connector = CTraderConnector(
            account_number=account.get("account_number"),
            server=account.get("server"),
            account_type=account.get("account_type", "demo"),
        )
        if connector.connect():
            return connector
    except ImportError:
        logger.debug("[ConnectorFactory] CTraderConnector not importable")
    except Exception as exc:
        logger.warning("[ConnectorFactory] Failed to build cTrader connector: %s", exc)
    return None


def build_connector_from_account(account: dict) -> Optional[Any]:
    """
    Instantiate and connect the appropriate connector for a sys_broker_account row.

    Args:
        account: Dict with at minimum 'platform_id', 'account_number', 'server'.

    Returns:
        Connected BaseConnector instance, or None if unavailable / connection failed.
    """
    platform_id: str = (account.get("platform_id") or "").lower()
    builder = _PLATFORM_BUILDERS.get(platform_id)
    if builder is None:
        logger.debug("[ConnectorFactory] No builder registered for platform_id='%s'", platform_id)
        return None
    return builder(account)
