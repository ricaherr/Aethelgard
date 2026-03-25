from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import pandas as pd

from models.signal import Signal, MarketRegime
from models.trade_result import TradeResult


class BaseStrategy(ABC):
    """
    Clase base abstracta para todas las estrategias de trading en Aethelgard.
    Define el contrato que deben cumplir las estrategias para ser ejecutadas
    por el SignalFactory (analyze) y por el ScenarioBacktester (evaluate_on_history).
    """

    def __init__(self, config: Dict):
        self.config = config

    @abstractmethod
    async def analyze(self, symbol: str, df: pd.DataFrame, regime: MarketRegime) -> Optional[Signal]:
        """
        Analiza los datos de mercado en tiempo real y genera una señal si se cumplen
        las condiciones de la estrategia.
        """
        pass

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Identificador único de la estrategia."""
        pass

    @abstractmethod
    def evaluate_on_history(self, df: pd.DataFrame, params: Dict) -> List[TradeResult]:
        """
        Evalúa la estrategia sobre un DataFrame OHLCV histórico y retorna la lista
        de operaciones que se habrían generado.

        Contrato:
        - Solo usa el DataFrame y params — sin dependencias externas (storage, sensores).
        - Cada operación en la lista es un TradeResult con todos los campos poblados.
        - DataFrame vacío o datos insuficientes → lista vacía (nunca lanza excepción).

        Args:
            df:     DataFrame OHLCV con columnas: open, high, low, close, volume.
            params: Parámetros de la estrategia para esta evaluación.
                    Puede incluir: risk_reward, confidence_threshold, etc.

        Returns:
            Lista de TradeResult (puede ser vacía si no se generan señales).
        """
        pass

    # ── Helper compartido para simulación de salida ───────────────────────────

    @staticmethod
    def _exit_by_sl_tp(
        df: pd.DataFrame,
        entry_idx: int,
        stop_loss: float,
        take_profit: float,
        direction: int,
        max_bars: int = 50,
    ) -> Tuple[float, int]:
        """
        Simula la salida de una operación buscando el primer bar donde se toca
        el SL o TP. Si no se alcanza ninguno, sale al precio de cierre del bar
        máximo permitido.

        Returns:
            (exit_price, bars_held)
        """
        n = len(df)
        for j in range(entry_idx + 1, min(entry_idx + max_bars + 1, n)):
            h = df["high"].iloc[j]
            lo = df["low"].iloc[j]
            if direction == 1:  # LONG
                if lo <= stop_loss:
                    return stop_loss, j - entry_idx
                if h >= take_profit:
                    return take_profit, j - entry_idx
            else:  # SHORT
                if h >= stop_loss:
                    return stop_loss, j - entry_idx
                if lo <= take_profit:
                    return take_profit, j - entry_idx
        end_idx = min(entry_idx + max_bars, n - 1)
        return float(df["close"].iloc[end_idx]), max_bars
