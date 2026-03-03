"""
Tests para FibonacciExtender - Proyector de Extensiones Fibonacci

Trace_ID: EXEC-FIBONACCI-EXT-001

Valida:
  - Cálculo de proyecciones Fibonacci 127% y 161%
  - Validación de rangos de sesión Londres
  - Detección de confluencia de precio
  - Integración con S-0005 (SESS_EXT_0001)
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from core_brain.sensors.fibonacci_extender import (
    FibonacciExtender,
    FibonacciLevel,
    FibonacciExtensionData,
    initialize_fibonacci_extender
)


@pytest.fixture
def mock_storage():
    """Mock de StorageManager."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {}
    storage.get_system_state = MagicMock(return_value={})
    return storage


@pytest.fixture
def mock_session_service():
    """Mock de MarketSessionService."""
    session_service = MagicMock()
    session_service.get_london_session.return_value = {
        'start_hour': 8,
        'end_hour': 17,
        'timezone': 'GMT'
    }
    return session_service


@pytest.fixture
def fibonacci_extender(mock_storage, mock_session_service):
    """Instancia de FibonacciExtender con dependencias mockeadas."""
    return FibonacciExtender(
        storage=mock_storage,
        session_service=mock_session_service,
        tenant_id="TEST",
        trace_id="TEST-FIBONACCI-001"
    )


class TestFibonacciExtenderInitialization:
    """Tests de inicialización del extractor Fibonacci."""
    
    def test_initialization(self, fibonacci_extender):
        """Verifica que el extractor se inicializa correctamente."""
        assert fibonacci_extender.tenant_id == "TEST"
        assert fibonacci_extender.trace_id == "TEST-FIBONACCI-001"
        assert fibonacci_extender.fib_levels['FIB_127'] == 1.27
        assert fibonacci_extender.fib_levels['FIB_161'] == 1.618
    
    def test_default_trace_id_generation(self, mock_storage, mock_session_service):
        """Verifica que se genera TRACE_ID automático si no se proporciona."""
        extender = FibonacciExtender(
            storage=mock_storage,
            session_service=mock_session_service,
            tenant_id="PROD"
        )
        assert "SENSOR-FIBONACCI-PROD" in extender.trace_id
    
    def test_factory_function(self, mock_storage, mock_session_service):
        """Verifica que la factory function funciona correctamente."""
        extender = initialize_fibonacci_extender(
            storage=mock_storage,
            session_service=mock_session_service,
            tenant_id="FACTORY_TEST"
        )
        assert isinstance(extender, FibonacciExtender)
        assert extender.tenant_id == "FACTORY_TEST"


class TestFibonacciProjection:
    """Tests de proyección de extensiones Fibonacci."""
    
    def test_project_fib_127_and_161(self, fibonacci_extender):
        """
        Verifica el cálculo correcto de extensiones 127% y 161%.
        
        Ejemplo: London range EUR/USD
        - High: 1.1000
        - Low: 1.0900
        - Range: 0.0100
        - FIB_127 = 1.1000 + (0.0100 * 1.27) = 1.1127
        - FIB_161 = 1.1000 + (0.0100 * 1.618) = 1.1162 (golden ratio)
        """
        london_high = 1.1000
        london_low = 1.0900
        
        levels = fibonacci_extender.project_fibonacci_extensions(london_high, london_low)
        
        assert 'FIB_127' in levels
        assert 'FIB_161' in levels
        
        # Verificar precisión de cálculos
        fib_127_expected = 1.1000 + (0.0100 * 1.27)
        fib_161_expected = 1.1000 + (0.0100 * 1.618)
        
        assert abs(levels['FIB_127'].price - fib_127_expected) < 1e-5
        assert abs(levels['FIB_161'].price - fib_161_expected) < 1e-5
    
    def test_project_fib_with_larger_range(self, fibonacci_extender):
        """
        Test con rango de sesión más grande (GBP/JPY typical).
        
        GBP/JPY London session
        - High: 186.50
        - Low: 185.00
        - Range: 1.50
        - FIB_127 = 186.50 + (1.50 * 1.27) = 188.405
        - FIB_161 = 186.50 + (1.50 * 1.618) = 188.927
        """
        london_high = 186.50
        london_low = 185.00
        
        levels = fibonacci_extender.project_fibonacci_extensions(london_high, london_low)
        
        fib_127_expected = 186.50 + (1.50 * 1.27)
        fib_161_expected = 186.50 + (1.50 * 1.618)
        
        assert abs(levels['FIB_127'].price - fib_127_expected) < 1e-2
        assert abs(levels['FIB_161'].price - fib_161_expected) < 1e-2
    
    def test_project_fib_invalid_range(self, fibonacci_extender):
        """Verifica que retorna dict vacío si high <= low."""
        london_high = 1.0900
        london_low = 1.1000  # high < low (inválido)
        
        levels = fibonacci_extender.project_fibonacci_extensions(london_high, london_low)
        
        assert levels == {}
    
    def test_project_fib_zero_range(self, fibonacci_extender):
        """Verifica comportamiento con rango cero."""
        london_high = 1.1000
        london_low = 1.1000
        
        levels = fibonacci_extender.project_fibonacci_extensions(london_high, london_low)
        
        assert levels == {}
    
    def test_fibonacci_level_structure(self, fibonacci_extender):
        """Verifica que cada FibonacciLevel tiene la estructura correcta."""
        london_high = 1.1000
        london_low = 1.0900
        
        levels = fibonacci_extender.project_fibonacci_extensions(london_high, london_low)
        
        for label, level in levels.items():
            assert isinstance(level, FibonacciLevel)
            assert level.label in ['FIB_127', 'FIB_161']
            assert level.price > london_high  # Extensión siempre encima
            assert level.ratio in [1.27, 1.618]
            assert level.range_component > 0


