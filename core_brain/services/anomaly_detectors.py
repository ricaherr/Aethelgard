"""
Anomaly Detection Algorithms
Detectores de volatilidad extrema, flash crashes y anomalías sistémicas.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd
import numpy as np

from core_brain.services.anomaly_models import AnomalyType

logger = logging.getLogger(__name__)


def detect_volatility_anomalies(
    symbol: str,
    df: pd.DataFrame,
    timeframe: str,
    volatility_zscore_threshold: float = 3.0,
) -> List[Dict[str, Any]]:
    """
    Detecta volatilidad extrema usando Z-Score en ventana móvil (30 velas).
    Umbrales: Z > 3.0 (3-sigma statistical outlier).
    
    Args:
        symbol: Instrumento
        df: DataFrame OHLC con columnas close
        timeframe: Temporalidad (M15, H1, etc)
        volatility_zscore_threshold: Threshold Z-Score (default 3.0)
        
    Returns:
        Lista de anomalías detectadas como dicts
    """
    anomalies: List[Dict[str, Any]] = []
    
    # Validación básica
    if df is None or df.empty or len(df) < 20:
        return anomalies
    
    try:
        # Calcular cambios de precio (retornos)
        df_clean = df.dropna(subset=['close'])
        if len(df_clean) < 20:
            return anomalies
        
        # Log-returns para mejor distribución normal
        returns = np.log(df_clean['close'] / df_clean['close'].shift(1))
        returns = returns.dropna()
        
        if len(returns) < 10:
            return anomalies
        
        # Z-Score usando ventana móvil (rolling 30 velas)
        window = min(30, len(returns) - 1)
        rolling_mean = returns.rolling(window=window, min_periods=1).mean()
        rolling_std = returns.rolling(window=window, min_periods=1).std()
        
        # Evitar división por cero
        rolling_std = rolling_std.replace(0, rolling_std[rolling_std > 0].mean() or 0.0001)
        
        z_scores = (returns - rolling_mean) / rolling_std
        
        # Detectar anomalías (Z-Score > threshold)
        anomaly_indices = np.where(np.abs(z_scores) > volatility_zscore_threshold)[0]
        
        for idx in anomaly_indices:
            # Asegurar que hay suficiente contexto
            if idx < len(df_clean):
                row = df_clean.iloc[idx]
                timestamp = row.get('timestamp', datetime.now())
                z_score = abs(z_scores.iloc[idx])
                
                # Validez de timestamp
                if not isinstance(timestamp, datetime):
                    timestamp = datetime.now()
                
                # Calcular confianza basada en magnitud de Z-Score
                confidence = min(1.0, z_score / 5.0)
                
                anomaly = {
                    "symbol": symbol,
                    "anomaly_type": AnomalyType.EXTREME_VOLATILITY.value,
                    "timestamp": timestamp,
                    "z_score": float(z_score),
                    "confidence": float(confidence),
                    "drop_percentage": 0.0,
                    "volume_spike_detected": False,
                    "trace_id": f"AN-{uuid.uuid4().hex[:8].upper()}",
                    "details": {
                        "timeframe": timeframe,
                        "return_magnitude": float(returns.iloc[idx]) if idx < len(returns) else 0.0,
                        "rolling_std": float(rolling_std.iloc[idx]) if idx < len(rolling_std) else 0.0,
                        "detection_method": "z_score_rolling",
                    }
                }
                anomalies.append(anomaly)
                logger.warning(
                    f"[ANOMALY_DETECTED] EXTREME_VOLATILITY: {symbol} Z={z_score:.2f} "
                    f"on {timeframe} @ {timestamp}. Trace_ID: {anomaly['trace_id']}"
                )
        
    except Exception as e:
        logger.error(f"[DETECTOR] Error in detect_volatility_anomalies: {e}")
    
    return anomalies


def detect_flash_crashes(
    symbol: str,
    df: pd.DataFrame,
    timeframe: str,
    flash_crash_threshold: float = -2.0,
    volume_percentile: int = 90,
) -> List[Dict[str, Any]]:
    """
    Detecta Flash Crashes: caída > -2% en una sola vela con volumen anómalo.
    
    Args:
        symbol: Instrumento
        df: DataFrame OHLC
        timeframe: Temporalidad
        flash_crash_threshold: Threshold % change (default -2%)
        volume_percentile: Percentil para detección de spike (default 90th)
        
    Returns:
        Lista de anomalías Flash Crash
    """
    anomalies: List[Dict[str, Any]] = []
    
    if df is None or df.empty or len(df) < 5:
        return anomalies
    
    try:
        df_clean = df.dropna(subset=['close', 'open', 'volume'])
        if len(df_clean) < 5:
            return anomalies
        
        # Calcular cambio de precio (open -> close)
        price_change_pct = ((df_clean['close'] - df_clean['open']) / df_clean['open']) * 100
        
        # Detectar caídas > threshold
        crash_indices = np.where(price_change_pct < flash_crash_threshold)[0]
        
        # Calcular volumen medio para detectar spike
        volume_threshold = np.percentile(df_clean['volume'], volume_percentile)
        
        for idx in crash_indices:
            row = df_clean.iloc[idx]
            timestamp = row.get('timestamp', datetime.now())
            if not isinstance(timestamp, datetime):
                timestamp = datetime.now()
            
            volume_spike_detected = row['volume'] > volume_threshold
            drop_pct = float(price_change_pct.iloc[idx])
            
            anomaly = {
                "symbol": symbol,
                "anomaly_type": AnomalyType.FLASH_CRASH.value,
                "timestamp": timestamp,
                "z_score": 0.0,
                "confidence": min(1.0, abs(drop_pct) / 5.0),
                "drop_percentage": drop_pct,
                "volume_spike_detected": volume_spike_detected,
                "trace_id": f"AN-{uuid.uuid4().hex[:8].upper()}",
                "details": {
                    "timeframe": timeframe,
                    "open": float(row['open']),
                    "close": float(row['close']),
                    "volume": float(row['volume']),
                    "volume_threshold": float(volume_threshold),
                    "detection_method": "single_candle_drop",
                }
            }
            anomalies.append(anomaly)
            logger.warning(
                f"[ANOMALY_DETECTED] FLASH_CRASH: {symbol} drop={drop_pct:.2f}% "
                f"on {timeframe} @ {timestamp}. Vol_spike: {volume_spike_detected}. "
                f"Trace_ID: {anomaly['trace_id']}"
            )
        
    except Exception as e:
        logger.error(f"[DETECTOR] Error in detect_flash_crashes: {e}")
    
    return anomalies
