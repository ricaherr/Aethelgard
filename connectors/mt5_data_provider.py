"""
Proveedor de datos OHLC desde MetaTrader 5.
Obtiene datos de forma autónoma vía copy_rates_from_pos, sin gráficas abiertas.
Usado por el Scanner Engine para ingestión proactiva.
ARCHITECTURE: Single source of truth = DATABASE (reads from broker_accounts)
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from data_vault.storage import StorageManager

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
    ARCHITECTURE: Configuration from DATABASE only (broker_accounts table)
    """

    def __init__(self, account_id: Optional[str] = None, login: Optional[int] = None, password: str = "", server: str = "", init_mt5: bool = True):
        """
        Initialize MT5 Data Provider
        
        Args:
            account_id: Optional account ID to load from DB. Preferred method.
            login: Legacy parameter for compatibility. If None, loads from DB.
            password: Legacy parameter for compatibility. If empty, loads from DB.
            server: Legacy parameter for compatibility. If empty, loads from DB.
            init_mt5: Whether to initialize MT5 on construction
        """
        self._initialized = False
        self.storage = StorageManager()
        self.account_id = account_id
        
        # Load from DB if account_id provided or no credentials given
        if account_id or (not login and not password):
            self._load_from_db()
        else:
            # Legacy mode: use provided credentials
            self.login = login
            self.password = str(password).strip() if password else ""
            self.server = str(server).strip() if server else ""
        
        self.init_mt5 = init_mt5
        
        if init_mt5 and mt5:
            self._try_initialize()
    
    def _load_from_db(self) -> None:
        """Load MT5 credentials from database"""
        try:
            all_accounts = self.storage.get_broker_accounts()
            mt5_accounts = [acc for acc in all_accounts if acc.get('platform_id') == 'mt5' and acc.get('enabled', True)]
            
            if not mt5_accounts:
                logger.warning("No MT5 accounts found in database")
                self.login = None
                self.password = ""
                self.server = ""
                return
            
            # Select account
            account = None
            if self.account_id:
                account = next((acc for acc in mt5_accounts if acc['account_id'] == self.account_id), None)
            else:
                account = mt5_accounts[0]
            
            if not account:
                logger.warning(f"MT5 account {self.account_id} not found")
                self.login = None
                self.password = ""
                self.server = ""
                return
            
            # Get credentials
            self.account_id = account['account_id']
            credentials = self.storage.get_credentials(self.account_id)
            
            self.login = int(account.get('login') or account.get('account_number'))
            self.server = str(account.get('server', '')).strip()
            self.password = str(credentials.get('password', '')).strip() if credentials else ""
            
            logger.info(f"MT5DataProvider loaded from DB: {account.get('account_name')} (Login: {self.login})")
            
        except Exception as e:
            logger.error(f"Error loading MT5 config from database: {e}", exc_info=True)
            self.login = None
            self.password = ""
            self.server = ""

    def _try_initialize(self) -> bool:
        """Intenta inicializar y loguear en MT5."""
        if not mt5:
            return False
            
        # Check if already initialized and healthy
        try:
            if self._initialized and mt5.terminal_info() is not None:
                return True
        except Exception:
            self._initialized = False

        if not mt5.initialize():
            logger.warning("MT5 no pudo inicializarse: %s", mt5.last_error())
            return False
            
        if self.login and self.server:
            try:
                authorized = mt5.login(
                    login=int(self.login),
                    password=self.password,
                    server=self.server
                )
                if not authorized:
                    logger.warning("MT5 no pudo autorizarse con login %s: %s", self.login, mt5.last_error())
                    return False
            except (ValueError, TypeError) as e:
                logger.error("Error en formato de login MT5: %s", e)
                return False
        
        self._initialized = True
        logger.info("MT5DataProvider listo. Versión MT5: %s", mt5.version())
        return True

    def shutdown(self) -> None:
        """Cierra la conexión con MT5."""
        if mt5 and self._initialized:
            mt5.shutdown()
            self._initialized = False
            logger.info("MT5DataProvider cerrado.")

    def _resolve_timeframe(self, timeframe: str) -> int:
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
            if not self._try_initialize():
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
