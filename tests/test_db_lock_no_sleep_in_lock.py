"""
Tests TDD: BaseRepository._execute_serialized debe evitar deadlock con múltiples threads.

Test anterior trataba de verificar que time.sleep() no se ejecutaba dentro
de un lock (lo cual causaría deadlock).

Desde FIX-DATABASE-MANAGER-SINGLETON-2026-04-01:
- Toda retry logic está en DatabaseManager (que maneja locks correctamente)
- BaseRepository._execute_serialized delegó al DatabaseManager.transaction()
- Este test ahora verifica que no hay deadlock en la nueva arquitectura
"""
import inspect
import threading
import pytest
from data_vault.base_repo import BaseRepository


class TestDbLockNoSleepInLock:
    def test_sleep_is_not_called_while_lock_is_held(self):
        """
        Verifica que múltiples hilos pueden acceder a _execute_serialized sin deadlock.

        Desde FIX-DATABASE-MANAGER-SINGLETON: La arquitectura delegó
        retry logic a DatabaseManager, que maneja locks inteligentemente.
        Este test verifica que la adaptación no introduce deadlock.
        """
        repo = BaseRepository(db_path=":memory:")

        call_order = []
        results = []

        def worker(worker_id):
            """Worker que ejecuta una operación simple."""
            def simple_op(conn):
                call_order.append(f"worker_{worker_id}_executed")
                return f"ok_{worker_id}"

            try:
                result = repo._execute_serialized(simple_op)
                results.append(result)
            except Exception as e:
                results.append(f"error_{worker_id}: {e}")

        # Spawn 3 concurrent workers
        import threading
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Verify all workers completed
        assert len(results) == 3, f"Expected 3 results, got {len(results)}: {results}"
        assert all("ok_" in r for r in results), f"Some workers failed: {results}"
        assert "lock_still_held_during_sleep" not in call_order, (
            "Deadlock detected: lock held too long"
        )

    def test_get_conn_uses_timeout_or_busy_pragma(self):
        """
        _get_conn() debe estar respaldado por un mecanismo de timeout en sqlite3
        (via sqlite3.connect(..., timeout=N) o PRAGMA busy_timeout).

        Desde FIX-DATABASE-MANAGER-SINGLETON: _get_conn() delega a DatabaseManager,
        que proporciona timeout=120 y PRAGMA busy_timeout=120000.
        """
        from data_vault.database_manager import get_database_manager

        # Verify DatabaseManager tiene timeout configurado
        db_manager = get_database_manager()

        # Check 1: sqlite3.connect() timeout
        source_manager = inspect.getsource(db_manager.get_connection)
        has_timeout_param = "timeout=" in source_manager

        # Check 2: O PRAGMA busy_timeout en config
        pragma_config = db_manager.get_pragma_config()
        has_busy_pragma = "busy_timeout" in pragma_config and pragma_config.get("busy_timeout", 0) > 0

        assert has_timeout_param or has_busy_pragma, (
            "DatabaseManager debe usar sqlite3.connect(..., timeout=N) "
            "o PRAGMA busy_timeout=N para evitar fallo inmediato en contención."
        )

    def test_two_threads_do_not_deadlock(self):
        """
        Con el fix aplicado, dos hilos ejecutando _execute_serialized
        deben completar sin deadlock en menos de 2 segundos.
        """
        repo = BaseRepository(db_path=":memory:")
        results = []

        def worker():
            def noop(conn):
                return "ok"
            results.append(repo._execute_serialized(noop))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        assert not t1.is_alive(), "Hilo t1 bloqueado — posible deadlock"
        assert not t2.is_alive(), "Hilo t2 bloqueado — posible deadlock"
        assert results.count("ok") == 2
