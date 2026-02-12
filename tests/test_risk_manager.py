import pytest
from unittest.mock import MagicMock, patch, mock_open, Mock
import json

# Asumimos que RiskManager está en core_brain.risk_manager
# Esta importación funcionará cuando se ejecute con pytest desde la raíz del proyecto
from core_brain.risk_manager import RiskManager
from models.signal import MarketRegime, Signal, SignalType, ConnectorType

@pytest.fixture
def mock_storage():
    """Fixture para mockear la clase StorageManager y su interacción con la DB."""
    mock = MagicMock()

    # Simula el estado inicial del sistema leído desde la DB

    mock.get_system_state.return_value = {'lockdown_mode': False}

    return mock



@pytest.fixture

def mock_dynamic_params():

    """Fixture para simular la lectura del archivo dynamic_params.json."""

    params = {

        "risk_per_trade": 0.02, # Un valor específico para la prueba

        "max_consecutive_losses": 3

    }

    return json.dumps(params)



def test_agnostic_position_sizing(mock_dynamic_params, mock_storage):



    """



    Verifica que el cálculo de tamaño de posición es agnóstico al instrumento.



    Prueba con valores para un contrato de Futuros (puntos) y un par de Forex (pips).



    """



    with patch('builtins.open', mock_open(read_data=mock_dynamic_params)):
        from data_vault.storage import StorageManager
        storage = StorageManager(db_path=':memory:')
        rm = RiskManager(storage=storage, initial_capital=10000)

    account_balance = 10000



    stop_loss_distance = 20



    regime_neutral = MarketRegime.NORMAL



    # Escenario 1: Futuros (ej. ES, valor del punto = $50)

    position_size_futures = rm.calculate_position_size(

        account_balance=account_balance,

        stop_loss_distance=stop_loss_distance,

        point_value=50,

        current_regime=regime_neutral

    )

    # Cálculo esperado: (10000 * 0.02) / (20 * 50) = 200 / 1000 = 0.2

    assert position_size_futures == 0.2



    # Escenario 2: Forex (ej. EUR/USD, lote estándar, valor del pip ~ $10)

    position_size_forex = rm.calculate_position_size(

        account_balance=account_balance,

        stop_loss_distance=stop_loss_distance, # 20 pips

        point_value=10,

        current_regime=regime_neutral

    )

    # Cálculo esperado: (10000 * 0.02) / (20 * 10) = 200 / 200 = 1.0

    assert position_size_forex == 1.0



def test_lockdown_persistence_on_init():

    """

    Verifica que el RiskManager recupera el estado de 'lockdown_mode'

    desde la base de datos al inicializarse.

    """

    # Simula que la base de datos reporta que el sistema YA ESTABA en lockdown

    mock_storage_in_lockdown = MagicMock()

    mock_storage_in_lockdown.get_system_state.return_value = {'lockdown_mode': True}



    params = json.dumps({"risk_per_trade": 0.01})



    with patch('builtins.open', mock_open(read_data=params)):

        with patch('core_brain.risk_manager.StorageManager', return_value=mock_storage_in_lockdown):

            rm = RiskManager(storage=mock_storage_in_lockdown, initial_capital=10000)



    assert rm.lockdown_mode is True

    # Verifica que no se abren posiciones si el sistema inicia en lockdown

    assert rm.calculate_position_size(10000, 20, 10, MarketRegime.NORMAL) == 0



def test_defensive_posture_with_none_regime(mock_dynamic_params):

    """

    Verifica que el sistema adopta una postura defensiva (tamaño de posición 0)

    cuando el régimen de mercado es None.

    """

    with patch('builtins.open', mock_open(read_data=mock_dynamic_params)):

        from data_vault.storage import StorageManager; storage = StorageManager(db_path=':memory:'); rm = RiskManager(storage=storage, initial_capital=10000)

    

    position_size = rm.calculate_position_size(

        account_balance=10000,

        stop_loss_distance=20,

        point_value=10,

        current_regime=None # Régimen nulo

    )

    

    assert position_size == 0, "RiskManager debe devolver 0 si el régimen es None."



def test_risk_auto_adjustment_from_params(mock_dynamic_params):

    """

    Verifica que el RiskManager carga el risk_per_trade desde el archivo

    de parámetros dinámicos y no usa un valor estático.

    """

    with patch('builtins.open', mock_open(read_data=mock_dynamic_params)):

        from data_vault.storage import StorageManager; storage = StorageManager(db_path=':memory:'); rm = RiskManager(storage=storage, initial_capital=10000)

    

    # El valor en mock_dynamic_params es 0.02

    assert rm.risk_per_trade == 0.02


def test_can_take_new_trade_rejects_if_exceeds_max_account_risk():
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
    # Setup: Mock storage con posiciones activas
    mock_storage = MagicMock()
    
    # 3 posiciones activas con $150 de riesgo cada una
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
        },
        {
            "ticket": 333,
            "symbol": "USDJPY",
            "volume": 0.4,
            "entry_price": 150.00,
            "stop_loss": 149.50,
            "metadata": {"risk_usd": 150.0}
        }
    ]
    
    # Mock dynamic_params.json con risk_per_trade
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
    mock_connector.get_symbol_info = Mock(return_value=MagicMock(
        trade_contract_size=100000,
        point=0.00001,
        digits=5
    ))
    mock_connector.get_current_price = Mock(return_value=1.1000)
    
    # Setup: Señal nueva ($100 riesgo esperado)
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
    
    # Create RiskManager con ambos mocks
    with patch('builtins.open', mock_open(read_data=mock_params)) as mock_file:
        # Configure mock_file para retornar diferentes contenidos según path
        def side_effect(path, *args, **kwargs):
            if 'risk_settings.json' in str(path):
                return mock_open(read_data=mock_risk_settings).return_value
            else:
                return mock_open(read_data=mock_params).return_value
        
        mock_file.side_effect = side_effect
        
        rm = RiskManager(storage=mock_storage, initial_capital=10000)
        
        # Execute: Verificar si puede tomar nueva operación
        can_trade, reason = rm.can_take_new_trade(test_signal, mock_connector)
    
    # Assert: Debe rechazar por exceder límite
    assert can_trade is False, "RiskManager debe rechazar señal que excede max_account_risk_pct"
    assert "account risk" in reason.lower(), f"Razón debe mencionar 'account risk', recibido: {reason}"
    assert "5.0%" in reason or "5%" in reason, f"Razón debe mencionar límite 5%, recibido: {reason}"


def test_can_take_new_trade_approves_if_within_limit():
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
        
        rm = RiskManager(storage=mock_storage, initial_capital=10000)
        can_trade, reason = rm.can_take_new_trade(test_signal, mock_connector)
    
    # Assert: Debe aprobar porque está dentro del límite
    assert can_trade is True, "RiskManager debe aprobar señal dentro del límite de riesgo"
    assert reason == "", f"Razón debe estar vacía cuando se aprueba, recibido: {reason}"


