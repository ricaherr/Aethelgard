from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

import core_brain.api.routers.system as system_router
import core_brain.server as server_module


class _DummySystemService:
    async def start_heartbeat(self) -> None:
        return None

    async def stop_heartbeat(self) -> None:
        return None


class _StubStorage:
    def __init__(
        self,
        *,
        heartbeats: dict[str, str] | None = None,
        operational_mode: str = "NORMAL",
        last_signal_at: str | None = None,
        last_trade_at: str | None = None,
        active_strategies_count: int = 0,
        fail_sys_config: bool = False,
    ) -> None:
        self._heartbeats = heartbeats or {}
        self._operational_mode = operational_mode
        self._last_signal_at = last_signal_at
        self._last_trade_at = last_trade_at
        self._active_strategies_count = active_strategies_count
        self._fail_sys_config = fail_sys_config

    def get_sys_config(self) -> dict[str, Any]:
        if self._fail_sys_config:
            raise RuntimeError("db unavailable")
        payload: dict[str, Any] = {
            "operational_mode": self._operational_mode,
        }
        payload.update({f"heartbeat_{k}": v for k, v in self._heartbeats.items()})
        return payload

    def get_recent_sys_signals(self, minutes: int = 1440, limit: int = 1, **_: Any) -> list[dict[str, Any]]:
        if self._last_signal_at is None:
            return []
        return [{"timestamp": self._last_signal_at}]

    def get_recent_usr_trades(self, limit: int = 1, execution_mode: str | None = None) -> list[dict[str, Any]]:
        if self._last_trade_at is None:
            return []
        return [{"created_at": self._last_trade_at}]

    def execute_query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "COUNT(*)" in sql:
            return [{"count": self._active_strategies_count}]
        return []



def _build_client(monkeypatch: Any) -> TestClient:
    monkeypatch.setattr(server_module, "_system_service_instance", _DummySystemService())
    app = server_module.create_app()
    return TestClient(app, raise_server_exceptions=False)


def test_health_endpoint_happy_path_contract(monkeypatch: Any) -> None:
    now = datetime.now(timezone.utc)
    storage = _StubStorage(
        heartbeats={
            "orchestrator": (now - timedelta(seconds=5)).isoformat(),
            "scanner": (now - timedelta(seconds=7)).isoformat(),
            "signal_factory": (now - timedelta(seconds=6)).isoformat(),
        },
        operational_mode="NORMAL",
        last_signal_at=(now - timedelta(minutes=3)).isoformat(),
        last_trade_at=(now - timedelta(minutes=5)).isoformat(),
        active_strategies_count=3,
    )
    monkeypatch.setattr(system_router, "_get_storage", lambda: storage)

    client = _build_client(monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    required_fields = {
        "status",
        "timestamp_utc",
        "orchestrator_heartbeat_age_s",
        "scanner_heartbeat_age_s",
        "signal_factory_heartbeat_age_s",
        "operational_mode",
        "last_signal_at",
        "last_trade_at",
        "active_strategies_count",
    }
    assert required_fields.issubset(payload.keys())
    assert payload["status"] == "ok"
    assert payload["operational_mode"] == "NORMAL"
    assert payload["active_strategies_count"] == 3


def test_health_endpoint_degraded_on_stale_heartbeat(monkeypatch: Any) -> None:
    now = datetime.now(timezone.utc)
    storage = _StubStorage(
        heartbeats={
            "orchestrator": (now - timedelta(seconds=500)).isoformat(),
            "scanner": (now - timedelta(seconds=10)).isoformat(),
            "signal_factory": (now - timedelta(seconds=12)).isoformat(),
        },
        active_strategies_count=1,
    )
    monkeypatch.setattr(system_router, "_get_storage", lambda: storage)

    client = _build_client(monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["orchestrator_heartbeat_age_s"] is not None
    assert payload["orchestrator_heartbeat_age_s"] > 120


def test_health_endpoint_db_error_returns_safe_payload(monkeypatch: Any) -> None:
    storage = _StubStorage(fail_sys_config=True)
    monkeypatch.setattr(system_router, "_get_storage", lambda: storage)

    client = _build_client(monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"degraded", "down"}
    assert "timestamp_utc" in payload


def test_health_endpoint_does_not_expose_secrets(monkeypatch: Any) -> None:
    now = datetime.now(timezone.utc)
    storage = _StubStorage(
        heartbeats={
            "orchestrator": (now - timedelta(seconds=5)).isoformat(),
            "scanner": (now - timedelta(seconds=5)).isoformat(),
            "signal_factory": (now - timedelta(seconds=5)).isoformat(),
        },
        active_strategies_count=2,
    )
    monkeypatch.setattr(system_router, "_get_storage", lambda: storage)

    client = _build_client(monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    payload_text = response.text.lower()
    for blocked_key in ("password", "token", "api_key", "secret"):
        assert blocked_key not in payload_text
