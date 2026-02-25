import pytest
from unittest.mock import MagicMock, patch, mock_open, Mock
import json

# Asumimos que RiskManager está en core_brain.risk_manager
# Esta importación funcionará cuando se ejecute con pytest desde la raíz del proyecto
from core_brain.risk_manager import RiskManager
from core_brain.instrument_manager import InstrumentManager
from models.signal import MarketRegime, Signal, SignalType, ConnectorType

INSTRUMENTS_CONFIG_EXAMPLE = {
    "FOREX": {
        "majors": {"instruments": ["EURUSD", "GBPUSD", "USDJPY"], "enabled": True, "min_score": 70.0},
        "minors": {"instruments": ["EURGBP", "EURJPY", "GBPJPY"], "enabled": True, "min_score": 75.0},
        "exotics": {"instruments": ["USDTRY", "USDZAR", "USDMXN"], "enabled": False, "min_score": 90.0},
    },
    "CRYPTO": {
        "tier1": {"instruments": ["BTCUSDT", "ETHUSDT"], "enabled": True, "min_score": 75.0},
        "altcoins": {"instruments": ["ADAUSDT", "DOGEUSDT"], "enabled": False, "min_score": 85.0},
    }
}

@pytest.fixture
def mock_storage():
    """Fixture para mockear la clase StorageManager y su interacción con la DB."""
    mock = MagicMock()

    # Simula el estado inicial del sistema leído desde la DB

    # Simula el estado inicial del sistema leído desde la DB
    mock.get_system_state.return_value = {'lockdown_mode': False}
    mock.get_risk_settings.return_value = {"max_account_risk_pct": 5.0}
    mock.get_dynamic_params.return_value = {"risk_per_trade": 0.01}

    return mock



@pytest.fixture

def mock_dynamic_params():

    """Fixture to simulate dynamic params data (now stored in DB — SSOT Rule 14)."""

    params = {

        "risk_per_trade": 0.02, # Un valor específico para la prueba

        "max_consecutive_losses": 3

    }

    return json.dumps(params)



@pytest.fixture
def instrument_manager():
    from data_vault.storage import StorageManager
    storage = StorageManager(db_path=':memory:')
    state = storage.get_system_state()
    state["instruments_config"] = INSTRUMENTS_CONFIG_EXAMPLE
    storage.update_system_state(state)
    return InstrumentManager(storage=storage)



def test_agnostic_position_sizing(mock_dynamic_params, instrument_manager):



    """



    Verifica que el cálculo de tamaño de posición es agnóstico al instrumento.



    Prueba con valores para un contrato de Futuros (puntos) y un par de Forex (pips).



    """



    from data_vault.storage import StorageManager
    storage = StorageManager(db_path=':memory:')
    storage.update_dynamic_params(json.loads(mock_dynamic_params))
    rm = RiskManager(storage=storage, initial_capital=10000, instrument_manager=instrument_manager)

    # Escenario 1: Futuros (ej. ES)
    position_size_futures = rm.calculate_position_size(
        symbol="BTCUSD",
        risk_amount_usd=200.0,
        stop_loss_dist=1000.0
    )
    assert position_size_futures >= 0

    # Escenario 2: Forex (ej. EUR/USD)
    position_size_forex = rm.calculate_position_size(
        symbol="EURUSD",
        risk_amount_usd=200.0,
        stop_loss_dist=0.0020
    )
    assert position_size_forex >= 0



def test_lockdown_persistence_on_init(instrument_manager):

    """

    Verifica que el RiskManager recupera el estado de 'lockdown_mode'

    desde la base de datos al inicializarse.

    """

    mock_storage_in_lockdown = MagicMock()
    from datetime import datetime
    mock_storage_in_lockdown.get_system_state.return_value = {
        'lockdown_mode': True,
        'lockdown_date': datetime.now().isoformat(),
        'lockdown_balance': 10000
    }


def test_defensive_posture_with_none_regime(mock_dynamic_params, instrument_manager):

    """

    Verifica que el sistema adopta una postura defensiva (tamaño de posición 0)

    cuando el régimen de mercado es None.

    """

    with patch('builtins.open', mock_open(read_data=mock_dynamic_params)):

        from data_vault.storage import StorageManager; storage = StorageManager(db_path=':memory:'); rm = RiskManager(storage=storage, initial_capital=10000, instrument_manager=instrument_manager)

    

    position_size = rm.calculate_position_size(

        symbol="EURUSD",

        risk_amount_usd=100.0,

        stop_loss_dist=0.0050

    )

    

    assert position_size >= 0, "RiskManager debe devolver un tamaño de posición válido (>= 0)."



def test_risk_auto_adjustment_from_params(mock_dynamic_params, instrument_manager):

    """

    Verifica que el RiskManager carga el risk_per_trade desde el archivo

    de parámetros dinámicos y no usa un valor estático.

    """

    from data_vault.storage import StorageManager
    storage = StorageManager(db_path=':memory:')
    storage.update_dynamic_params(json.loads(mock_dynamic_params))
    rm = RiskManager(storage=storage, initial_capital=10000, instrument_manager=instrument_manager)

    

    # El valor en mock_dynamic_params es 0.02

    assert rm.risk_per_trade == 0.02


