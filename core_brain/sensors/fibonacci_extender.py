"""
FibonacciExtender - Proyector de Niveles Fibonacci en Extensiones de Sesión

Responsabilidades:
- Calcular proyecciones de Fibonacci basadas en rangos de sesión (Londres)
- Proyectar extensiones 127% (1.27R) y 161% (1.618R) desde session high/low
- Validar niveles según datos de mercado actual
- Proporcionar confirmación de precio para entrada confluente

Estrategia S-0005 (SESS_EXT_0001): Fibonacci Extensions en Sessión Daily Flow
- Prime assets: GBP/JPY (0.90 affinity), EUR/JPY (0.85), AUD/JPY (0.65)
- Timeframes: H1/H4
- Membership: Premium+
- Operación: Busca extensión Fibonacci 127%+ desde Londres session range

TRACE_ID: SENSOR-FIBONACCI-EXTENDER-2026
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional, List, Any
from pydantic import BaseModel, Field, ValidationError

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class FibonacciLevel(BaseModel):
    """Validación de un nivel Fibonacci proyectado."""
    label: str = Field(..., description="Nivel (e.g., 'FIB_127', 'FIB_161')")
    price: float = Field(..., gt=0, description="Nivel de precio calculado")
    ratio: float = Field(..., ge=0, description="Ratio Fibonacci (e.g., 1.27, 1.618)")
    range_component: float = Field(..., gt=0, description="Componente de rango usado")
    
    class Config:
        str_strip_whitespace = True


class FibonacciExtensionData(BaseModel):
    """Validación de datos de extensión Fibonacci desde sesión Londres."""
    london_high: float = Field(..., gt=0, description="Session High Londres")
    london_low: float = Field(..., gt=0, description="Session Low Londres")
    london_range: float = Field(..., gt=0, description="Rango Londres (high - low)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        str_strip_whitespace = True


class FibonacciExtender:
    """
    Sensor para proyectar niveles de extensión Fibonacci.
    
    Basado en session high/low de Londres, proyecta extensiones 127% y 161%
    que sirven como targets para estrategia SESS_EXT_0001.
    
    Patrón operativo:
    1. Capturar London Session High/Low (08:00-17:00 GMT)
    2. Calcular rango: range = high - low
    3. Proyectar FIB_127: high + (range * 1.27)
    4. Proyectar FIB_161: high + (range * 1.618)
    5. Esperar confluencia de elephant candle + NY opening
    6. Entrada en FIB_127 con stop en FIB_0 (session low)
    """
    
    def __init__(
        self,
        storage: StorageManager,
        session_service=None,
        tenant_id: str = "DEFAULT",
        trace_id: str = None
    ):
        """
        Inicializa FibonacciExtender con inyección de dependencias.
        
        Args:
            storage: StorageManager para acceso a datos configuración
            session_service: Servicio de sesiones (MarketSessionService) para obtener London H/L
            tenant_id: Identificador del tenant para aislamiento multitenancy
            trace_id: Identificador único de traza para logging
        """
        self.storage_manager = storage
        self.session_service = session_service
        self.tenant_id = tenant_id
        self.trace_id = trace_id or f"SENSOR-FIBONACCI-{tenant_id}"
        
        # Ratios Fibonacci para extensiones
        self.fib_levels = {
            'FIB_127': 1.27,      # Extensión 127% (objetivo primario)
            'FIB_161': 1.618,     # Extensión 161% (objetivo secundario, golden ratio)
        }
        
        logger.info(f"[{self.trace_id}] FibonacciExtender initialized for tenant {self.tenant_id}")
    
    
    def project_fibonacci_extensions(
        self,
        london_high: float,
        london_low: float
    ) -> Dict[str, FibonacciLevel]:
        """
        Proyecta niveles de extensión Fibonacci basados en rango de sesión Londres.
        
        Fórmula:
        - Range = London High - London Low
        - FIB_127 = London High + (Range * 1.27)
        - FIB_161 = London High + (Range * 1.618)
        
        Args:
            london_high: Session high de Londres (08:00-17:00 GMT)
            london_low: Session low de Londres
            
        Returns:
            Dict con FibonacciLevel para cada ratio
            
        Raises:
            ValidationError: Si los precios no son válidos
        """
        try:
            # Validar datos de entrada
            if london_high <= london_low:
                logger.warning(
                    f"[{self.trace_id}] Invalid London range: high={london_high} <= low={london_low}"
                )
                return {}
            
            london_range = london_high - london_low
            
            # Crear modelo validado
            ext_data = FibonacciExtensionData(
                london_high=london_high,
                london_low=london_low,
                london_range=london_range
            )
            
            logger.debug(
                f"[{self.trace_id}] London session - High: {ext_data.london_high:.5f}, "
                f"Low: {ext_data.london_low:.5f}, Range: {ext_data.london_range:.5f}"
            )
            
            # Calcular niveles Fibonacci
            levels = {}
            for label, ratio in self.fib_levels.items():
                fib_price = london_high + (london_range * ratio)
                
                level = FibonacciLevel(
                    label=label,
                    price=fib_price,
                    ratio=ratio,
                    range_component=london_range * ratio
                )
                
                levels[label] = level
                
                logger.info(
                    f"[{self.trace_id}] {label} (ratio {ratio}): {fib_price:.5f} "
                    f"(range_component: {london_range * ratio:.5f})"
                )
            
            return levels
            
        except ValidationError as ve:
            logger.error(f"[{self.trace_id}] Validation error: {ve}")
            return {}
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error projecting Fibonacci levels: {e}")
            return {}
    
    
    def get_primary_target(self, london_high: float, london_low: float) -> Optional[float]:
        """
        Retorna el nivel FIB_127 (target primario para S-0005).
        
        Args:
            london_high: Session high de Londres
            london_low: Session low de Londres
            
        Returns:
            Precio del FIB_127, o None si no se puede calcular
        """
        levels = self.project_fibonacci_extensions(london_high, london_low)
        if 'FIB_127' in levels:
            return levels['FIB_127'].price
        return None
    
    
    def get_secondary_target(self, london_high: float, london_low: float) -> Optional[float]:
        """
        Retorna el nivel FIB_161 (target secundario, golden ratio).
        
        Args:
            london_high: Session high de Londres
            london_low: Session low de Londres
            
        Returns:
            Precio del FIB_161, o None si no se puede calcular
        """
        levels = self.project_fibonacci_extensions(london_high, london_low)
        if 'FIB_161' in levels:
            return levels['FIB_161'].price
        return None
    
    
    def validate_price_confluence(
        self,
        current_price: float,
        london_high: float,
        london_low: float,
        tolerance_pips: float = 5.0
    ) -> Dict[str, any]:
        """
        Valida si precio actual está en confluencia con niveles Fibonacci.
        
        Usado para confirmar entrada cuando elephant candle + Fibonacci + NY opening convergen.
        
        Args:
            current_price: Precio actual de mercado
            london_high: Session high de Londres
            london_low: Session low de Londres
            tolerance_pips: Tolerancia en pips para confluencia
            
        Returns:
            Dict con {is_confluent: bool, level_near: Optional[str], distance_pips: float}
        """
        try:
            levels = self.project_fibonacci_extensions(london_high, london_low)
            
            if not levels:
                return {'is_confluent': False, 'level_near': None, 'distance_pips': None}
            
            result = {
                'is_confluent': False,
                'level_near': None,
                'distance_pips': float('inf')
            }
            
            for label, level in levels.items():
                distance_pips = abs(current_price - level.price) * 10000  # Convertir a pips
                
                if distance_pips <= tolerance_pips:
                    result['is_confluent'] = True
                    result['level_near'] = label
                    result['distance_pips'] = distance_pips
                    
                    logger.info(
                        f"[{self.trace_id}] Price confluence detected: {current_price:.5f} "
                        f"near {label} (distance: {distance_pips:.2f} pips)"
                    )
                    break
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error validating price confluence: {e}")
            return {'is_confluent': False, 'level_near': None, 'distance_pips': None}


def initialize_fibonacci_extender(
    storage: StorageManager,
    session_service: Optional[Any] = None,
    tenant_id: str = "DEFAULT"
) -> FibonacciExtender:
    """
    Factory function para inicializar FibonacciExtender.
    
    Usado desde core_brain services para crear instancia con DI.
    
    Args:
        storage: StorageManager instance
        session_service: MarketSessionService instance
        tenant_id: Tenant identifier
        
    Returns:
        FibonacciExtender instance
    """
    return FibonacciExtender(
        storage=storage,
        session_service=session_service,
        tenant_id=tenant_id
    )
