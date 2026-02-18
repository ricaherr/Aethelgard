"""
Clasificador de Régimen de Mercado Optimizado
Analiza volatilidad y tendencia para determinar el modo de operación.
"""
from typing import List, Optional, Dict
from datetime import datetime
import logging
import pandas as pd
import numpy as np

from models.signal import MarketRegime
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class RegimeClassifier:
    """
    Clasifica el régimen de mercado basándose en:
    - Volatilidad (ADX, ATR)
    - Tendencia (SMA 200)
    - Shocks de volatilidad
    """
    
    # Class-level cache for parameters
    _params_cache: Dict[str, Dict] = {}
    
    @staticmethod
    def _load_params_from_storage(storage: Optional[StorageManager] = None) -> Dict:
        """
        Carga parámetros desde Storage (SSOT) o usa valores por defecto.
        """
        if storage:
            return storage.get_dynamic_params()
        return {}
    
    def __init__(self, 
                 storage: Optional[StorageManager] = None,
                 adx_period: Optional[int] = None,
                 sma_period: Optional[int] = None,
                 adx_trend_threshold: Optional[float] = None,
                 adx_range_threshold: Optional[float] = None,
                 adx_range_exit_threshold: Optional[float] = None,
                 volatility_shock_multiplier: Optional[float] = None,
                 shock_lookback: Optional[int] = None,
                 min_volatility_atr_period: Optional[int] = None,
                 persistence_candles: Optional[int] = None):
        """
        Inicializa el clasificador.
        """
        # Cargar configuración (SSOT)
        config = self._load_params_from_storage(storage)
        
        # Usar valores de configuración si no se proporcionan explícitamente
        self.adx_period = adx_period if adx_period is not None else config.get("adx_period", 14)
        self.sma_period = sma_period if sma_period is not None else config.get("sma_period", 200)
        self.adx_trend_threshold = adx_trend_threshold if adx_trend_threshold is not None else config.get("adx_trend_threshold", 25.0)
        self.adx_range_threshold = adx_range_threshold if adx_range_threshold is not None else config.get("adx_range_threshold", 20.0)
        self.adx_range_exit_threshold = adx_range_exit_threshold if adx_range_exit_threshold is not None else config.get("adx_range_exit_threshold", 18.0)
        self.volatility_shock_multiplier = volatility_shock_multiplier if volatility_shock_multiplier is not None else config.get("volatility_shock_multiplier", 5.0)
        self.shock_lookback = shock_lookback if shock_lookback is not None else config.get("shock_lookback", 5)
        self.min_volatility_atr_period = min_volatility_atr_period if min_volatility_atr_period is not None else config.get("min_volatility_atr_period", 50)
        self.persistence_candles = persistence_candles if persistence_candles is not None else config.get("persistence_candles", 2)
        
        self.storage = storage
        self.df: Optional[pd.DataFrame] = None
        self.max_history = 300
        
        # Estado para persistencia
        self._confirmed_regime: Optional[MarketRegime] = None
        self._pending_regime: Optional[MarketRegime] = None
        self._pending_count: int = 0
        self._last_classify_len: int = 0
    
    def add_candle(self, 
                   close: float,
                   high: Optional[float] = None,
                   low: Optional[float] = None,
                   open_price: Optional[float] = None,
                   timestamp: Optional[datetime] = None) -> None:
        if timestamp is None:
            timestamp = datetime.now()
        
        high = high if high is not None else close
        low = low if low is not None else close
        open_price = open_price if open_price is not None else close
        
        new_row = pd.DataFrame({
            'timestamp': [timestamp],
            'open': [open_price],
            'high': [high],
            'low': [low],
            'close': [close]
        })
        
        if self.df is None:
            self.df = new_row
        else:
            self.df = pd.concat([self.df, new_row], ignore_index=True)
        
        if len(self.df) > self.max_history:
            self.df = self.df.tail(self.max_history).reset_index(drop=True)
    
    def _calculate_indicators(self) -> None:
        if self.df is None or len(self.df) < self.adx_period:
            return

        from core_brain.tech_utils import TechnicalAnalyzer
        self.df['adx'] = TechnicalAnalyzer.calculate_adx(self.df, self.adx_period)
        self.df['atr'] = TechnicalAnalyzer.calculate_atr(self.df, self.min_volatility_atr_period)
        self.df['volatility'] = TechnicalAnalyzer.calculate_volatility(self.df, 20)
        self.df['sma_200'] = TechnicalAnalyzer.calculate_sma(self.df, self.sma_period)

    def _get_latest_adx(self) -> float:
        if self.df is None or 'adx' not in self.df.columns:
            self._calculate_indicators()
        
        if self.df is not None and not self.df.empty:
            val = self.df['adx'].iloc[-1]
            return float(val) if not pd.isna(val) else 0.0
        return 0.0

    def _get_atr_pct(self) -> float:
        if self.df is None or 'atr' not in self.df.columns:
            self._calculate_indicators()
            
        if self.df is not None and not self.df.empty:
            atr = self.df['atr'].iloc[-1]
            current_price = self.df['close'].iloc[-1]
            if current_price > 0:
                return float((atr / current_price) * 100)
        return 0.0
    
    def _detect_volatility_shock(self) -> bool:
        n = self.shock_lookback * 2
        if self.df is None or len(self.df) < n + max(20, self.min_volatility_atr_period):
            return False
        
        df = self.df.copy()
        df['returns'] = df['close'].pct_change()
        
        current_volatility = df['returns'].tail(self.shock_lookback).std()
        base_volatility = df['returns'].iloc[-n:-self.shock_lookback].std()
        
        if base_volatility == 0 or pd.isna(base_volatility) or pd.isna(current_volatility):
            return False
        
        atr_pct = self._get_atr_pct()
        if current_volatility < atr_pct:
            return False
        
        return (current_volatility / base_volatility) >= self.volatility_shock_multiplier
    
    def _calculate_sma_distance(self) -> Optional[float]:
        if self.df is None or 'sma_200' not in self.df.columns:
            self._calculate_indicators()
            
        if self.df is not None and not self.df.empty:
            current_price = self.df['close'].iloc[-1]
            sma_value = self.df['sma_200'].iloc[-1]
            if not pd.isna(sma_value) and sma_value > 0:
                return float(((current_price - sma_value) / sma_value) * 100)
        return None
    
    def get_bias(self) -> Optional[str]:
        distance = self._calculate_sma_distance()
        if distance is None: return None
        return 'BULLISH' if distance > 0 else 'BEARISH'
    
    def _classify_raw(self, last_confirmed: Optional[MarketRegime]) -> MarketRegime:
        if self.df is None or len(self.df) < max(self.adx_period * 2, 20):
            return MarketRegime.NORMAL
        
        if self._detect_volatility_shock():
            return MarketRegime.CRASH
        
        adx = self._get_latest_adx()
        if last_confirmed == MarketRegime.TREND:
            if adx < self.adx_range_exit_threshold:
                return MarketRegime.RANGE
            return MarketRegime.TREND
        
        if adx > self.adx_trend_threshold:
            return MarketRegime.TREND
        if adx < self.adx_range_threshold:
            return MarketRegime.RANGE
        return MarketRegime.NORMAL
    
    def classify(self, current_price: Optional[float] = None) -> MarketRegime:
        if current_price is not None:
            self.add_candle(close=current_price)
        
        n = len(self.df) if self.df is not None else 0
        if n < max(self.adx_period * 2, 20):
            return MarketRegime.NORMAL
        
        if n == self._last_classify_len:
            return self._confirmed_regime or MarketRegime.NORMAL
        self._last_classify_len = n
        
        raw = self._classify_raw(self._confirmed_regime)
        if self._confirmed_regime is None or raw == self._confirmed_regime:
            self._confirmed_regime = raw
            self._pending_regime = None
            self._pending_count = 0
            return raw
        
        if raw == self._pending_regime:
            self._pending_count += 1
            if self._pending_count >= self.persistence_candles:
                self._confirmed_regime = raw
                return raw
        else:
            self._pending_regime = raw
            self._pending_count = 1
            
        return self._confirmed_regime
    
    def reload_params(self) -> None:
        config = self._load_params_from_storage(self.storage)
        self.adx_period = config.get("adx_period", self.adx_period)
        self.sma_period = config.get("sma_period", self.sma_period)
        logger.info("[OK] Parámetros de régimen recargados desde Storage")

    def load_ohlc(self, df: pd.DataFrame) -> None:
        if df is None or len(df) == 0:
            self.df = None
        else:
            d = df.copy()
            if "timestamp" not in d.columns and "time" in d.columns:
                d["timestamp"] = pd.to_datetime(d["time"], unit="s")
            self.df = d[["timestamp", "open", "high", "low", "close"]].tail(self.max_history).reset_index(drop=True)
        self._confirmed_regime = None
        self._last_classify_len = 0
            
    def get_metrics(self) -> Dict[str, Any]:
        """
        Devuelve métricas actuales del régimen.
        """
        return {
            "adx": self._get_latest_adx(),
            "atr_pct": self._get_atr_pct(),
            "volatility_shock": self._detect_volatility_shock(),
            "sma_distance": self._calculate_sma_distance(),
            "bias": self.get_bias()
        }