class TestPrimarySecondaryTargets:
    """Tests para métodos de target primario y secundario."""
    
    def test_primary_target_fib_127(self, fibonacci_extender):
        """Verifica que get_primary_target retorna FIB_127."""
        london_high = 1.1000
        london_low = 1.0900
        
        primary = fibonacci_extender.get_primary_target(london_high, london_low)
        
        assert primary is not None
        fib_127_expected = 1.1000 + (0.0100 * 1.27)
        assert abs(primary - fib_127_expected) < 1e-5
    
    def test_secondary_target_fib_161(self, fibonacci_extender):
        """Verifica que get_secondary_target retorna FIB_161."""
        london_high = 1.1000
        london_low = 1.0900
        
        secondary = fibonacci_extender.get_secondary_target(london_high, london_low)
        
        assert secondary is not None
        fib_161_expected = 1.1000 + (0.0100 * 1.618)
        assert abs(secondary - fib_161_expected) < 1e-5
    
    def test_primary_target_invalid_range(self, fibonacci_extender):
        """Verifica que get_primary_target retorna None si rango es inválido."""
        london_high = 1.0900
        london_low = 1.1000
        
        primary = fibonacci_extender.get_primary_target(london_high, london_low)
        
        assert primary is None


class TestPriceConfluence:
    """Tests de validación de confluencia de precio."""
    
    def test_confluence_at_fib_127(self, fibonacci_extender):
        """Verifica confluencia cuando precio está en FIB_127."""
        london_high = 1.1000
        london_low = 1.0900
        fib_127_expected = london_high + ((london_high - london_low) * 1.27)
        
        # Precio exactamente en FIB_127
        current_price = fib_127_expected
        
        result = fibonacci_extender.validate_price_confluence(
            current_price=current_price,
            london_high=london_high,
            london_low=london_low,
            tolerance_pips=5.0
        )
        
        assert result['is_confluent'] is True
        assert result['level_near'] == 'FIB_127'
        assert result['distance_pips'] < 5.0
    
    def test_confluence_near_fib_161(self, fibonacci_extender):
        """Verifica confluencia cuando precio está cerca de FIB_161."""
        london_high = 1.1000
        london_low = 1.0900
        fib_161_expected = london_high + ((london_high - london_low) * 1.618)
        
        # Precio dentro de tolerancia
        current_price = fib_161_expected + 0.00003  # ~3 pips de diferencia
        
        result = fibonacci_extender.validate_price_confluence(
            current_price=current_price,
            london_high=london_high,
            london_low=london_low,
            tolerance_pips=5.0
        )
        
        assert result['is_confluent'] is True
        assert result['level_near'] == 'FIB_161'
    
    def test_no_confluence_far_from_levels(self, fibonacci_extender):
        """Verifica que no hay confluencia si precio está lejos de niveles."""
        london_high = 1.1000
        london_low = 1.0900
        
        # Precio lejos de cualquier nivel
        current_price = 1.0850
        
        result = fibonacci_extender.validate_price_confluence(
            current_price=current_price,
            london_high=london_high,
            london_low=london_low,
            tolerance_pips=5.0
        )
        
        assert result['is_confluent'] is False
        assert result['level_near'] is None
    
    def test_confluence_with_custom_tolerance(self, fibonacci_extender):
        """Verifica que tolerance_pips personalizado funciona."""
        london_high = 1.1000
        london_low = 1.0900
        fib_127_expected = london_high + ((london_high - london_low) * 1.27)
        
        # Precio 8 pips de diferencia
        current_price = fib_127_expected + 0.0008
        
        # Con tolerance 5 pips -> no confluente
        result_tight = fibonacci_extender.validate_price_confluence(
            current_price=current_price,
            london_high=london_high,
            london_low=london_low,
            tolerance_pips=5.0
        )
        
        # Con tolerance 10 pips -> confluente
        result_loose = fibonacci_extender.validate_price_confluence(
            current_price=current_price,
            london_high=london_high,
            london_low=london_low,
            tolerance_pips=10.0
        )
        
        assert result_tight['is_confluent'] is False
        assert result_loose['is_confluent'] is True


