"""
TDD: MT5 Single-Thread Executor
================================
Validates that ALL mt5.* DLL calls are serialized through a single dedicated
executor thread, eliminating COM-apartment race conditions.

Race conditions being fixed (N1-1):
  - MT5-Background-Connector thread
  - _schedule_retry() threading.Timer thread
  - FastAPI / asyncio caller thread
"""
import queue
import threading
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import Future

from connectors.mt5_connector import MT5Connector, _MT5Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_connector(mock_mt5=None) -> MT5Connector:
    """Create MT5Connector with mocked DB (no real storage needed)."""
    with patch("connectors.mt5_connector.StorageManager") as mock_storage_cls:
        mock_storage = Mock()
        mock_storage.get_sys_broker_accounts.return_value = []
        mock_storage_cls.return_value = mock_storage
        # patch mt5 module so __init__ doesn't fail on MT5_AVAILABLE check
        with patch("connectors.mt5_connector.MT5_AVAILABLE", True):
            connector = MT5Connector()
    return connector


# ---------------------------------------------------------------------------
# _MT5Task dataclass
# ---------------------------------------------------------------------------

class TestMT5TaskDataclass:
    """_MT5Task bundles a callable + future for the executor queue."""

    def test_mt5_task_holds_fn_args_kwargs_and_future(self):
        fn = lambda x, y=1: x + y
        task = _MT5Task(fn=fn, args=(10,), kwargs={"y": 5}, future=Future())
        assert task.fn is fn
        assert task.args == (10,)
        assert task.kwargs == {"y": 5}
        assert isinstance(task.future, Future)

    def test_mt5_task_default_future_is_new_instance(self):
        fn = lambda: None
        t1 = _MT5Task(fn=fn, args=(), kwargs={})
        t2 = _MT5Task(fn=fn, args=(), kwargs={})
        assert t1.future is not t2.future


# ---------------------------------------------------------------------------
# Executor thread lifecycle
# ---------------------------------------------------------------------------

