import pytest
import asyncio
import tempfile
from core_brain.signal_factory import SignalFactory
from core_brain.strategies.base_strategy import BaseStrategy
## No importar clases con anotaciones de tipo no resueltas para evitar NameError
from data_vault.storage import StorageManager


class DummyStrategy(BaseStrategy):
    strategy_id = "dummy"
    def __init__(self, config=None):
        super().__init__(config or {})
    async def analyze(self, symbol, df, regime):
        from models.signal import Signal, ConnectorType
        return Signal(
            symbol=symbol,
            signal_type="BUY",
            entry_price=1.0,
            stop_loss=0.9,
            take_profit=1.1,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            strategy="dummy",
            created_at="2024-01-01T00:00:00Z"
        )

def make_scan_results():
    return {
        "EURUSD|M5": {
            "regime": "TREND",
            "df": object(),
            "symbol": "EURUSD",
            "timeframe": "M5"
        },
        "USDJPY|M5": {
            "regime": "RANGE",
            "df": object(),
            "symbol": "USDJPY",
            "timeframe": "M5"
        }
    }

@pytest.mark.asyncio
async def test_generate_signals_batch_creates_tasks():
    # Usar StorageManager con base de datos en memoria
    storage = StorageManager(db_path=':memory:')
    from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
    from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
    confluence = MultiTimeframeConfluenceAnalyzer(storage=storage, enabled=False)
    trifecta = TrifectaAnalyzer(storage=storage, config_data={"enabled": False})
    factory = SignalFactory(
        storage_manager=storage,
        strategies=[DummyStrategy({})],
        confluence_analyzer=confluence,
        trifecta_analyzer=trifecta,
        mt5_connector=None
    )
    scan_results = make_scan_results()
    signals = await factory.generate_signals_batch(scan_results)
    assert len(signals) == 2
    assert all(hasattr(s, 'symbol') for s in signals)

@pytest.mark.asyncio
async def test_generate_signals_batch_no_tasks_logs_warning(caplog):
    storage = StorageManager(db_path=':memory:')
    from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
    from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
    confluence = MultiTimeframeConfluenceAnalyzer(storage=storage, enabled=False)
    trifecta = TrifectaAnalyzer(storage=storage, config_data={"enabled": False})
    factory = SignalFactory(
        storage_manager=storage,
        strategies=[DummyStrategy({})],
        confluence_analyzer=confluence,
        trifecta_analyzer=trifecta,
        mt5_connector=None
    )
    # scan_results sin datos válidos
    scan_results = {"EURUSD|M5": {"regime": None, "df": None, "symbol": None, "timeframe": "M5"}}
    with caplog.at_level("WARNING"):
        signals = await factory.generate_signals_batch(scan_results)
    assert len(signals) == 0
    assert any("No tasks created" in r for r in caplog.text.splitlines())
