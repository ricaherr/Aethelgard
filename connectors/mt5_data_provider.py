"""
Proveedor de datos OHLC desde MetaTrader 5.
Obtiene datos de forma autónoma vía copy_rates_from_pos, sin gráficas abiertas.
Usado por el Scanner Engine para ingestión proactiva.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger(__name__)

# Mapeo timeframe string -> constante MT5
TIMEFRAME_MAP = {
    "M1": getattr(mt5, "TIMEFRAME_M1", 1) if mt5 else 1,
    "M5": getattr(mt5, "TIMEFRAME_M5", 5) if mt5 else 5,
    "M15": getattr(mt5, "TIMEFRAME_M15", 15) if mt5 else 15,
    "M30": getattr(mt5, "TIMEFRAME_M30", 30) if mt5 else 30,
    "H1": getattr(mt5, "TIMEFRAME_H1", 16385) if mt5 else 16385,
    "H4": getattr(mt5, "TIMEFRAME_H4", 16388) if mt5 else 16388,
    "D1": getattr(mt5, "TIMEFRAME_D1", 16408) if mt5 else 16408,
    "W1": getattr(mt5, "TIMEFRAME_W1", 32769) if mt5 else 32769,
    "MN1": getattr(mt5, "TIMEFRAME_MN1", 49153) if mt5 else 49153,
}


class MT5DataProvider:
    """
    Obtiene OHLC desde MT5 mediante copy_rates_from_pos.
    No requiere gráficas abiertas; los símbolos deben estar en Market Watch.
    """

    def __init__(self, login: Optional[int] = None, password: str = "", server: str = "", init_mt5: bool = True):
        self._initialized = False
        if not init_mt5 or not mt5:
            return
            
        # Initialize MT5
        if not mt5.initialize():
            logger.warning("MT5 no pudo inicializarse: %s", mt5.last_error())
            return
            
        # Login if credentials provided
        if login and server:
            authorized = mt5.login(
                login=int(login),
                password=password,
                server=server
            )
            if not authorized:
                logger.warning("MT5 no pudo autorizarse con login %s: %s", login, mt5.last_error())
                return
        
        self._initialized = True
        logger.info("MT5DataProvider listo. Versión MT5: %s", mt5.version())

    def shutdown(self) -> None:
        """Cierra la conexión con MT5."""
        if mt5 and self._initialized:
            mt5.shutdown()
            self._initialized = False
            logger.info("MT5DataProvider cerrado.")

    def _resolve_timeframe(self, timeframe: str):
        t = (timeframe or "M5").upper()
        if t not in TIMEFRAME_MAP:
            logger.warning("Timeframe '%s' desconocido, usando M5.", timeframe)
            t = "M5"
        return TIMEFRAME_MAP[t]

    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500,
    ) -> Optional[pd.DataFrame]:
        """
        Obtiene las últimas velas OHLC para un símbolo vía copy_rates_from_pos.

        Args:
            symbol: Símbolo (ej. EURUSD, AAPL, MES).
            timeframe: M1, M5, M15, M30, H1, H4, D1, W1, MN1.
            count: Número de velas a recuperar.

        Returns:
            DataFrame con columnas time, open, high, low, close; None si error.
        """
        if not mt5 or not self._initialized:
            logger.error("MT5 no disponible o no inicializado.")
            return None

        tf = self._resolve_timeframe(timeframe)
        # start_pos=0: desde la vela actual; count: cuántas barras
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            err = mt5.last_error()
            logger.warning("copy_rates_from_pos(%s, %s) falló: %s", symbol, timeframe, err)
            return None

        df = pd.DataFrame(rates)
        if df.empty:
            return None
        # Mantener columnas necesarias para RegimeClassifier (time -> timestamp en load_ohlc)
        df = df[["time", "open", "high", "low", "close"]].copy()
        return df

    def is_available(self) -> bool:
        """Indica si MT5 está inicializado y listo."""
        return bool(mt5 and self._initialized)
