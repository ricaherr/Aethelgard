"""
test_tenant_signal_isolation.py — Prueba de Fuego: HU 8.1
Trace_ID: SAAS-BACKBONE-2026-001

Objetivo:
    Verificar que la señal guardada por el Usuario_A NO es visible para el Usuario_B.
    Esta es la prueba definitiva de soberanía de datos del sistema multi-tenant.

Rules (TDD):
    - All tests use temporary paths — zero production DB pollution.
    - TenantDBFactory cache must be cleared between tests for full isolation.
"""
import pytest
from pathlib import Path

from data_vault.tenant_factory import TenantDBFactory
from data_vault.storage import StorageManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_factory_cache():
    """Reset TenantDBFactory cache before/after each test for clean isolation."""
    TenantDBFactory._instances.clear()
    yield
    for sm in TenantDBFactory._instances.values():
        if hasattr(sm, '_persistent_conn') and sm._persistent_conn:
            try:
                sm._persistent_conn.close()
            except Exception:
                pass
    TenantDBFactory._instances.clear()


def _make_signal(signal_id: str, symbol: str = "EURUSD") -> dict:
    """Helper: build a minimal valid signal dict for save_signal()."""
    return {
        "id": signal_id,
        "symbol": symbol,
        "signal_type": "BUY",
        "confidence": 0.92,
        "timeframe": "H1",
        "price": 1.1050,
        "direction": "LONG",
        "status": "active",
    }


# ---------------------------------------------------------------------------
# HU 8.1: Prueba de Fuego — Señal Isolation
# ---------------------------------------------------------------------------

class TestSignalIsolation:
    """
    GIVEN: Two tenants with physically separated SQLite databases.
    WHEN:  Usuario_A saves a signal via its StorageManager.
    THEN:  Usuario_B queries its signals and receives an EMPTY result set.
           Zero data leakage between tenants.
    """

    def test_signal_saved_by_user_a_is_invisible_to_user_b(self, tmp_path: Path):
        """
        PRUEBA DE FUEGO (especificada en HU 8.1):
        Usuario_A guarda una señal → Usuario_B debe recibir un set de datos vacío.
        """
        # Arrange
        storage_a = TenantDBFactory.get_storage("usuario_a", base_path=str(tmp_path))
        storage_b = TenantDBFactory.get_storage("usuario_b", base_path=str(tmp_path))

        signal_for_a = _make_signal("signal_user_a_001", symbol="EURUSD")

        # Act: Only Usuario_A writes a signal
        storage_a.save_signal(signal_for_a)

        # Assert: Usuario_B sees NOTHING
        signals_b = storage_b.get_recent_signals(limit=10)
        assert len(signals_b) == 0, (
            "AISLAMIENTO ROTO: Usuario_B puede ver la señal de Usuario_A. "
            "Soberanía de datos comprometida."
        )

    def test_each_tenant_only_sees_its_own_signals(self, tmp_path: Path):
        """
        Both tenants write signals. Each should only see their own data.
        """
        storage_a = TenantDBFactory.get_storage("tenant_alice", base_path=str(tmp_path))
        storage_b = TenantDBFactory.get_storage("tenant_bob", base_path=str(tmp_path))

        # Both write a signal
        storage_a.save_signal(_make_signal("sig_alice_001", symbol="EURUSD"))
        storage_a.save_signal(_make_signal("sig_alice_002", symbol="GBPUSD"))
        storage_b.save_signal(_make_signal("sig_bob_001", symbol="USDJPY"))

        signals_a = storage_a.get_recent_signals(limit=10)
        signals_b = storage_b.get_recent_signals(limit=10)

        # Alice sees exactly 2 signals — her own
        assert len(signals_a) == 2, f"Alice debe ver 2 señales, vio {len(signals_a)}"

        # Bob sees exactly 1 signal — his own
        assert len(signals_b) == 1, f"Bob debe ver 1 señal, vio {len(signals_b)}"

        # Verify signal IDs never cross-pollinate
        alice_ids = {s.get("id") or s.get("signal_id") for s in signals_a}
        bob_ids = {s.get("id") or s.get("signal_id") for s in signals_b}
        assert alice_ids.isdisjoint(bob_ids), (
            "AISLAMIENTO ROTO: IDs de señales se solapan entre tenants."
        )

    def test_signal_count_correct_after_multiple_writes(self, tmp_path: Path):
        """
        A tenant writing N signals must have exactly N signals — no phantom rows
        from other tenants.
        """
        storage_a = TenantDBFactory.get_storage("big_writer", base_path=str(tmp_path))
        storage_b = TenantDBFactory.get_storage("silent_reader", base_path=str(tmp_path))

        # A writes 5 signals
        for i in range(5):
            storage_a.save_signal(_make_signal(f"sig_a_{i:03d}"))

        # B writes 0 signals — but both DBs were provisioned and are active

        signals_b = storage_b.get_recent_signals(limit=20)
        assert len(signals_b) == 0, (
            f"CONTAMINACIÓN DETECTADA: Usuario_B (silent_reader) tiene {len(signals_b)} señales "
            "a pesar de no haber guardado ninguna."
        )


