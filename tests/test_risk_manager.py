import pytest
from unittest.mock import MagicMock, patch, mock_open
import json

# Asumimos que RiskManager está en core_brain.risk_manager
# Esta importación funcionará cuando se ejecute con pytest desde la raíz del proyecto
from core_brain.risk_manager import RiskManager
from models.signal import MarketRegime

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

            rm = RiskManager(initial_capital=10000)



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

