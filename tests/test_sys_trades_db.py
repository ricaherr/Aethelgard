"""
test_sys_trades_db.py — Integration tests for sys_trades persistence layer.

Tests:
  1. save_sys_trade() writes to sys_trades, NOT usr_trades
  2. get_sys_trades() returns only sys_trades records
  3. SHADOW trades routed to sys_trades
  4. LIVE trades still routed to usr_trades (no regression)
  5. ShadowManager can read metrics from sys_trades

Naming convention: test_<componente>_<comportamiento>
"""
import pytest
import sqlite3
import uuid
from datetime import datetime, timezone

from data_vault.schema import initialize_schema


@pytest.fixture
def db():
    """In-memory SQLite database with full Aethelgard schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    yield conn
    conn.close()


def _make_trade(execution_mode: str, **kwargs) -> dict:
    """Helper to build a minimal trade dict."""
    base = {
        "id": str(uuid.uuid4()),
        "symbol": "EURUSD",
        "execution_mode": execution_mode,
        "entry_price": 1.1000,
        "exit_price": 1.1050,
        "profit": 50.0,
        "exit_reason": "TP",
        "close_time": datetime.now(timezone.utc).isoformat(),
        "instance_id": "INST_001",
        "account_id": None,
        "signal_id": None,
        "strategy_id": "BRK_OPEN_0001",
        "order_id": None,
        "direction": "BUY",
        "open_time": None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Helpers — raw INSERT wrappers (bypass application layer for direct DB tests)
# ---------------------------------------------------------------------------

def _insert_sys_trade(conn: sqlite3.Connection, trade: dict) -> None:
    """Direct INSERT into sys_trades (for schema-level tests)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sys_trades (
            id, signal_id, instance_id, account_id, symbol, direction,
            entry_price, exit_price, profit, exit_reason,
            open_time, close_time, execution_mode, strategy_id, order_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade["id"], trade.get("signal_id"), trade.get("instance_id"),
            trade.get("account_id"), trade["symbol"], trade.get("direction"),
            trade.get("entry_price"), trade.get("exit_price"),
            trade.get("profit"), trade.get("exit_reason"),
            trade.get("open_time"), trade.get("close_time"),
            trade["execution_mode"], trade.get("strategy_id"), trade.get("order_id"),
        ),
    )
    conn.commit()


def _insert_usr_trade(conn: sqlite3.Connection, trade: dict) -> None:
    """Direct INSERT into usr_trades (for regression tests)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO usr_trades (
            id, signal_id, symbol, entry_price, exit_price,
            profit, exit_reason, close_time, execution_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade["id"], trade.get("signal_id"), trade["symbol"],
            trade.get("entry_price"), trade.get("exit_price"),
            trade.get("profit"), trade.get("exit_reason"),
            trade.get("close_time"), trade["execution_mode"],
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# save_sys_trade() tests (application-layer function)
# ---------------------------------------------------------------------------

class TestSaveSysTrade:
    """Tests for save_sys_trade() routing to sys_trades, not usr_trades."""

    def test_save_sys_trade_writes_to_sys_trades_not_usr_trades(self, db):
        """save_sys_trade() must write to sys_trades and leave usr_trades empty."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        trade = _make_trade("SHADOW")
        repo.save_sys_trade(trade)

        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM sys_trades")
        assert cursor.fetchone()[0] == 1, "sys_trades should have 1 row"

        cursor.execute("SELECT COUNT(*) FROM usr_trades")
        assert cursor.fetchone()[0] == 0, "usr_trades should have 0 rows"

    def test_save_sys_trade_shadow_mode(self, db):
        """save_sys_trade() with SHADOW mode stores all columns correctly."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        trade = _make_trade(
            "SHADOW",
            instance_id="INST_SHADOW_001",
            account_id="ACC_DEMO_001",
            profit=75.5,
            symbol="GBPUSD",
        )
        repo.save_sys_trade(trade)

        cursor = db.cursor()
        cursor.execute("SELECT * FROM sys_trades WHERE id = ?", (trade["id"],))
        row = cursor.fetchone()
        assert row is not None, "Trade not found in sys_trades"
        assert row["execution_mode"] == "SHADOW"
        assert row["instance_id"] == "INST_SHADOW_001"
        assert row["account_id"] == "ACC_DEMO_001"
        assert row["profit"] == 75.5
        assert row["symbol"] == "GBPUSD"

    def test_save_sys_trade_backtest_mode(self, db):
        """save_sys_trade() with BACKTEST mode persists strategy_id correctly."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        trade = _make_trade("BACKTEST", strategy_id="STRAT_BKT_XYZ", profit=-30.0)
        repo.save_sys_trade(trade)

        cursor = db.cursor()
        cursor.execute("SELECT * FROM sys_trades WHERE id = ?", (trade["id"],))
        row = cursor.fetchone()
        assert row is not None
        assert row["execution_mode"] == "BACKTEST"
        assert row["strategy_id"] == "STRAT_BKT_XYZ"

    def test_save_trade_result_live_still_goes_to_usr_trades(self, db):
        """save_trade_result() with LIVE mode must write to usr_trades (regression guard)."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        trade = _make_trade("LIVE")
        repo.save_trade_result(trade)

        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM usr_trades")
        assert cursor.fetchone()[0] == 1, "usr_trades should have 1 row for LIVE trade"

        cursor.execute("SELECT COUNT(*) FROM sys_trades")
        assert cursor.fetchone()[0] == 0, "sys_trades should have 0 rows for LIVE trade"

    def test_sys_trades_rejects_live_mode_at_app_layer(self, db):
        """save_sys_trade() must raise ValueError if execution_mode='LIVE'."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        trade = _make_trade("LIVE")
        with pytest.raises(ValueError, match="LIVE"):
            repo.save_sys_trade(trade)

    def test_sys_trades_rejects_live_mode_at_db_layer(self, db):
        """Direct INSERT with execution_mode='LIVE' into sys_trades must raise IntegrityError."""
        with pytest.raises(sqlite3.IntegrityError):
            _insert_sys_trade(db, _make_trade("LIVE"))