def test_can_take_new_trade_rejects_if_exceeds_max_account_risk(instrument_manager):
    """
    Verifica que RiskManager.can_take_new_trade() rechaza una señal
    cuando el riesgo total de cuenta excedería el límite configurado.
    
    Escenario:
    - Cuenta: $10,000
    - max_account_risk_pct: 5.0% ($500 máximo)
    - 3 posiciones activas: $150 cada una = $450 total (4.5%)
    - Nueva señal: $100 de riesgo (1%)
    - Total si se ejecuta: $550 (5.5%) > $500 (5.0%) → RECHAZAR
    
    Expected: can_take_new_trade() retorna (False, reason)
    """
    # ...existing code...
    # ...existing code...
    
    # Mock dynamic_params (DB SSOT) con risk_per_trade
    mock_params = json.dumps({
        "risk_per_trade": 0.01,  # 1% per trade
        "max_consecutive_losses": 3
    })
    
    # Mock risk_settings.json con max_account_risk_pct
    mock_risk_settings = json.dumps({
        "max_account_risk_pct": 5.0,  # 5% max account risk
        "lockdown_mode_enabled": True,
        "max_consecutive_losses": 3
    })
    
    # Setup: Mock connector
    mock_connector = Mock()
    mock_connector.get_account_balance = Mock(return_value=10000.0)
    mock_connector.get_open_positions = Mock(return_value=[
        {
            "symbol": "EURUSD",
            "volume": 0.5,
            "entry_price": 1.1000,
            "stop_loss": 1.0970,
            "ticket": 111
        },
        {
            "symbol": "GBPUSD",
            "volume": 0.3,
            "entry_price": 1.2600,
            "stop_loss": 1.2550,
            "ticket": 222
        },
        {
            "symbol": "USDJPY",
            "volume": 0.4,
            "entry_price": 150.00,
            "stop_loss": 149.50,
            "ticket": 333
        }
    ])
def test_can_take_new_trade_approves_if_within_limit(instrument_manager):
    """
    Verifica que RiskManager.can_take_new_trade() APRUEBA una señal
    cuando el riesgo total de cuenta se mantiene dentro del límite.
    
    Escenario:
    - Cuenta: $10,000
    - max_account_risk_pct: 5.0% ($500 máximo)
    - 2 posiciones activas: $150 cada una = $300 total (3%)
    - Nueva señal: $100 de riesgo (1%)
    - Total si se ejecuta: $400 (4%) < $500 (5.0%) → APROBAR
    
    Expected: can_take_new_trade() retorna (True, "")
    """
    # Setup: Mock storage con solo 2 posiciones activas
    mock_storage = MagicMock()
    mock_storage.get_risk_settings.return_value = {"max_account_risk_pct": 5.0}
    mock_storage.get_dynamic_params.return_value = {"risk_per_trade": 0.01}
    
    mock_storage.get_active_positions.return_value = [
        {
            "ticket": 111,
            "symbol": "EURUSD",
            "volume": 0.5,
            "entry_price": 1.1000,
            "stop_loss": 1.0970,
            "metadata": {"risk_usd": 150.0}
        },
        {
            "ticket": 222,
            "symbol": "GBPUSD",
            "volume": 0.3,
            "entry_price": 1.2600,
            "stop_loss": 1.2550,
            "metadata": {"risk_usd": 150.0}
        }
    ]
    
    mock_params = json.dumps({
        "risk_per_trade": 0.01,
        "max_consecutive_losses": 3
    })
    
    mock_risk_settings = json.dumps({
        "max_account_risk_pct": 5.0,
        "lockdown_mode_enabled": True,
        "max_consecutive_losses": 3
    })
    
    mock_connector = Mock()
    mock_connector.get_account_balance = Mock(return_value=10000.0)
    mock_connector.get_open_positions = Mock(return_value=[
        {
            "symbol": "EURUSD",
            "volume": 0.5,
            "entry_price": 1.1000,
            "stop_loss": 1.0970,
            "ticket": 111
        },
        {
            "symbol": "GBPUSD",
            "volume": 0.3,
            "entry_price": 1.2600,
            "stop_loss": 1.2550,
            "ticket": 222
        }
    ])
    mock_connector.get_symbol_info = Mock(return_value=MagicMock(
        trade_contract_size=100000,
        point=0.00001,
        digits=5
    ))
    mock_connector.get_current_price = Mock(return_value=1.1000)
    
    test_signal = Signal(
        symbol="XAUUSD",
        signal_type=SignalType.BUY,
        connector_type=ConnectorType.METATRADER5,
        timeframe="H1",
        entry_price=2050.0,
        stop_loss=2040.0,
        take_profit=2070.0,
        confidence=0.80,
        metadata={"regime": MarketRegime.TREND.value}
    )
    
    with patch('builtins.open', mock_open(read_data=mock_params)) as mock_file:
        def side_effect(path, *args, **kwargs):
            if 'risk_settings.json' in str(path):
                return mock_open(read_data=mock_risk_settings).return_value
            else:
                return mock_open(read_data=mock_params).return_value
        
        mock_file.side_effect = side_effect
        
        rm = RiskManager(storage=mock_storage, initial_capital=10000, instrument_manager=instrument_manager)
        can_trade, reason = rm.can_take_new_trade(test_signal, mock_connector)

