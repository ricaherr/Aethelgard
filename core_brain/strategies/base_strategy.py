from abc import ABC, abstractmethod
from typing import Optional, Dict
import pandas as pd
from models.signal import Signal, MarketRegime

class BaseStrategy(ABC):
    """
    Clase base abstracta para todas las estrategias de trading en Aethelgard.
    Define el contrato que deben cumplir las estrategias para ser ejecutadas por el SignalFactory.
    """
    
    def __init__(self, config: Dict):
        """
        Inicializa la estrategia con su configuración.
        
        Args:
            config: Diccionario con parámetros específicos de la estrategia.
        """
        self.config = config

    @abstractmethod
    async def analyze(self, symbol: str, df: pd.DataFrame, regime: MarketRegime) -> Optional[Signal]:
        """
        Analiza los datos de mercado y determina si se genera una señal.
        
        Args:
            symbol: El símbolo del activo.
            df: DataFrame con datos OHLC e indicadores.
            regime: El régimen de mercado actual detectado.
            
        Returns:
            Optional[Signal]: Objeto Signal si se cumplen condiciones, None en caso contrario.
        """
        pass
    
    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Retorna el identificador único de la estrategia."""
        pass
