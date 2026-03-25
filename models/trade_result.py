"""
trade_result.py — Resultado atómico de una operación en backtesting histórico.

Usado por evaluate_on_history() en todas las estrategias para reportar
el outcome de cada trade simulado sobre datos OHLCV reales.
"""
from dataclasses import dataclass


@dataclass
class TradeResult:
    """
    Resultado de una operación simulada durante el backtesting histórico.

    Attributes:
        entry_price:     Precio de entrada.
        exit_price:      Precio de salida (SL, TP o cierre temporal).
        pnl:             P&L en unidades de precio: direction × (exit - entry).
        direction:       1 = LONG, -1 = SHORT.
        bars_held:       Cantidad de barras entre entrada y salida.
        regime_at_entry: Régimen de mercado en el momento de la entrada
                         ('TREND' | 'RANGE' | 'VOLATILE' | 'UNKNOWN').
        sl_distance:     Distancia en precio entre entrada y stop-loss (siempre ≥ 0).
        tp_distance:     Distancia en precio entre entrada y take-profit (siempre ≥ 0).
    """
    entry_price: float
    exit_price: float
    pnl: float
    direction: int
    bars_held: int
    regime_at_entry: str
    sl_distance: float
    tp_distance: float