class TestDLLExecutorThread:
    """The connector must spawn and maintain a dedicated DLL executor thread."""

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_executor_thread_is_created_on_init(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        assert hasattr(connector, "_dll_executor_thread"), (
            "MT5Connector must have _dll_executor_thread attribute"
        )
        assert isinstance(connector._dll_executor_thread, threading.Thread)

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_executor_thread_is_alive_after_init(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        assert connector._dll_executor_thread.is_alive(), (
            "DLL executor thread must be alive immediately after __init__"
        )

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_executor_thread_is_named_correctly(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        assert connector._dll_executor_thread.name == "MT5-DLL-Executor"

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_executor_thread_is_daemon(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        assert connector._dll_executor_thread.daemon is True, (
            "Executor thread must be daemon so it doesn't block shutdown"
        )

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_connector_has_dll_queue(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        assert hasattr(connector, "_dll_queue"), (
            "MT5Connector must have _dll_queue attribute"
        )
        assert isinstance(connector._dll_queue, queue.Queue)


# ---------------------------------------------------------------------------
# _submit_to_executor
# ---------------------------------------------------------------------------

class TestSubmitToExecutor:
    """_submit_to_executor must dispatch the callable to the executor thread."""

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_to_executor_returns_function_result(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        result = connector._submit_to_executor(lambda: 42)
        assert result == 42

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_to_executor_passes_args_and_kwargs(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        result = connector._submit_to_executor(lambda x, y=0: x + y, 10, y=5)
        assert result == 15

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_to_executor_runs_in_executor_thread(self, mock_storage_cls):
        """The callable must execute in the MT5-DLL-Executor thread, not the caller's."""
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        caller_thread = threading.current_thread()
        executed_in = []

        def capture_thread():
            executed_in.append(threading.current_thread().name)

        connector._submit_to_executor(capture_thread)
        assert len(executed_in) == 1
        assert executed_in[0] == "MT5-DLL-Executor", (
            f"DLL call should run in MT5-DLL-Executor, not in {executed_in[0]}"
        )

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_to_executor_propagates_exceptions(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        def boom():
            raise ValueError("DLL error")

        with pytest.raises(ValueError, match="DLL error"):
            connector._submit_to_executor(boom)

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_concurrent_submits_are_serialized(self, mock_storage_cls):
        """Multiple concurrent callers must not execute simultaneously in executor."""
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        concurrent_count = []
        max_concurrent = [0]
        lock = threading.Lock()

        def check_no_concurrent():
            with lock:
                concurrent_count.append(1)
                max_concurrent[0] = max(max_concurrent[0], len(concurrent_count))
            time.sleep(0.01)  # Simulate DLL work
            with lock:
                concurrent_count.pop()

        threads = [
            threading.Thread(
                target=connector._submit_to_executor, args=(check_no_concurrent,)
            )
            for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_concurrent[0] == 1, (
            f"DLL calls must be serialized. Max concurrent was {max_concurrent[0]}"
        )


# ---------------------------------------------------------------------------
# _submit_async
# ---------------------------------------------------------------------------

class TestSubmitAsync:
    """_submit_async is the awaitable variant of _submit_to_executor."""

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_async_exists(self, mock_storage_cls):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        assert hasattr(connector, "_submit_async"), (
            "MT5Connector must expose _submit_async coroutine method"
        )
        import asyncio, inspect
        assert inspect.iscoroutinefunction(connector._submit_async), (
            "_submit_async must be a coroutine function (async def)"
        )

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_async_returns_result(self, mock_storage_cls):
        import asyncio
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        async def run():
            return await connector._submit_async(lambda: 99)

        result = asyncio.run(run())
        assert result == 99

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_submit_async_runs_in_executor_thread(self, mock_storage_cls):
        import asyncio
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        executed_in = []

        async def run():
            await connector._submit_async(
                lambda: executed_in.append(threading.current_thread().name)
            )

        asyncio.run(run())
        assert executed_in[0] == "MT5-DLL-Executor"


# ---------------------------------------------------------------------------
# _schedule_retry no longer spawns raw DLL threads
# ---------------------------------------------------------------------------

class TestScheduleRetryUsesExecutor:
    """_schedule_retry must not create threads that call mt5.* directly."""

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_schedule_retry_does_not_start_new_mt5_threads(self, mock_storage_cls):
        """After _schedule_retry(), no extra threads named 'MT5-Connector' must exist."""
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        before = {t.name for t in threading.enumerate()}
        connector._schedule_retry()
        time.sleep(0.05)  # Give any created thread time to start

        after = {t.name for t in threading.enumerate()}
        new_threads = after - before - {"MT5-DLL-Executor"}  # executor is expected

        # Should not spawn a thread named "MT5-Connector" or "MT5-Background-Connector"
        dll_caller_threads = {
            name for name in new_threads
            if name.startswith("MT5-") and name != "MT5-DLL-Executor"
        }
        assert "MT5-Connector" not in dll_caller_threads, (
            "_schedule_retry must not spawn MT5-Connector thread (bypasses executor)"
        )

    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_schedule_retry_cancels_previous_timer(self, mock_storage_cls):
        """Calling _schedule_retry twice must cancel the first timer, not stack them."""
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()

        connector._schedule_retry()
        first_timer = connector.retry_timer

        connector._schedule_retry()
        second_timer = connector.retry_timer

        assert first_timer is not second_timer, "Second call must replace the timer"


# ---------------------------------------------------------------------------
# connect_blocking routes through executor
# ---------------------------------------------------------------------------

class TestConnectBlockingUsesExecutor:
    """connect_blocking() must dispatch MT5 init/login to the executor thread."""

    @patch("connectors.mt5_connector.mt5")
    @patch("connectors.mt5_connector.MT5_AVAILABLE", True)
    @patch("connectors.mt5_connector.StorageManager")
    def test_connect_blocking_routes_through_executor(self, mock_storage_cls, mock_mt5):
        mock_storage_cls.return_value.get_sys_broker_accounts.return_value = []
        connector = MT5Connector()
        connector.config = {
            "enabled": True,
            "login": 12345,
            "password": "pass",
            "server": "ICMarkets-Demo",
        }

        executed_threads = []

        original_connect_once = connector._connect_sync_once
        def spy_connect():
            executed_threads.append(threading.current_thread().name)
            return False  # Don't let it actually connect

        connector._connect_sync_once = spy_connect

        connector.connect_blocking()

        assert len(executed_threads) == 1
        assert executed_threads[0] == "MT5-DLL-Executor", (
            f"connect_blocking must use executor thread, got: {executed_threads[0]}"
        )
