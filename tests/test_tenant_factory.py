"""
test_tenant_factory.py — TDD Test Suite for TenantDBFactory (HU 8.1)
Trace_ID: SAAS-BACKBONE-2026-001

Tests are written BEFORE production code, per TDD contract.
All tests use temporary paths — zero production DB pollution.
"""
import os
import threading
import pytest
from pathlib import Path

from data_vault.tenant_factory import TenantDBFactory
from data_vault.storage import StorageManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_factory_cache():
    """
    Reset TenantDBFactory singleton cache before and after each test.
    Guarantees full isolation between tests.
    """
    TenantDBFactory._instances.clear()
    yield
    # Close any open persistent connections before clearing
    for sm in TenantDBFactory._instances.values():
        if hasattr(sm, '_persistent_conn') and sm._persistent_conn:
            try:
                sm._persistent_conn.close()
            except Exception:
                pass
    TenantDBFactory._instances.clear()


@pytest.fixture
def tenant_root(tmp_path: Path) -> str:
    """Return a temporary tenants root directory path."""
    tenants_dir = tmp_path / "tenants"
    tenants_dir.mkdir()
    return str(tmp_path)


# ---------------------------------------------------------------------------
# HU 8.1-T1 — Auto-Provisioning
# ---------------------------------------------------------------------------

class TestAutoProvisioning:
    """TenantDBFactory must create a private DB on first access."""

    def test_new_tenant_creates_db_automatically(self, tmp_path):
        """
        GIVEN: A tenant_id that has never been used.
        WHEN:  get_storage() is called.
        THEN:  A new DB file is created at data_vault/tenants/{id}/aethelgard.db
               and the StorageManager is fully initialised.
        """
        expected_db = tmp_path / "tenants" / "user_alpha" / "aethelgard.db"
        assert not expected_db.exists(), "Precondition: DB must not exist yet"

        storage = TenantDBFactory.get_storage("user_alpha", base_path=str(tmp_path))

        assert expected_db.exists(), "DB file must be created automatically"
        assert isinstance(storage, StorageManager)

    def test_schema_is_initialised_for_new_tenant(self, tmp_path):
        """
        GIVEN: A brand-new tenant DB.
        WHEN:  get_storage() is called.
        THEN:  The DB contains the expected core tables (signals, trades, system_state).
        """
        storage = TenantDBFactory.get_storage("user_beta", base_path=str(tmp_path))

        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
        finally:
            storage._close_conn(conn)

        assert "signals" in tables
        assert "trade_results" in tables
        assert "system_state" in tables
        assert "user_preferences" in tables


