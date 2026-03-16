"""
N2-2: WebSocket Auth Standardization — TDD Test Suite
Trace_ID: WS-AUTH-STD-N2-2026-03-15

Verifies that ALL WebSocket endpoints reject unauthenticated connections
via the unified get_ws_user() dependency, replacing all _verify_token()
manual implementations and demo-token fallbacks.

AC-1: No token → 1008 Policy Violation on all 3 WS endpoints
AC-2: Invalid token → 1008 on all 3 WS endpoints
AC-3: Valid cookie → connection accepted, tenant_id extracted
AC-4: No _verify_token() or demo fallback in any router
AC-5: get_ws_user() is the single WS auth function in auth.py
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketState

from models.auth import TokenPayload
from core_brain.api.dependencies.auth import get_ws_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_token_payload(tenant_id: str = "tenant_001") -> TokenPayload:
    """Return a realistic TokenPayload for use in tests."""
    return TokenPayload(
        sub=tenant_id,
        exp=9999999999.0,
        role="trader",
        tid=tenant_id,
    )


def _make_app_with_ws_user_override(override_fn) -> FastAPI:
    """
    Create a minimal FastAPI app that has a /ws/test endpoint
    protected by get_ws_user, with the dependency overridden.
    Used to test the dependency contract in isolation.
    """
    from fastapi import Depends
    app = FastAPI()

    @app.websocket("/ws/test")
    async def ws_endpoint(
        websocket: WebSocket,
        token_data: TokenPayload = Depends(get_ws_user),
    ) -> None:
        await websocket.accept()
        await websocket.send_json({"tid": token_data.sub})
        await websocket.close()

    app.dependency_overrides[get_ws_user] = override_fn
    return app


# ---------------------------------------------------------------------------
# AC-5: get_ws_user exists in auth.py and is importable
# ---------------------------------------------------------------------------

class TestGetWsUserExists:
    """AC-5: get_ws_user must exist as the single WS auth dependency."""

    def test_get_ws_user_is_importable(self):
        """get_ws_user must be importable from dependencies.auth."""
        from core_brain.api.dependencies.auth import get_ws_user
        assert callable(get_ws_user)

    def test_get_current_active_user_still_exists(self):
        """HTTP dependency must not be affected."""
        from core_brain.api.dependencies.auth import get_current_active_user
        assert callable(get_current_active_user)


# ---------------------------------------------------------------------------
# AC-3: Valid credentials → accepted, tenant_id extracted
# ---------------------------------------------------------------------------

class TestGetWsUserValidCredentials:
    """AC-3: Valid cookie/header/query → connection accepted."""

    @pytest.mark.asyncio
    async def test_valid_cookie_returns_token_payload(self):
        """get_ws_user returns TokenPayload when cookie is valid."""
        valid_payload = _make_valid_token_payload()

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {"a_token": "valid.jwt.token"}
        mock_ws.headers = {}

        mock_auth = MagicMock()
        mock_auth.decode_token.return_value = valid_payload

        from core_brain.api.dependencies.auth import get_ws_user
        result = await get_ws_user(websocket=mock_ws, token=None, auth_service=mock_auth)

        assert result.sub == "tenant_001"
        mock_auth.decode_token.assert_called_once_with("valid.jwt.token")

    @pytest.mark.asyncio
    async def test_valid_bearer_header_returns_token_payload(self):
        """get_ws_user returns TokenPayload when Authorization header is valid."""
        valid_payload = _make_valid_token_payload("tenant_002")

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {}
        mock_ws.headers = {"authorization": "Bearer header.jwt.token"}

        mock_auth = MagicMock()
        mock_auth.decode_token.return_value = valid_payload

        from core_brain.api.dependencies.auth import get_ws_user
        result = await get_ws_user(websocket=mock_ws, token=None, auth_service=mock_auth)

        assert result.sub == "tenant_002"
        mock_auth.decode_token.assert_called_once_with("header.jwt.token")

    @pytest.mark.asyncio
    async def test_valid_query_param_returns_token_payload(self):
        """get_ws_user returns TokenPayload when query ?token= is valid."""
        valid_payload = _make_valid_token_payload("tenant_003")

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {}
        mock_ws.headers = {}

        mock_auth = MagicMock()
        mock_auth.decode_token.return_value = valid_payload

        from core_brain.api.dependencies.auth import get_ws_user
        result = await get_ws_user(
            websocket=mock_ws, token="query.jwt.token", auth_service=mock_auth
        )

        assert result.sub == "tenant_003"
        mock_auth.decode_token.assert_called_once_with("query.jwt.token")

    @pytest.mark.asyncio
    async def test_cookie_has_priority_over_query(self):
        """AC cookie priority: cookie wins over query param."""
        cookie_payload = _make_valid_token_payload("cookie_tenant")

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {"a_token": "cookie.jwt.token"}
        mock_ws.headers = {}

        mock_auth = MagicMock()
        mock_auth.decode_token.return_value = cookie_payload

        from core_brain.api.dependencies.auth import get_ws_user
        result = await get_ws_user(
            websocket=mock_ws, token="query.jwt.token", auth_service=mock_auth
        )

        # Must use cookie, not query
        mock_auth.decode_token.assert_called_once_with("cookie.jwt.token")
        assert result.sub == "cookie_tenant"


# ---------------------------------------------------------------------------
# AC-1 & AC-2: Missing / invalid credentials → WebSocketException(1008)
# ---------------------------------------------------------------------------

class TestGetWsUserRejectsInvalidCreds:
    """AC-1/AC-2: Missing or invalid token → WebSocketException with code 1008."""

    @pytest.mark.asyncio
    async def test_no_token_raises_websocket_exception(self):
        """get_ws_user raises WebSocketException(1008) when no token provided."""
        from fastapi import WebSocketException

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {}
        mock_ws.headers = {}

        with pytest.raises(WebSocketException) as exc_info:
            from core_brain.api.dependencies.auth import get_ws_user
            await get_ws_user(websocket=mock_ws, token=None)

        assert exc_info.value.code == 1008

    @pytest.mark.asyncio
    async def test_invalid_token_raises_websocket_exception(self):
        """get_ws_user raises WebSocketException(1008) when token is invalid."""
        from fastapi import WebSocketException

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {"a_token": "invalid.token.here"}
        mock_ws.headers = {}

        mock_auth = MagicMock()
        mock_auth.decode_token.return_value = None  # Simulate invalid token

        from core_brain.api.dependencies.auth import get_ws_user
        with pytest.raises(WebSocketException) as exc_info:
            await get_ws_user(websocket=mock_ws, token=None, auth_service=mock_auth)

        assert exc_info.value.code == 1008

    @pytest.mark.asyncio
    async def test_empty_string_token_raises_websocket_exception(self):
        """Empty string token is treated as no token."""
        from fastapi import WebSocketException

        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.cookies = {}
        mock_ws.headers = {}

        with pytest.raises(WebSocketException) as exc_info:
            from core_brain.api.dependencies.auth import get_ws_user
            await get_ws_user(websocket=mock_ws, token="")

        assert exc_info.value.code == 1008


# ---------------------------------------------------------------------------
# AC-4: No _verify_token() or demo fallback exists in routers
# ---------------------------------------------------------------------------

class TestNoLegacyAuthInRouters:
    """AC-4: _verify_token() and demo fallback must be removed from all routers."""

    def _read_router(self, filename: str) -> str:
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "core_brain",
            "api",
            "routers",
            filename,
        )
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_strategy_ws_has_no_verify_token(self):
        """strategy_ws.py must not contain _verify_token()."""
        content = self._read_router("strategy_ws.py")
        assert "_verify_token" not in content, (
            "strategy_ws.py still contains _verify_token() — not removed"
        )

    def test_telemetry_has_no_verify_token(self):
        """telemetry.py must not contain _verify_token()."""
        content = self._read_router("telemetry.py")
        assert "_verify_token" not in content, (
            "telemetry.py still contains _verify_token() — not removed"
        )

    def test_telemetry_has_no_demo_fallback(self):
        """telemetry.py must not contain demo fallback token generation."""
        content = self._read_router("telemetry.py")
        assert "demo@aethelgard" not in content, (
            "telemetry.py still contains demo-token fallback — security vulnerability"
        )

    def test_shadow_ws_has_no_demo_fallback(self):
        """shadow_ws.py must not contain demo fallback token generation."""
        content = self._read_router("shadow_ws.py")
        assert "demo@aethelgard" not in content, (
            "shadow_ws.py still contains demo-token fallback — security vulnerability"
        )

    def test_strategy_ws_uses_get_ws_user(self):
        """strategy_ws.py must import and use get_ws_user."""
        content = self._read_router("strategy_ws.py")
        assert "get_ws_user" in content, (
            "strategy_ws.py does not use get_ws_user dependency"
        )

    def test_telemetry_uses_get_ws_user(self):
        """telemetry.py must import and use get_ws_user."""
        content = self._read_router("telemetry.py")
        assert "get_ws_user" in content, (
            "telemetry.py does not use get_ws_user dependency"
        )

    def test_shadow_ws_uses_get_ws_user(self):
        """shadow_ws.py must import and use get_ws_user."""
        content = self._read_router("shadow_ws.py")
        assert "get_ws_user" in content, (
            "shadow_ws.py does not use get_ws_user dependency"
        )