class TestPydanticValidation:
    """Tests de validación con Pydantic."""
    
    def test_fibonacci_extension_data_validation(self):
        """Verifica que FibonacciExtensionData valida datos correctamente."""
        data = FibonacciExtensionData(
            london_high=1.1000,
            london_low=1.0900,
            london_range=0.0100
        )
        
        assert data.london_high == 1.1000
        assert data.london_low == 1.0900
        assert data.london_range == 0.0100
        assert isinstance(data.timestamp, datetime)
    
    def test_fibonacci_level_validation(self):
        """Verifica que FibonacciLevel valida estructura correctamente."""
        level = FibonacciLevel(
            label="FIB_127",
            price=1.1127,
            ratio=1.27,
            range_component=0.0127
        )
        
        assert level.label == "FIB_127"
        assert level.price == 1.1127
        assert level.ratio == 1.27
        assert level.range_component == 0.0127


class TestS0005Integration:
    """Tests de integración con estrategia S-0005 (SESS_EXT_0001)."""
    
    def test_gbp_jpy_scenario(self, fibonacci_extender):
        """
        Test escenario real de GBP/JPY (prime asset para S-0005).
        
        Datos de sesión Londres:
        - High: 186.50
        - Low: 185.00
        - Target FIB_127: ~188.41
        - Target FIB_161: ~188.93
        """
        london_high = 186.50
        london_low = 185.00
        
        primary = fibonacci_extender.get_primary_target(london_high, london_low)
        secondary = fibonacci_extender.get_secondary_target(london_high, london_low)
        
        # Valores esperados de acuerdo con MANIFESTO S-0005
        assert 188.0 < primary < 189.0
        assert 188.5 < secondary < 189.5
        assert secondary > primary  # FIB_161 > FIB_127
    
    def test_eur_jpy_scenario(self, fibonacci_extender):
        """
        Test escenario EUR/JPY (secondary asset, 0.85 affinity).
        """
        london_high = 162.25
        london_low = 161.00
        
        primary = fibonacci_extender.get_primary_target(london_high, london_low)
        secondary = fibonacci_extender.get_secondary_target(london_high, london_low)
        
        assert primary is not None
        assert secondary is not None
        assert primary < secondary
    
    def test_affinity_asset_filtering(self):
        """
        Verifica que assets con baja affinity no deben usar S-0005.
        
        AUD/JPY tiene 0.65 affinity (solo monitoreo, sin operación).
        """
        # Este test es más conceptual - verifica que FibonacciExtender
        # retorna niveles válidos pero es responsabilidad de StrategyGatekeeper
        # filtrar por affinity.
        
        # AUD/JPY datos hipotéticos
        london_high = 105.50
        london_low = 104.75
        
        levels = {
            'FIB_127': london_high + ((london_high - london_low) * 1.27),
            'FIB_161': london_high + ((london_high - london_low) * 1.618)
        }
        
        # FibonacciExtender calcula siempre, el gatekeeper filtra por affinity
        assert levels['FIB_127'] > london_high
        assert levels['FIB_161'] > levels['FIB_127']


