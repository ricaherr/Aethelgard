"""
Test Suite: N2-1 JSON_SCHEMA Interpreter

Tests for:
1. SafeConditionEvaluator — OWASP A03 compliant, no eval()
2. DB migration — type + logic columns (ALTER TABLE, never recreate)
3. UniversalStrategyEngine.execute_from_registry() with JSON_SCHEMA strategies
4. _calculate_indicators() receives schema as parameter
5. StrategyEngineFactory._instantiate_json_schema_strategy() passes spec to engine

Trace_ID: JSON-SCHEMA-INTERP-N2-1-2026
"""
import json
import sqlite3
import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch


# ============================================================================
# Imports under test
# ============================================================================
from core_brain.universal_strategy_engine import (
    SafeConditionEvaluator,
    UniversalStrategyEngine,
    ExecutionMode,
)
from core_brain.services.strategy_engine_factory import StrategyEngineFactory


# ============================================================================
# Group 1: SafeConditionEvaluator — security + correctness
# ============================================================================

class TestSafeConditionEvaluator:
    """Tests for the injection-safe condition evaluator."""

    def test_rsi_less_than_passes(self):
        """RSI=25 satisfies 'RSI < 30'."""
        result = SafeConditionEvaluator.evaluate("RSI < 30", {"RSI": 25.0})
        assert result is True

    def test_rsi_greater_than_fails(self):
        """RSI=35 does NOT satisfy 'RSI < 30'."""
        result = SafeConditionEvaluator.evaluate("RSI < 30", {"RSI": 35.0})
        assert result is False

    def test_greater_than_equal_operator(self):
        """RSI=70 satisfies 'RSI >= 70'."""
        result = SafeConditionEvaluator.evaluate("RSI >= 70", {"RSI": 70.0})
        assert result is True

    def test_combined_and_condition_true(self):
        """Both sub-conditions true → True."""
        result = SafeConditionEvaluator.evaluate(
            "RSI < 30 and MACD > 0", {"RSI": 25.0, "MACD": 0.1}
        )
        assert result is True

    def test_combined_and_condition_partial_false(self):
        """One sub-condition false → False (AND semantics)."""
        result = SafeConditionEvaluator.evaluate(
            "RSI < 30 and MACD > 0", {"RSI": 25.0, "MACD": -0.1}
        )
        assert result is False

    def test_or_condition_one_true(self):
        """One sub-condition true → True (OR semantics)."""
        result = SafeConditionEvaluator.evaluate(
            "RSI > 70 or MACD > 0", {"RSI": 25.0, "MACD": 0.1}
        )
        assert result is True

    def test_or_condition_both_false(self):
        """Both sub-conditions false → False (OR semantics)."""
        result = SafeConditionEvaluator.evaluate(
            "RSI > 70 or MACD > 0", {"RSI": 25.0, "MACD": -0.1}
        )
        assert result is False

    def test_injection_attempt_returns_false(self):
        """Arbitrary Python code must NOT execute — fail-safe returns False."""
        result = SafeConditionEvaluator.evaluate(
            "__import__('os').system('echo pwned')", {"RSI": 25.0}
        )
        assert result is False

    def test_unknown_indicator_returns_false(self):
        """Condition references indicator not in the provided dict → False."""
        result = SafeConditionEvaluator.evaluate("UNKNOWN_IND > 10", {"RSI": 25.0})
        assert result is False

    def test_empty_condition_returns_false(self):
        """Empty string condition → False (fail-safe)."""
        result = SafeConditionEvaluator.evaluate("", {"RSI": 25.0})
        assert result is False

    def test_none_condition_returns_false(self):
        """None condition → False (fail-safe)."""
        result = SafeConditionEvaluator.evaluate(None, {"RSI": 25.0})
        assert result is False

    def test_none_indicator_value_returns_false(self):
        """Indicator value is None → safe False, no exception."""
        result = SafeConditionEvaluator.evaluate("RSI < 30", {"RSI": None})
        assert result is False

    def test_equality_operator(self):
        """Equality check works correctly."""
        result = SafeConditionEvaluator.evaluate("SIGNAL == 1", {"SIGNAL": 1.0})
        assert result is True

    def test_not_equal_operator(self):
        """Inequality check works correctly."""
        result = SafeConditionEvaluator.evaluate("SIGNAL != 0", {"SIGNAL": 1.0})
        assert result is True