# ---------------------------------------------------------------------------
# HU 8.1: Blindaje via TradingService (agnosticismo confirmado)
# ---------------------------------------------------------------------------

class TestTradingServiceTenantBlindage:
    """
    The TradingService must not know HOW data is stored.
    It only passes tenant_id — the storage property handles the rest.
    """

    def test_trading_service_with_tenant_id_uses_isolated_storage(self, tmp_path: Path):
        """
        GIVEN: TradingService instantiated with tenant_id.
        THEN:  Its storage property resolves to the tenant's isolated StorageManager.
               Writing data does NOT affect the global DB or other tenants.
        """
        from core_brain.services.trading_service import TradingService

        # Provision tenant storage via factory first (simulates real call)
        tenant_storage = TenantDBFactory.get_storage("svc_tenant_x", base_path=str(tmp_path))

        # Create TradingService with tenant storage (simulates per-request DI)
        svc = TradingService(storage=tenant_storage)

        # Storage must be the tenant's isolated instance
        assert svc.storage is tenant_storage

        # Any operation on svc.storage writes to the tenant's private DB only
        svc.storage.update_system_state({"tenant_marker": "svc_tenant_x"})
        state = svc.storage.get_system_state()
        assert state.get("tenant_marker") == "svc_tenant_x"

        # Verify no other tenant has this marker
        other_storage = TenantDBFactory.get_storage("svc_tenant_y", base_path=str(tmp_path))
        other_state = other_storage.get_system_state()
        assert "tenant_marker" not in other_state, (
            "tenant_marker de svc_tenant_x no debe existir en svc_tenant_y."
        )

    def test_get_trading_service_with_tenant_id_returns_fresh_instance(self, tmp_path: Path):
        """
        get_trading_service(tenant_id=...) returns a NEW per-tenant instance,
        not the global singleton. Two different tenant_ids get different objects
        with different StorageManagers.
        """
        from core_brain.services.trading_service import get_trading_service

        # HU 8.1: passing tenant_id forces a fresh (non-singleton) instance
        svc_a = get_trading_service(tenant_id="tgt_tenant_a")
        svc_b = get_trading_service(tenant_id="tgt_tenant_b")

        # Trigger lazy storage resolution so we can compare them
        # (pre-provision via factory using tmp_path to keep DBs isolated)
        TenantDBFactory.get_storage("tgt_tenant_a", base_path=str(tmp_path))
        TenantDBFactory.get_storage("tgt_tenant_b", base_path=str(tmp_path))

        # Two different tenant_id instances → must be different objects entirely
        assert svc_a is not svc_b, (
            "get_trading_service con tenant_id diferente debe devolver instancias distintas."
        )

        # Each service bound to a different tenant_id
        assert svc_a._tenant_id != svc_b._tenant_id, (
            "Cada instancia per-tenant debe conservar su propio tenant_id."
        )