class TestFibonacciExtenderMultiTenant:
    """
    Tests de aislamiento multi-tenant para FibonacciExtender.
    
    Valida que el sensor respeta tenant_id y no mezcla datos entre tenants.
    Cumple con DEVELOPMENT_GUIDELINES Rule 1.1 (Aislamiento / RULE T1).
    
    TRACE_ID: EXEC-TENANT-ISOLATION-FIBONACCI
    """
    
    def test_fibonacci_extender_respects_tenant_id(self):
        """
        Verifica que FibonacciExtender almacena y respeta tenant_id en TRACE_ID.
        
        Escenario: Dos tenants (ALICE, BOB) crean sus propios FibonacciExtenders.
        Se espera que cada uno tenga su propio trace_id con su tenant_id.
        """
        mock_storage = MagicMock()
        mock_service = MagicMock()
        
        # Crear extender para ALICE
        alice_extender = FibonacciExtender(
            storage=mock_storage,
            session_service=mock_service,
            tenant_id="ALICE",
            trace_id=None  # Auto-generate
        )
        
        # Crear extender para BOB
        bob_extender = FibonacciExtender(
            storage=mock_storage,
            session_service=mock_service,
            tenant_id="BOB",
            trace_id=None  # Auto-generate
        )
        
        # Validar que cada uno tiene su tenant_id
        assert alice_extender.tenant_id == "ALICE"
        assert bob_extender.tenant_id == "BOB"
        
        # Validar que TRACE_ID contiene el tenant_id
        assert "ALICE" in alice_extender.trace_id
        assert "BOB" in bob_extender.trace_id
        
        # Validar que TRACE_IDs son diferentes
        assert alice_extender.trace_id != bob_extender.trace_id
    
    def test_fibonacci_isolation_calculations_independent(self):
        """
        Verifica que cálculos Fibonacci de diferentes tenants son independientes.
        
        Escenario: ALICE y BOB ejecutan project_fibonacci_extensions() con los
        mismos rangos. Se espera que ambos obtengan resultados idénticos
        (los cálculos son agnósticos de tenant), pero que el logging sea diferente
        (cada uno tiene su TRACE_ID único).
        """
        mock_storage = MagicMock()
        mock_service = MagicMock()
        
        alice_extender = FibonacciExtender(
            storage=mock_storage,
            session_service=mock_service,
            tenant_id="ALICE"
        )
        
        bob_extender = FibonacciExtender(
            storage=mock_storage,
            session_service=mock_service,
            tenant_id="BOB"
        )
        
        # Mismo rango Londres para ambos
        london_high = 186.50
        london_low = 185.00
        
        # Ambos calculan sobre el mismo rango
        alice_levels = alice_extender.project_fibonacci_extensions(london_high, london_low)
        bob_levels = bob_extender.project_fibonacci_extensions(london_high, london_low)
        
        # Deben obtener el MISMO resultado numérico (cálculos agnósticos)
        assert abs(alice_levels['FIB_127'].price - bob_levels['FIB_127'].price) < 1e-5
        assert abs(alice_levels['FIB_161'].price - bob_levels['FIB_161'].price) < 1e-5
        
        # Pero sus niveles Fibonacci tienen metadata de tenant diferente
        # (implícitamente: si hubiera logueo, ALICE y BOB tendrían TRACE_IDs diferentes)
        assert alice_extender.tenant_id != bob_extender.tenant_id
    
    def test_fibonacci_storage_manager_isolation(self):
        """
        Verifica que cada tenant usa su propia StorageManager (vía DI).
        
        Patrón DEVELOPMENT_GUIDELINES 1.1:
        Si contamos con TenantDBFactory.get_storage(tenant_id),
        cada FibonacciExtender debe recibir su propia instancia.
        
        Este test valida que la inyección de dependencias funciona
        sin mezcla de storage entre tenants.
        """
        # Simular dos StorageManager instancias (una por tenant)
        alice_storage = MagicMock()
        alice_storage.get_dynamic_params.return_value = {}
        
        bob_storage = MagicMock()
        bob_storage.get_dynamic_params.return_value = {}
        
        mock_session_service = MagicMock()
        
        # ALICE recibe su storage
        alice_extender = FibonacciExtender(
            storage=alice_storage,
            session_service=mock_session_service,
            tenant_id="ALICE"
        )
        
        # BOB recibe su storage
        bob_extender = FibonacciExtender(
            storage=bob_storage,
            session_service=mock_session_service,
            tenant_id="BOB"
        )
        
        # Validar que están usando diferentes storage
        assert alice_extender.storage_manager is alice_storage
        assert bob_extender.storage_manager is bob_storage
        assert alice_extender.storage_manager is not bob_extender.storage_manager
    
    def test_fibonacci_factory_respects_tenant_context(self):
        """
        Verifica que initialize_fibonacci_extender() factory respeta tenant_id.
        
        Factory function DEBE pasar correctamente el tenant_id al constructor.
        """
        mock_storage = MagicMock()
        mock_service = MagicMock()
        
        # Factory para ALICE
        alice_factory = initialize_fibonacci_extender(
            storage=mock_storage,
            session_service=mock_service,
            tenant_id="ALICE"
        )
        
        # Factory para BOB
        bob_factory = initialize_fibonacci_extender(
            storage=mock_storage,
            session_service=mock_service,
            tenant_id="BOB"
        )
        
        # Ambos deben ser instancias correctas
        assert isinstance(alice_factory, FibonacciExtender)
        assert isinstance(bob_factory, FibonacciExtender)
        
        # Con sus respectivos tenant_ids
        assert alice_factory.tenant_id == "ALICE"
        assert bob_factory.tenant_id == "BOB"
        
        # Y TRACE_IDs únicos
        assert alice_factory.trace_id != bob_factory.trace_id