# ============================================================================
# Group 2: DB migration — type + logic columns
# ============================================================================

class TestDbMigration:
    """Tests that migration adds columns without recreating the table."""

    def _create_db_without_new_cols(self) -> sqlite3.Connection:
        """Create an in-memory DB with sys_strategies lacking type/logic columns."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE sys_strategies (
                class_id TEXT PRIMARY KEY,
                mnemonic TEXT NOT NULL,
                version TEXT DEFAULT '1.0',
                affinity_scores TEXT DEFAULT '{}',
                market_whitelist TEXT DEFAULT '[]',
                description TEXT,
                readiness TEXT DEFAULT 'UNKNOWN',
                readiness_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return conn

    def test_migration_adds_type_column(self):
        """ALTER TABLE adds 'type' column when missing."""
        conn = self._create_db_without_new_cols()
        cursor = conn.cursor()

        # Run migration logic (mirrors schema.py apply_migrations)
        cursor.execute("PRAGMA table_info(sys_strategies)")
        cols = [r[1] for r in cursor.fetchall()]
        if "type" not in cols:
            cursor.execute(
                "ALTER TABLE sys_strategies ADD COLUMN type TEXT DEFAULT 'PYTHON_CLASS'"
            )
        conn.commit()

        # Verify column exists
        cursor.execute("PRAGMA table_info(sys_strategies)")
        col_names = [r[1] for r in cursor.fetchall()]
        assert "type" in col_names

    def test_migration_adds_logic_column(self):
        """ALTER TABLE adds 'logic' column when missing."""
        conn = self._create_db_without_new_cols()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(sys_strategies)")
        cols = [r[1] for r in cursor.fetchall()]
        if "logic" not in cols:
            cursor.execute(
                "ALTER TABLE sys_strategies ADD COLUMN logic TEXT DEFAULT NULL"
            )
        conn.commit()

        cursor.execute("PRAGMA table_info(sys_strategies)")
        col_names = [r[1] for r in cursor.fetchall()]
        assert "logic" in col_names

    def test_migration_is_idempotent(self):
        """Running migration twice does not raise errors."""
        conn = self._create_db_without_new_cols()
        cursor = conn.cursor()

        def run_migration():
            cursor.execute("PRAGMA table_info(sys_strategies)")
            cols = [r[1] for r in cursor.fetchall()]
            if "type" not in cols:
                cursor.execute(
                    "ALTER TABLE sys_strategies ADD COLUMN type TEXT DEFAULT 'PYTHON_CLASS'"
                )
            if "logic" not in cols:
                cursor.execute(
                    "ALTER TABLE sys_strategies ADD COLUMN logic TEXT DEFAULT NULL"
                )
            conn.commit()

        run_migration()
        # Second run must not raise
        run_migration()

        cursor.execute("PRAGMA table_info(sys_strategies)")
        col_names = [r[1] for r in cursor.fetchall()]
        assert "type" in col_names
        assert "logic" in col_names

    def test_logic_column_stores_and_retrieves_json(self):
        """logic column can store JSON and be retrieved as dict."""
        conn = self._create_db_without_new_cols()
        cursor = conn.cursor()

        cursor.execute(
            "ALTER TABLE sys_strategies ADD COLUMN type TEXT DEFAULT 'PYTHON_CLASS'"
        )
        cursor.execute(
            "ALTER TABLE sys_strategies ADD COLUMN logic TEXT DEFAULT NULL"
        )

        logic_spec = {
            "strategy_id": "TEST_001",
            "indicators": {"RSI": {"type": "RSI", "period": 14}},
            "entry_logic": {"condition": "RSI < 30", "direction": "BUY", "confidence": 0.8},
        }
        cursor.execute(
            "INSERT INTO sys_strategies (class_id, mnemonic, type, logic) VALUES (?, ?, ?, ?)",
            ("TEST_001", "TEST_MNEMONIC", "JSON_SCHEMA", json.dumps(logic_spec)),
        )
        conn.commit()

        cursor.execute("SELECT logic FROM sys_strategies WHERE class_id = ?", ("TEST_001",))
        row = cursor.fetchone()
        retrieved = json.loads(row[0])
        assert retrieved["entry_logic"]["condition"] == "RSI < 30"
        assert retrieved["indicators"]["RSI"]["period"] == 14


# ============================================================================
# Group 3: UniversalStrategyEngine.execute_from_registry() with JSON_SCHEMA
# ============================================================================

def _make_mock_storage(strategy_meta: Dict[str, Any]) -> MagicMock:
    """Helper: mock StorageManager that returns given strategy metadata."""
    mock = MagicMock()
    mock.get_strategy.return_value = strategy_meta
    mock.get_all_sys_strategies.return_value = [strategy_meta]
    return mock


def _make_mock_indicator_provider(rsi_value: float = 25.0) -> MagicMock:
    """Helper: mock indicator provider with calculate_rsi method."""
    mock = MagicMock()
    mock.calculate_rsi = MagicMock(return_value=rsi_value)
    return mock


@pytest.mark.asyncio
async def test_json_schema_buy_signal_generated():
    """JSON_SCHEMA strategy with satisfied BUY condition emits signal='BUY'."""
    logic_spec = {
        "strategy_id": "BRK_TEST_001",
        "version": "1.0",
        "indicators": {"RSI": {"type": "RSI", "period": 14}},
        "entry_logic": {"condition": "RSI < 30", "direction": "BUY", "confidence": 0.8},
    }
    strategy_meta = {
        "class_id": "BRK_TEST_001",
        "strategy_id": "BRK_TEST_001",
        "mnemonic": "TEST",
        "type": "JSON_SCHEMA",
        "readiness": "READY_FOR_ENGINE",
        "logic": logic_spec,
    }

    mock_storage = _make_mock_storage(strategy_meta)
    mock_provider = _make_mock_indicator_provider(rsi_value=25.0)  # RSI < 30 → BUY

    engine = UniversalStrategyEngine(
        indicator_provider=mock_provider,
        storage=mock_storage,
    )

    result = await engine.execute_from_registry("BRK_TEST_001", "EURUSD", MagicMock())

    assert result.execution_mode == ExecutionMode.SIGNAL_GENERATED
    assert result.signal == "BUY"


@pytest.mark.asyncio
async def test_json_schema_no_signal_when_condition_not_met():
    """JSON_SCHEMA strategy with unsatisfied condition emits signal=None."""
    logic_spec = {
        "strategy_id": "BRK_TEST_002",
        "version": "1.0",
        "indicators": {"RSI": {"type": "RSI", "period": 14}},
        "entry_logic": {"condition": "RSI < 30", "direction": "BUY", "confidence": 0.8},
    }
    strategy_meta = {
        "class_id": "BRK_TEST_002",
        "strategy_id": "BRK_TEST_002",
        "mnemonic": "TEST2",
        "type": "JSON_SCHEMA",
        "readiness": "READY_FOR_ENGINE",
        "logic": logic_spec,
    }

    mock_storage = _make_mock_storage(strategy_meta)
    mock_provider = _make_mock_indicator_provider(rsi_value=55.0)  # RSI=55, NOT < 30

    engine = UniversalStrategyEngine(
        indicator_provider=mock_provider,
        storage=mock_storage,
    )

    result = await engine.execute_from_registry("BRK_TEST_002", "EURUSD", MagicMock())

    assert result.execution_mode == ExecutionMode.NO_SIGNAL
    assert result.signal is None


@pytest.mark.asyncio
async def test_logic_pending_strategy_blocked():
    """LOGIC_PENDING strategy returns READINESS_BLOCKED, never executes logic."""
    strategy_meta = {
        "class_id": "BLOCKED_001",
        "strategy_id": "BLOCKED_001",
        "mnemonic": "BLOCKED",
        "type": "JSON_SCHEMA",
        "readiness": "LOGIC_PENDING",
        "logic": None,
    }

    mock_storage = _make_mock_storage(strategy_meta)
    engine = UniversalStrategyEngine(
        indicator_provider=MagicMock(),
        storage=mock_storage,
    )

    result = await engine.execute_from_registry("BLOCKED_001", "EURUSD", MagicMock())

    assert result.execution_mode == ExecutionMode.READINESS_BLOCKED


@pytest.mark.asyncio
async def test_missing_logic_returns_crash_veto_not_exception():
    """Strategy with logic=None returns CRASH_VETO gracefully (no unhandled exception)."""
    strategy_meta = {
        "class_id": "NO_LOGIC_001",
        "strategy_id": "NO_LOGIC_001",
        "mnemonic": "NO_LOGIC",
        "type": "JSON_SCHEMA",
        "readiness": "READY_FOR_ENGINE",
        "logic": None,
    }

    mock_storage = _make_mock_storage(strategy_meta)
    engine = UniversalStrategyEngine(
        indicator_provider=MagicMock(),
        storage=mock_storage,
    )

    # Must not raise
    result = await engine.execute_from_registry("NO_LOGIC_001", "EURUSD", MagicMock())

    assert result.execution_mode == ExecutionMode.CRASH_VETO


# ============================================================================
# Group 4: _calculate_indicators receives schema as parameter
# ============================================================================

@pytest.mark.asyncio
async def test_indicators_calculated_from_schema_param():
    """_calculate_indicators uses indicators from the schema passed to it."""
    mock_provider = MagicMock()
    mock_provider.calculate_rsi = MagicMock(return_value=28.5)

    mock_storage = MagicMock()
    engine = UniversalStrategyEngine(
        indicator_provider=mock_provider,
        storage=mock_storage,
    )

    schema = {
        "strategy_id": "TEST",
        "indicators": {"RSI": {"type": "RSI", "period": 14}},
    }
    df_mock = MagicMock()

    results = await engine._calculate_indicators(df_mock, schema)

    assert "RSI" in results
    assert results["RSI"] == 28.5
    mock_provider.calculate_rsi.assert_called_once()


@pytest.mark.asyncio
async def test_empty_indicators_returns_empty_dict():
    """Schema with no indicators → empty dict returned without error."""
    mock_storage = MagicMock()
    engine = UniversalStrategyEngine(
        indicator_provider=MagicMock(),
        storage=mock_storage,
    )

    results = await engine._calculate_indicators(MagicMock(), {"strategy_id": "X", "indicators": {}})
    assert results == {}


# ============================================================================
# Group 5: StrategyEngineFactory passes spec to engine
# ============================================================================

def test_json_schema_factory_pre_loads_schema_in_engine():
    """Factory stores logic spec in engine._schema_cache so no extra DB round-trip."""
    logic_spec = {
        "strategy_id": "BRK_OPEN_0001",
        "indicators": {"RSI": {"type": "RSI", "period": 14}},
        "entry_logic": {"condition": "RSI < 30", "direction": "BUY", "confidence": 0.8},
    }
    strategy_spec = {
        "class_id": "BRK_OPEN_0001",
        "type": "JSON_SCHEMA",
        "readiness": "READY_FOR_ENGINE",
        "logic": logic_spec,
    }

    mock_storage = MagicMock()
    mock_storage.ensure_signal_ranking_for_strategy.return_value = {"execution_mode": "SHADOW"}

    with (
        patch("core_brain.universal_strategy_engine.UniversalStrategyEngine") as MockEngine,
        patch("core_brain.tech_utils.TechnicalAnalyzer"),
    ):
        mock_instance = MagicMock()
        mock_instance._schema_cache = {}
        MockEngine.return_value = mock_instance

        factory = StrategyEngineFactory(storage=mock_storage, config={})
        factory._instantiate_json_schema_strategy(strategy_spec)

        # Schema must be pre-loaded in engine cache
        assert "BRK_OPEN_0001" in mock_instance._schema_cache
        cached = mock_instance._schema_cache["BRK_OPEN_0001"]
        assert cached["entry_logic"]["condition"] == "RSI < 30"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
