"""
Clasificador de Régimen de Mercado Optimizado
Analiza volatilidad y tendencia para determinar el modo de operación
Usa pandas para cálculos vectorizados eficientes

Incluye: filtro de volatilidad mínima, histéresis ADX, suavizado de shock,
y filtro de persistencia (2 velas consecutivas).
"""
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
import json
import logging
from models.signal import MarketRegime
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class RegimeClassifier:
    """
    Clasifica el régimen de mercado basándose en:
    - Volatilidad (desviación estándar de retornos, umbral mínimo vía ATR)
    - Tendencia (ADX con histéresis: entrar TREND >25, salir RANGE <18)
    - Movimientos extremos (shock: +500% volatilidad en 5 velas, solo si vol > ATR base)
    - Sesgo a largo plazo (distancia a SMA 200)
    - Persistencia: cambio confirmado solo tras 2 velas consecutivas
    """
    
    # Class-level cache for parameters (singleton pattern)
    _params_cache: Dict[str, Dict] = {}
    
    @staticmethod
    def _load_params_from_config(config_path: str = "config/dynamic_params.json", force_reload: bool = False) -> Dict:
        """
        Carga parámetros desde el archivo de configuración dinámica.
        Usa cache para evitar lecturas repetidas del disco.
        
        Args:
            config_path: Ruta al archivo de configuración
            force_reload: Si True, ignora cache y recarga desde archivo
        
        Returns:
            Diccionario con los parámetros cargados
        """
        # Check cache first (unless force_reload requested)
        if not force_reload and config_path in RegimeClassifier._params_cache:
            return RegimeClassifier._params_cache[config_path]
        
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.warning(f"Archivo de configuración no encontrado: {config_path}. Usando valores por defecto.")
            return {}
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"Parámetros cargados desde {config_path}")
                
                # Cache the loaded config
                RegimeClassifier._params_cache[config_path] = config
                return config
        except Exception as e:
            logger.error(f"Error cargando configuración desde {config_path}: {e}. Usando valores por defecto.")
            return {}
    
    @staticmethod
    def reload_params():
        """
        Invalida cache de parámetros para forzar recarga.
        Útil cuando dynamic_params.json es modificado por EdgeTuner.
        """
        RegimeClassifier._params_cache.clear()
        logger.info("Parameter cache cleared. Next classifier will reload from file.")
    
    def __init__(self, 
                 adx_period: Optional[int] = None,
                 sma_period: Optional[int] = None,
                 adx_trend_threshold: Optional[float] = None,
                 adx_range_threshold: Optional[float] = None,
                 adx_range_exit_threshold: Optional[float] = None,
                 volatility_shock_multiplier: Optional[float] = None,
                 shock_lookback: Optional[int] = None,
                 min_volatility_atr_period: Optional[int] = None,
                 persistence_candles: Optional[int] = None,
                 config_path: str = "config/dynamic_params.json"):
        """
        Inicializa el clasificador. Los parámetros se cargan desde config/dynamic_params.json
        si no se proporcionan explícitamente.
        
        Args:
            adx_period: Período para cálculo de ADX (se carga desde config si es None)
            sma_period: Período para SMA de largo plazo (se carga desde config si es None)
            adx_trend_threshold: ADX > este valor para ENTRAR en TREND (se carga desde config si es None)
            adx_range_threshold: ADX < este valor para ENTRAR en RANGE cuando no en TREND (se carga desde config si es None)
            adx_range_exit_threshold: ADX < este valor para SALIR de TREND a RANGE (se carga desde config si es None)
            volatility_shock_multiplier: Multiplicador para detectar shock (se carga desde config si es None)
            shock_lookback: Número de velas para comparar volatilidad (se carga desde config si es None)
            min_volatility_atr_period: Período ATR largo plazo como umbral base de volatilidad (se carga desde config si es None)
            persistence_candles: Velas consecutivas requeridas para confirmar cambio (se carga desde config si es None)
            config_path: Ruta al archivo de configuración dinámica
        """
        # Cargar configuración desde archivo
        config = self._load_params_from_config(config_path)
        
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
        
        self.config_path = config_path
        
        # DataFrame para almacenar datos OHLC
        self.df: Optional[pd.DataFrame] = None
        self.max_history = 300  # Mantener suficientes datos para SMA 200
        
        # Estado para persistencia e histéresis
        self._confirmed_regime: Optional[MarketRegime] = None
        self._pending_regime: Optional[MarketRegime] = None
        self._pending_count: int = 0
        self._last_classify_len: int = 0
    
    def add_candle(self, 
                   close: float,
                   high: Optional[float] = None,
                   low: Optional[float] = None,
                   open_price: Optional[float] = None,
                   timestamp: Optional[datetime] = None):
        """
        Añade una vela al historial para análisis
        
        Args:
            close: Precio de cierre (requerido)
            high: Precio máximo (opcional, se usa close si no se proporciona)
            low: Precio mínimo (opcional, se usa close si no se proporciona)
            open_price: Precio de apertura (opcional, se usa close si no se proporciona)
            timestamp: Timestamp de la vela (opcional)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Si no se proporcionan high/low/open, usar close como aproximación
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
        
        # Mantener solo el historial reciente
        if len(self.df) > self.max_history:
            self.df = self.df.tail(self.max_history).reset_index(drop=True)
    
    def add_price(self, price: float, timestamp: Optional[datetime] = None):
        """
        Método de compatibilidad: añade solo precio (se usa como close)
        Para mejor precisión, usar add_candle() con datos OHLC completos
        """
        self.add_candle(close=price, timestamp=timestamp)
    
    def _calculate_adx(self) -> float:
        """
        Calcula el ADX (Average Directional Index) correctamente usando pandas
        Implementa el método de suavizado de Wilder para ATR, +DI, -DI y ADX
        
        Returns:
            Valor de ADX entre 0-100, o 0.0 si no hay suficientes datos
        """
        if self.df is None or len(self.df) < self.adx_period * 2:
            return 0.0
        
        df = self.df.copy()
        period = self.adx_period
        
        # Calcular True Range (TR)
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # Calcular Directional Movement
        df['plus_dm'] = df['high'].diff()
        df['minus_dm'] = -df['low'].diff()
        
        # Filtrar movimientos direccionales según reglas de ADX
        # +DM solo cuenta si es mayor que -DM y positivo
        # -DM solo cuenta si es mayor que +DM y positivo
        df.loc[(df['plus_dm'] <= df['minus_dm']) | (df['plus_dm'] < 0), 'plus_dm'] = 0
        df.loc[(df['minus_dm'] <= df['plus_dm']) | (df['minus_dm'] < 0), 'minus_dm'] = 0
        
        # Calcular ATR usando Wilder's Smoothing
        # Primera vez: suma simple de los primeros 'period' valores
        # Después: ATR = (ATR_previo * (period - 1) + TR_actual) / period
        atr = pd.Series(index=df.index, dtype=float)
        atr.iloc[period-1] = df['tr'].iloc[:period].sum() / period
        
        for i in range(period, len(df)):
            atr.iloc[i] = (atr.iloc[i-1] * (period - 1) + df['tr'].iloc[i]) / period
        
        # Calcular +DI y -DI usando Wilder's Smoothing
        plus_dm_smooth = pd.Series(index=df.index, dtype=float)
        minus_dm_smooth = pd.Series(index=df.index, dtype=float)
        
        plus_dm_smooth.iloc[period-1] = df['plus_dm'].iloc[:period].sum() / period
        minus_dm_smooth.iloc[period-1] = df['minus_dm'].iloc[:period].sum() / period
        
        for i in range(period, len(df)):
            plus_dm_smooth.iloc[i] = (plus_dm_smooth.iloc[i-1] * (period - 1) + df['plus_dm'].iloc[i]) / period
            minus_dm_smooth.iloc[i] = (minus_dm_smooth.iloc[i-1] * (period - 1) + df['minus_dm'].iloc[i]) / period
        
        # Calcular +DI y -DI como porcentaje del ATR
        plus_di = 100 * (plus_dm_smooth / atr)
        minus_di = 100 * (minus_dm_smooth / atr)
        
        # Calcular DX (Directional Index)
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        dx = 100 * (di_diff / di_sum.replace(0, np.nan))
        
        # Calcular ADX usando Wilder's Smoothing de DX
        adx = pd.Series(index=df.index, dtype=float)
        adx.iloc[period*2-2] = dx.iloc[period-1:period*2-1].mean()
        
        for i in range(period*2-1, len(df)):
            adx.iloc[i] = (adx.iloc[i-1] * (period - 1) + dx.iloc[i]) / period
        
        # Retornar el último valor de ADX
        return float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
    
    def _calculate_volatility(self, window: int = 20) -> float:
        """
        Calcula la volatilidad basada en desviación estándar de retornos usando pandas
        
        Args:
            window: Ventana de tiempo para el cálculo (default: 20)
        
        Returns:
            Volatilidad (desviación estándar de retornos)
        """
        if self.df is None or len(self.df) < window + 1:
            return 0.0
        
        df = self.df.copy()
        df['returns'] = df['close'].pct_change()
        
        # Calcular desviación estándar de retornos en la ventana
        volatility = df['returns'].tail(window).std()
        
        return float(volatility) if not pd.isna(volatility) else 0.0
    
    def _get_atr_pct(self, period: Optional[int] = None) -> float:
        """
        ATR como porcentaje del precio (volatilidad base de largo plazo).
        Se usa como umbral mínimo para activar detección de shock.
        
        Args:
            period: Período ATR (default: min_volatility_atr_period)
        
        Returns:
            ATR / close actual, en decimal (ej. 0.005 = 0.5%)
        """
        period = period or self.min_volatility_atr_period
        if self.df is None or len(self.df) < period + 1:
            return 0.0
        
        df = self.df.copy()
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = (df['high'] - df['prev_close']).abs()
        df['tr3'] = (df['low'] - df['prev_close']).abs()
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        atr = df['tr'].rolling(window=period).mean().iloc[-1]
        close = df['close'].iloc[-1]
        if pd.isna(atr) or close <= 0:
            return 0.0
        return float(atr / close)
    
    def _detect_volatility_shock(self) -> bool:
        """
        Detecta shock solo si:
        1. Volatilidad actual supera umbral base (ATR largo plazo) — evita falsos CRASH en mercados muertos.
        2. La volatilidad aumentó >= multiplicador (ej. 5x) en las últimas N velas (ej. 5).
        
        Returns:
            True si se detecta un shock/crash
        """
        n = self.shock_lookback * 2
        if self.df is None or len(self.df) < n + max(20, self.min_volatility_atr_period):
            return False
        
        df = self.df.copy()
        df['returns'] = df['close'].pct_change()
        
        current_volatility = df['returns'].tail(self.shock_lookback).std()
        base_volatility = df['returns'].iloc[-n:-self.shock_lookback].std()
        
        if base_volatility == 0 or pd.isna(base_volatility) or pd.isna(current_volatility):
            return False
        
        # Filtro de volatilidad mínima: no activar shock si el mercado está "muerto"
        atr_pct = self._get_atr_pct()
        if current_volatility < atr_pct:
            return False
        
        volatility_increase = current_volatility / base_volatility
        return volatility_increase >= self.volatility_shock_multiplier
    
    def _calculate_sma_distance(self) -> Optional[float]:
        """
        Calcula la distancia porcentual del precio actual a la SMA 200
        
        Returns:
            Distancia porcentual (positiva = por encima, negativa = por debajo)
            None si no hay suficientes datos
        """
        if self.df is None or len(self.df) < self.sma_period:
            return None
        
        df = self.df.copy()
        df['sma'] = df['close'].rolling(window=self.sma_period).mean()
        
        current_price = df['close'].iloc[-1]
        sma_value = df['sma'].iloc[-1]
        
        if pd.isna(sma_value):
            return None
        
        # Calcular distancia porcentual
        distance = ((current_price - sma_value) / sma_value) * 100
        
        return float(distance)
    
    def get_bias(self) -> Optional[str]:
        """
        Determina el sesgo alcista o bajista basado en la distancia a SMA 200
        
        Returns:
            'BULLISH' si precio > SMA 200, 'BEARISH' si precio < SMA 200, None si no hay datos
        """
        distance = self._calculate_sma_distance()
        
        if distance is None:
            return None
        
        return 'BULLISH' if distance > 0 else 'BEARISH'
    
    def _classify_raw(self, last_confirmed: Optional[MarketRegime]) -> MarketRegime:
        """
        Clasificación "instantánea" sin persistencia.
        Usa histéresis ADX: entrar TREND > 25, salir TREND -> RANGE < 18.
        
        Args:
            last_confirmed: Último régimen confirmado (para histéresis)
        
        Returns:
            Régimen raw según ADX y shock
        """
        if self.df is None or len(self.df) < max(self.adx_period * 2, 20):
            return MarketRegime.NORMAL
        
        if self._detect_volatility_shock():
            return MarketRegime.CRASH
        
        adx = self._calculate_adx()
        in_trend = last_confirmed == MarketRegime.TREND
        
        if in_trend:
            # Histéresis: para salir de TREND, ADX debe caer por debajo de 18
            if adx < self.adx_range_exit_threshold:
                return MarketRegime.RANGE
            return MarketRegime.TREND
        
        # No en TREND: entrar TREND > 25, entrar RANGE < 20
        if adx > self.adx_trend_threshold:
            return MarketRegime.TREND
        if adx < self.adx_range_threshold:
            return MarketRegime.RANGE
        return MarketRegime.NORMAL
    
    def classify(self, 
                 current_price: Optional[float] = None,
                 high: Optional[float] = None,
                 low: Optional[float] = None,
                 open_price: Optional[float] = None) -> MarketRegime:
        """
        Clasifica el régimen de mercado actual.
        Un cambio solo se confirma si se mantiene al menos persistence_candles velas consecutivas.
        
        Args:
            current_price: Precio actual (opcional, se añade al historial como close)
            high: Precio máximo (opcional)
            low: Precio mínimo (opcional)
            open_price: Precio de apertura (opcional)
        
        Returns:
            MarketRegime: Régimen confirmado
        """
        if current_price is not None:
            self.add_candle(
                close=current_price,
                high=high,
                low=low,
                open_price=open_price
            )
        
        n = len(self.df) if self.df is not None else 0
        if n < max(self.adx_period * 2, 20):
            return MarketRegime.NORMAL
        
        # Re-evaluación sin nueva vela (ej. get_metrics): no actualizar persistencia
        if n == self._last_classify_len:
            return self._confirmed_regime or MarketRegime.NORMAL
        self._last_classify_len = n
        
        raw = self._classify_raw(self._confirmed_regime)
        
        if self._confirmed_regime is None:
            self._confirmed_regime = raw
            self._pending_regime = None
            self._pending_count = 0
            return self._confirmed_regime
        
        if raw == self._confirmed_regime:
            self._pending_regime = None
            self._pending_count = 0
            return self._confirmed_regime
        
        if raw == self._pending_regime:
            self._pending_count += 1
            if self._pending_count >= self.persistence_candles:
                self._confirmed_regime = raw
                self._pending_regime = None
                self._pending_count = 0
                return self._confirmed_regime
            return self._confirmed_regime
        
        self._pending_regime = raw
        self._pending_count = 1
        return self._confirmed_regime
    
    def get_metrics(self) -> Dict:
        """
        Retorna un diccionario con todas las métricas calculadas
        
        Returns:
            Diccionario con: adx, volatility, sma_distance, bias, regime, atr_pct, etc.
        """
        if self.df is None or len(self.df) < max(self.adx_period * 2, 20):
            return {
                'adx': 0.0,
                'volatility': 0.0,
                'sma_distance': None,
                'bias': None,
                'regime': MarketRegime.NORMAL.value,
                'volatility_shock_detected': False,
                'atr_pct': 0.0,
            }
        
        return {
            'adx': self._calculate_adx(),
            'volatility': self._calculate_volatility(),
            'sma_distance': self._calculate_sma_distance(),
            'bias': self.get_bias(),
            'regime': self.classify().value,
            'volatility_shock_detected': self._detect_volatility_shock(),
            'atr_pct': self._get_atr_pct(),
        }
    
    def reload_params(self):
        """Recarga los parámetros desde el archivo de configuración"""
        config = self._load_params_from_config(self.config_path)
        
        self.adx_period = config.get("adx_period", self.adx_period)
        self.sma_period = config.get("sma_period", self.sma_period)
        self.adx_trend_threshold = config.get("adx_trend_threshold", self.adx_trend_threshold)
        self.adx_range_threshold = config.get("adx_range_threshold", self.adx_range_threshold)
        self.adx_range_exit_threshold = config.get("adx_range_exit_threshold", self.adx_range_exit_threshold)
        self.volatility_shock_multiplier = config.get("volatility_shock_multiplier", self.volatility_shock_multiplier)
        self.shock_lookback = config.get("shock_lookback", self.shock_lookback)
        self.min_volatility_atr_period = config.get("min_volatility_atr_period", self.min_volatility_atr_period)
        self.persistence_candles = config.get("persistence_candles", self.persistence_candles)
        
        logger.info("Parámetros recargados desde configuración")
    
    def reset(self):
        """Resetea el historial y el estado de persistencia/histéresis"""
        self.df = None
        self._confirmed_regime = None
        self._pending_regime = None
        self._pending_count = 0
        self._last_classify_len = 0

    def load_ohlc(self, df: pd.DataFrame):
        """
        Reemplaza el historial OHLC interno con el DataFrame proporcionado.
        Resetea el estado de persistencia/histéresis.
        Útil para ingestión masiva (ej. mt5.copy_rates_from_pos) en escáner proactivo.

        Args:
            df: DataFrame con columnas 'timestamp' (o 'time'), 'open', 'high', 'low', 'close'.
                Si tiene 'time' (epoch), se convierte a datetime.
        """
        if df is None or len(df) == 0:
            self.df = None
        else:
            d = df.copy()
            if "timestamp" not in d.columns and "time" in d.columns:
                d["timestamp"] = pd.to_datetime(d["time"], unit="s")
            if "timestamp" not in d.columns:
                raise ValueError("DataFrame debe tener 'timestamp' o 'time'")
            cols = ["timestamp", "open", "high", "low", "close"]
            for c in cols:
                if c not in d.columns:
                    raise ValueError(f"DataFrame debe tener columna '{c}'")
            self.df = d[cols].tail(self.max_history).reset_index(drop=True)
        self._confirmed_regime = None
        self._pending_regime = None
        self._pending_count = 0
        self._last_classify_len = 0
