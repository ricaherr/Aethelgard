"""
Tests TDD: BaseRepository._execute_serialized no debe dormir con el lock adquirido.

El bug actual: time.sleep() se llama DENTRO del bloque `with self._db_lock:`,
lo que bloquea todos los demás hilos durante el backoff completo.

Fix requerido:
  - time.sleep() debe estar FUERA del bloque `with self._db_lock:`.
  - _get_conn() debe usar timeout=5 para que SQLite espere antes de fallar.
  - Alternativa: PRAGMA busy_timeout=5000 en cada conexión nueva.

RED state: falla porque el código actual ejecuta sleep DENTRO del lock.
"""
import inspect
import threading
import time
import pytest
from data_vault.base_repo import BaseRepository


class TestDbLockNoSleepInLock:
    def test_sleep_is_not_called_while_lock_is_held(self):
        """
        Verifica estructuralmente que time.sleep no se invoca dentro del
        contexto del lock en _execute_serialized.

        Estrategia: adquirir el lock desde otro hilo DURANTE el sleep del retry;
        si sleep ocurre dentro del lock, el hilo externo NO puede adquirirlo
        mientras dura el sleep. Si está fuera, sí puede.
        """
        repo = BaseRepository(db_path=":memory:")

        call_order = []
        lock_acquired_during_sleep = threading.Event()
        sleep_started = threading.Event()

        original_sleep = time.sleep

        def patched_sleep(duration):
            sleep_started.set()
            # Intenta adquirir el lock desde este contexto (dentro del sleep)
            # Si el lock YA está liberado, lo obtenemos inmediatamente
            acquired = BaseRepository._db_lock.acquire(blocking=False)
            if acquired:
                call_order.append("lock_acquired_outside_sleep")
                BaseRepository._db_lock.release()
            else:
                call_order.append("lock_still_held_during_sleep")
            original_sleep(duration)

        import unittest.mock as mock
        with mock.patch("data_vault.base_repo.time.sleep", side_effect=patched_sleep):
            def failing_func(conn):
                raise Exception("database is locked")

            try:
                repo._execute_serialized(failing_func, retries=2, backoff=0.01)
            except Exception:
                pass

        assert "lock_still_held_during_sleep" not in call_order, (
            "time.sleep() se llamó DENTRO del lock — esto provoca deadlock. "
            "Mueve el sleep FUERA del bloque `with self._db_lock:`."
        )

    def test_get_conn_uses_timeout_or_busy_pragma(self):
        """
        _get_conn() debe configurar sqlite3 con timeout>0 O ejecutar
        PRAGMA busy_timeout para evitar fallo inmediato en contención.
        """
        source = inspect.getsource(BaseRepository._get_conn)
        has_timeout_param = "timeout=" in source
        has_busy_pragma = "busy_timeout" in source
        assert has_timeout_param or has_busy_pragma, (
            "_get_conn() debe usar sqlite3.connect(..., timeout=N) "
            "o ejecutar PRAGMA busy_timeout=N para evitar fallo inmediato en contención."
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
