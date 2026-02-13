"""
Trifecta Logic Module for Aethelgard
Based on Oliver Velez's 2m-5m-15m Alignment Strategy.
Optimized with: Location, Narrow State, and Time of Day rules.

ARCHITECTURE:
- Pure business logic (NO broker imports allowed - agnóstico)
- Receives pandas DataFrames for M1, M5, M15
- Returns Dict with validation result, direction, score, metadata
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TrifectaAnalyzer:
    """
    Analiza la alineación fractal (Trifecta) y la calidad del setup (Location).
    
    Core Rules (Oliver Velez):
    1. Alignment: Precio debe estar en mismo lado de SMA20 en M1, M5, M15
    2. Location: Precio no debe estar extendido >1% de SMA20
    3. Narrow State: SMA20 cerca de SMA200 (<1.5%) = setup explosivo
    4. Time of Day: Evitar Midday Doldrums (11:30-14:00 EST)
    """

    def __init__(self):
        self.micro_tf = "M1"  # Proxy para 2m (MT5 usa M1)
        self.mid_tf = "M5"
        self.macro_tf = "M15"
        
        # Oliver Velez Time Zones (EST - Eastern Standard Time)
        self.open_start = time(9, 30)
        self.doldrums_start = time(11, 30)
        self.doldrums_end = time(14, 00)
        self.close_end = time(16, 00)

    def analyze(self, symbol: str, market_data: Dict[str, pd.DataFrame]) -> Dict:
        """
        Ejecuta el análisis completo de Trifecta + Optimizaciones.
        
        Args:
            symbol: Symbol to analyze (e.g., "EURUSD")
            market_data: Dict with DataFrames for each timeframe
                        {"M1": df1, "M5": df5, "M15": df15}
        
        Returns:
            Dict with keys:
                - valid (bool): True if setup is valid
                - direction (str): "BUY" or "SELL"
                - score (float): 0-100 scoring
                - reason (str): Rejection reason if valid=False
                - metadata (dict): Additional data (is_narrow, in_doldrums, etc.)
        """
        if not self._validate_data(market_data):
            return {"valid": False, "reason": "Insufficient Data"}

        # 1. Análisis Técnico por Timeframe
        micro = self._analyze_tf(market_data[self.micro_tf])
        mid = self._analyze_tf(market_data[self.mid_tf])
        macro = self._analyze_tf(market_data[self.macro_tf])

        # 2. Verificar Alineación (Trifecta Core)
        # Bullish: Precio > SMA20 en los 3 timeframes
        is_bullish = micro['bullish'] and mid['bullish'] and macro['bullish']
        # Bearish: Precio < SMA20 en los 3 timeframes
        is_bearish = micro['bearish'] and mid['bearish'] and macro['bearish']

        if not (is_bullish or is_bearish):
            return {"valid": False, "reason": "No Alignment"}

        direction = "BUY" if is_bullish else "SELL"

        # 3. Optimización: Location (Extension from SMA 20)
        # Usamos el timeframe medio (M5) como referencia principal
        is_extended = mid['extension_pct'] > 1.0  # Si está > 1% lejos de SMA20, es peligroso
        if is_extended:
            return {"valid": False, "reason": "Extended from SMA20 (Rubber Band)"}

        # 4. Optimización: Narrow State (SMA 20 vs SMA 200)
        # Bonificación si las medias están comprimidas (potencial explosivo)
        is_narrow = mid['sma_diff_pct'] < 1.5
        
        # 5. Optimización: Elephant Bar / Momentum
        has_momentum = mid['elephant_candle'] or micro['elephant_candle']

        # 6. Optimización: Time of Day (Midday Doldrums)
        current_time = datetime.now().time()  # Nota: En producción ajustar a EST
        in_doldrums = self.doldrums_start <= current_time <= self.doldrums_end
        
        # --- SCORING SYSTEM (0-100) ---
        score = 50.0  # Base por alineación
        
        if is_narrow:
            score += 20.0      # +20 por Narrow State (Explosivo)
        if has_momentum:
            score += 15.0      # +15 por Vela Elefante
        if not in_doldrums:
            score += 15.0      # +15 por buen horario
        
        # Penalización por horario muerto
        if in_doldrums:
            score -= 20.0

        return {
            "valid": True,
            "direction": direction,
            "score": score,
            "metadata": {
                "is_narrow": is_narrow,
                "in_doldrums": in_doldrums,
                "extension_pct": mid['extension_pct'],
                "stop_loss_ref": mid['low'] if direction == "BUY" else mid['high']
            }
        }

    def _validate_data(self, data: Dict) -> bool:
        """
        Verifica que existen los 3 timeframes necesarios.
        """
        return all(tf in data for tf in [self.micro_tf, self.mid_tf, self.macro_tf])

    def _analyze_tf(self, df: pd.DataFrame) -> Dict:
        """
        Análisis técnico de un solo timeframe.
        
        Returns:
            Dict with: bullish, bearish, extension_pct, sma_diff_pct, 
                       elephant_candle, low, high
        """
        if df.empty or len(df) < 200:
            return {
                "bullish": False,
                "bearish": False,
                "extension_pct": 100.0,
                "sma_diff_pct": 100.0,
                "elephant_candle": False,
                "low": 0.0,
                "high": 0.0
            }

        close = df['close'].iloc[-1]
        open_p = df['open'].iloc[-1]
        high = df['high'].iloc[-1]
        low = df['low'].iloc[-1]
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]
        
        # Extension: Distancia precio a SMA20
        extension_pct = abs(close - sma20) / sma20 * 100
        
        # Narrow: Distancia SMA20 a SMA200
        sma_diff_pct = abs(sma20 - sma200) / sma200 * 100

        # Elephant Candle (Cuerpo > 2x promedio)
        body = abs(close - open_p)
        avg_body = (df['close'] - df['open']).abs().rolling(20).mean().iloc[-1]
        is_elephant = body > (avg_body * 2.0)

        return {
            "bullish": close > sma20,
            "bearish": close < sma20,
            "extension_pct": extension_pct,
            "sma_diff_pct": sma_diff_pct,
            "elephant_candle": is_elephant,
            "low": low,
            "high": high
        }