# ---------------------------------------------------------------------------
# get_sys_trades() tests
# ---------------------------------------------------------------------------

class TestGetSysTrades:
    """Tests for get_sys_trades() query with filters."""

    def test_get_sys_trades_returns_shadow_trades(self, db):
        """get_sys_trades(execution_mode='SHADOW') returns only SHADOW records."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        for i in range(2):
            repo.save_sys_trade(_make_trade("SHADOW", id=f"shadow-{i}"))
        repo.save_sys_trade(_make_trade("BACKTEST", id="backtest-0"))

        results = repo.get_sys_trades(execution_mode="SHADOW")
        assert len(results) == 2
        assert all(r["execution_mode"] == "SHADOW" for r in results)

    def test_get_sys_trades_by_instance_id(self, db):
        """get_sys_trades(instance_id=...) returns only matching instance's trades."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        repo.save_sys_trade(_make_trade("SHADOW", id="t1", instance_id="INST_A"))
        repo.save_sys_trade(_make_trade("SHADOW", id="t2", instance_id="INST_A"))
        repo.save_sys_trade(_make_trade("SHADOW", id="t3", instance_id="INST_B"))

        results = repo.get_sys_trades(instance_id="INST_A")
        assert len(results) == 2
        assert all(r["instance_id"] == "INST_A" for r in results)

    def test_get_sys_trades_win_rate_calculation(self, db):
        """Win rate from sys_trades: 2 profits + 1 loss → win_rate ≈ 0.667."""
        from data_vault.trades_db import TradesMixin

        class _Repo(TradesMixin):
            def _get_conn(self):
                return db
            def _close_conn(self, conn):
                pass

        repo = _Repo()
        repo.save_sys_trade(_make_trade("SHADOW", id="w1", profit=100.0))
        repo.save_sys_trade(_make_trade("SHADOW", id="w2", profit=50.0))
        repo.save_sys_trade(_make_trade("SHADOW", id="l1", profit=-30.0))

        trades = repo.get_sys_trades(execution_mode="SHADOW")
        total = len(trades)
        wins = sum(1 for t in trades if t["profit"] > 0)
        win_rate = wins / total if total > 0 else 0.0
        assert abs(win_rate - 2 / 3) < 0.01, f"Expected ~0.667 win rate, got {win_rate}"


# ---------------------------------------------------------------------------
# ShadowStorageManager.calculate_instance_metrics_from_sys_trades() tests
# ---------------------------------------------------------------------------

class TestShadowManagerMetrics:
    """Tests for calculate_instance_metrics_from_sys_trades() in ShadowStorageManager."""

    def test_calculate_instance_metrics_from_sys_trades(self, db):
        """Seed known trades → verify total_trades, win_rate, profit_factor."""
        from data_vault.shadow_db import ShadowStorageManager

        manager = ShadowStorageManager(db)

        # Seed: 2 wins (100, 50), 1 loss (-30)
        for t in [
            _make_trade("SHADOW", id="m1", instance_id="INST_001", profit=100.0),
            _make_trade("SHADOW", id="m2", instance_id="INST_001", profit=50.0),
            _make_trade("SHADOW", id="m3", instance_id="INST_001", profit=-30.0),
        ]:
            _insert_sys_trade(db, t)

        metrics = manager.calculate_instance_metrics_from_sys_trades("INST_001")

        assert metrics.total_trades_executed == 3
        assert abs(metrics.win_rate - 2 / 3) < 0.01, f"win_rate={metrics.win_rate}"
        # profit_factor = sum(wins) / sum(losses) = 150 / 30 = 5.0
        assert abs(metrics.profit_factor - 5.0) < 0.01, f"profit_factor={metrics.profit_factor}"

    def test_instance_with_no_trades_returns_zero_metrics(self, db):
        """Instance with no trades → ShadowMetrics with all-zero values."""
        from data_vault.shadow_db import ShadowStorageManager

        manager = ShadowStorageManager(db)
        metrics = manager.calculate_instance_metrics_from_sys_trades("INST_NO_TRADES")

        assert metrics.total_trades_executed == 0
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0.0

    def test_calculate_metrics_consecutive_losses(self, db):
        """Verify consecutive_losses_max is counted correctly."""
        from data_vault.shadow_db import ShadowStorageManager

        manager = ShadowStorageManager(db)

        trades = [
            _make_trade("SHADOW", id="c1", instance_id="INST_CL", profit=10.0),
            _make_trade("SHADOW", id="c2", instance_id="INST_CL", profit=-5.0),
            _make_trade("SHADOW", id="c3", instance_id="INST_CL", profit=-5.0),
            _make_trade("SHADOW", id="c4", instance_id="INST_CL", profit=-5.0),
            _make_trade("SHADOW", id="c5", instance_id="INST_CL", profit=15.0),
        ]
        for t in trades:
            _insert_sys_trade(db, t)

        metrics = manager.calculate_instance_metrics_from_sys_trades("INST_CL")
        assert metrics.consecutive_losses_max == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