# ---------------------------------------------------------------------------
# HU 8.1-T2 — Tenant Isolation (The Cathedral Wall Test)
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Data written to Tenant A must NEVER be readable by Tenant B."""

    def test_trade_data_does_not_cross_pollinate(self, tmp_path):
        """
        GIVEN: Two independent tenants.
        WHEN:  Tenant A saves a trade result.
        THEN:  Tenant B's trade list is empty — zero data leakage.
        """
        storage_a = TenantDBFactory.get_storage("tenant_alice", base_path=str(tmp_path))
        storage_b = TenantDBFactory.get_storage("tenant_bob", base_path=str(tmp_path))

        trade = {
            "id": "trade_alice_001",
            "signal_id": "sig_001",
            "symbol": "EURUSD",
            "entry_price": 1.1000,
            "exit_price": 1.1050,
            "profit": 50.0,
            "exit_reason": "Take Profit",
            "close_time": "2026-02-26T15:00:00"
        }
        storage_a.save_trade_result(trade)

        # Bob must see zero trades
        bob_trades = storage_b.get_recent_trades(limit=10)
        assert len(bob_trades) == 0, "Tenant B must NOT see Tenant A's trades"

    def test_system_state_is_isolated_per_tenant(self, tmp_path):
        """
        GIVEN: Two independent tenants.
        WHEN:  Tenant A sets lockdown_mode=True.
        THEN:  Tenant B's system state is unchanged (lockdown_mode defaults to False/missing).
        """
        storage_a = TenantDBFactory.get_storage("tenant_carol", base_path=str(tmp_path))
        storage_b = TenantDBFactory.get_storage("tenant_dave", base_path=str(tmp_path))

        storage_a.update_system_state({"lockdown_mode": True})

        state_b = storage_b.get_system_state()
        assert not state_b.get("lockdown_mode", False), \
            "Tenant B's lockdown_mode must be unaffected by Tenant A"

    def test_db_files_are_physically_separate(self, tmp_path):
        """
        GIVEN: Two tenants with active StorageManagers.
        THEN:  Each has its own physical DB path — they are different files.
        """
        storage_a = TenantDBFactory.get_storage("file_alice", base_path=str(tmp_path))
        storage_b = TenantDBFactory.get_storage("file_bob", base_path=str(tmp_path))

        assert storage_a.db_path != storage_b.db_path
        assert os.path.isfile(storage_a.db_path)
        assert os.path.isfile(storage_b.db_path)


# ---------------------------------------------------------------------------
# HU 8.1-T3 — Singleton Cache (Thread-Safe)
# ---------------------------------------------------------------------------

class TestSingletonCache:
    """Same tenant_id must always return the exact same instance."""

    def test_same_tenant_returns_same_instance(self, tmp_path):
        """
        GIVEN: get_storage() called twice with the same tenant_id.
        THEN:  Both calls return the identical object (is, not just ==).
        """
        s1 = TenantDBFactory.get_storage("tenant_eve", base_path=str(tmp_path))
        s2 = TenantDBFactory.get_storage("tenant_eve", base_path=str(tmp_path))

        assert s1 is s2, "Factory must return the cached instance on subsequent calls"

    def test_different_tenants_return_different_instances(self, tmp_path):
        """
        GIVEN: Two different tenant_ids.
        THEN:  Each gets its own StorageManager instance.
        """
        s_a = TenantDBFactory.get_storage("tenant_frank", base_path=str(tmp_path))
        s_b = TenantDBFactory.get_storage("tenant_grace", base_path=str(tmp_path))

        assert s_a is not s_b

    def test_concurrent_access_returns_same_instance(self, tmp_path):
        """
        GIVEN: 10 threads simultaneously calling get_storage() for the same tenant_id.
        THEN:  All receive the identical instance — no duplicate DBs created.
        """
        results = []
        barrier = threading.Barrier(10)

        def get_storage_thread():
            barrier.wait()  # All start simultaneously
            s = TenantDBFactory.get_storage("concurrent_tenant", base_path=str(tmp_path))
            results.append(id(s))

        threads = [threading.Thread(target=get_storage_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 1, \
            "All threads must receive the exact same instance (thread-safe singleton)"


# ---------------------------------------------------------------------------
# HU 8.1-T4 — Release / Eviction
# ---------------------------------------------------------------------------

class TestRelease:
    """Releasing a tenant must evict it from cache."""

    def test_release_removes_from_cache(self, tmp_path):
        """
        GIVEN: A tenant is cached.
        WHEN:  release() is called.
        THEN:  The next get_storage() returns a NEW instance.
        """
        s1 = TenantDBFactory.get_storage("tenant_henry", base_path=str(tmp_path))
        TenantDBFactory.release("tenant_henry")

        s2 = TenantDBFactory.get_storage("tenant_henry", base_path=str(tmp_path))

        assert s1 is not s2, "After release(), a fresh instance must be created"

    def test_release_unknown_tenant_does_not_raise(self, tmp_path):
        """release() on an unknown tenant_id must be a no-op (no exception)."""
        TenantDBFactory.release("nonexistent_tenant")  # Must not raise


# ---------------------------------------------------------------------------
# HU 8.1-T5 — Global Fallback (Backward Compatibility)
# ---------------------------------------------------------------------------

class TestGlobalFallback:
    """StorageManager() with no args must still work — zero regression."""

    def test_storage_manager_no_args_uses_global_db(self, tmp_path):
        """
        GIVEN: StorageManager instantiated with a temp path (simulating global DB).
        THEN:  It works exactly as before — no dependency on TenantDBFactory.
        """
        global_storage = StorageManager(db_path=str(tmp_path / "global.db"))

        # Perform a basic operation to verify it's fully functional
        global_storage.update_system_state({"ping": "pong"})
        state = global_storage.get_system_state()

        assert state.get("ping") == "pong"

    def test_tenant_factory_does_not_affect_global_storage(self, tmp_path):
        """
        GIVEN: TenantDBFactory creates tenant DBs.
        THEN:  A separate global StorageManager is completely independent.
        """
        tenant_storage = TenantDBFactory.get_storage("tenant_iris", base_path=str(tmp_path))
        tenant_storage.update_system_state({"tenant_key": "tenant_value"})

        global_storage = StorageManager(db_path=str(tmp_path / "global_aethelgard.db"))
        global_state = global_storage.get_system_state()

        assert "tenant_key" not in global_state, \
            "Global StorageManager must be unaffected by tenant writes"
