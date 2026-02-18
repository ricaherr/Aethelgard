"""
Trifecta Logic Module for Aethelgard
Based on Oliver Velez's 2m-5m-15m Alignment Strategy.
Optimized with: Location, Narrow State, and Time of Day rules.

ARCHITECTURE:
- Pure business logic (NO broker imports allowed - agnóstico)
- Receives pandas DataFrames for M1, M5, M15
- Returns Dict with validation result, direction, score, metadata
- AUTONOMY: Auto-enables required timeframes if disabled (HYBRID approach)
"""
import logging
import json
from pathlib import Path
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
    
    HYBRID MODE:
    - Intenta auto-habilitar M1/M5/M15 en config.json (Autonomía)
    - Si falla o datos faltantes → opera en modo DEGRADADO (sin filtros Trifecta)
    """

    def __init__(self, config_path: str = "config/config.json", auto_enable_tfs: bool = True):
        """
        Args:
            config_path: Path to config.json for scanner configuration
            auto_enable_tfs: If True, attempts to auto-enable required timeframes
        """
        self.micro_tf = "M1"  # Proxy para 2m (MT5 usa M1)
        self.mid_tf = "M5"
        self.macro_tf = "M15"
        self.required_tfs = [self.micro_tf, self.mid_tf, self.macro_tf]
        self.config_path = config_path
        
        # Oliver Velez Time Zones (EST - Eastern Standard Time)
        self.open_start = time(9, 30)
        self.doldrums_start = time(11, 30)
        self.doldrums_end = time(14, 00)
        self.close_end = time(16, 00)
        
        # HYBRID MODE: Try to auto-enable required timeframes
        if auto_enable_tfs:
            try:
                self._ensure_required_timeframes()
            except Exception as e:
                logger.warning(
                    f"⚠️ TrifectaAnalyzer: Auto-enable failed ({e}). "
                    f"Will operate in DEGRADED mode if data is missing."
                )

    def analyze(self, symbol: str, market_data: Dict[str, pd.DataFrame]) -> Dict:
        """
        Ejecuta el análisis completo de Trifecta + Optimizaciones.
        
        HYBRID MODE: Si faltan timeframes → retorna en modo DEGRADED (permite señal base)
        
        Args:
            symbol: Symbol to analyze (e.g., "EURUSD")
            market_data: Dict with DataFrames for each timeframe
                        {"M1": df1, "M5": df5, "M15": df15}
        
        Returns:
            Dict with keys:
                - valid (bool): True if setup is valid (or degraded mode)
                - direction (str): "BUY"/"SELL"/"UNKNOWN" (unknown in degraded)
                - score (float): 0-100 scoring (50 neutral in degraded mode)
                - reason (str): Rejection reason if valid=False
                - metadata (dict): Additional data (degraded_mode, missing_timeframes)
        """
        # HYBRID FALLBACK 1: Check if required data is available
        if not self._validate_data(market_data):
            missing_tfs = [tf for tf in self.required_tfs if tf not in market_data]
            
            # REJECTION: No trades allowed without full Trifecta confluency
            reason = f"Insufficient Data - Missing {missing_tfs}. Trifecta alignment not verified."
            logger.warning(f"❌ [{symbol}] Signal rejected: {reason}")
            
            return {
                "valid": False,
                "direction": "UNKNOWN",
                "score": 0.0,
                "reason": reason,
                "metadata": {
                    "degraded_mode": False,
                    "missing_timeframes": missing_tfs,
                    "reason": reason
                }
            }

        # 1. Análisis Técnico por Timeframe
        micro = self._analyze_tf(market_data[self.micro_tf])
        mid = self._analyze_tf(market_data[self.mid_tf])
        macro = self._analyze_tf(market_data[self.macro_tf])

        # 2. Verificar Alineación Básica (Trifecta Core - Precio vs SMA20)
        # Primero validemos la alineación básica sin considerar jerarquía SMA200
        price_bullish = micro['bullish'] and mid['bullish'] and macro['bullish']
        price_bearish = micro['bearish'] and mid['bearish'] and macro['bearish']

        if not (price_bullish or price_bearish):
            return {"valid": False, "reason": "No Alignment"}
        
        # 2.1 Validar pendiente de SMA20 en los 3 timeframes (no debe estar plana)
        # Ejecutamos ANTES de validar jerarquía para dar feedback más específico
        # Umbral: slope mínimo de 0.005% en los 3 timeframes
        min_slope = 0.005
        for tf_name, tf_data in zip(["Micro", "Mid", "Macro"], [micro, mid, macro]):
            if tf_data['sma20_slope'] < min_slope:
                return {
                    "valid": False,
                    "reason": f"No Trend - {tf_name} EMA20 Flat (slope: {tf_data['sma20_slope']:.3f}% < {min_slope}%)"
                }

        # 2.2 ADAPTATIVO: Validar separación EMA20/EMA200 basada en ATR en los 3 timeframes
        for tf_name, tf_data in zip(["Micro", "Mid", "Macro"], [micro, mid, macro]):
            atr_threshold = tf_data['atr_pct'] * 0.3
            if not tf_data['emas_separated_atr']:
                return {
                    "valid": False,
                    "reason": f"No Trend - {tf_name} EMAs Too Close (sep: {tf_data['sma_diff_pct']:.3f}% < {atr_threshold:.3f}% [ATR-based])"
                }

        # 2.3 Validar Jerarquía SMA (Trap Zone Prevention)
        # CRÍTICO: Precio puede estar alineado (> SMA20) pero en tendencia contraria (SMA20 < SMA200)
        # Bullish requiere: Precio > SMA20 > SMA200 (jerarquía alcista completa)
        # Bearish requiere: Precio < SMA20 < SMA200 (jerarquía bajista completa)
        if price_bullish and mid['sma20_value'] < mid['sma200_value']:
            return {"valid": False, "reason": "Trap Zone (Bullish price in Bearish trend)"}
        
        if price_bearish and mid['sma20_value'] > mid['sma200_value']:
            return {"valid": False, "reason": "Trap Zone (Bearish price in Bullish trend)"}
        
        # Si llegamos aquí, tenemos alineación completa con jerarquía válida
        direction = "BUY" if price_bullish else "SELL"

        # NUEVO: Análisis de Fuerza de Tendencia
        from core_brain.tech_utils import TechnicalAnalyzer
        trend_class = TechnicalAnalyzer.classify_trend(market_data[self.mid_tf], 20, 200)
        trend_strength = TechnicalAnalyzer.calculate_trend_strength(market_data[self.mid_tf], 20, 200)

        # 3. Optimización: Location (Extension from SMA 20)
        # Usamos el timeframe medio (M5) como referencia principal
        # ATR Adaptativo: > 3.0 * ATR en lugar de 1% fijo
        max_extension = mid['atr_pct'] * 3.0
        is_extended = mid['extension_pct'] > max_extension
        if is_extended:
            return {"valid": False, "reason": f"Extended from SMA20 (Rubber Band): {mid['extension_pct']:.2f}% > {max_extension:.2f}% (3xATR)"}

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
        
        # NUEVO: Bonus/penalización por fuerza de tendencia
        if trend_class in ["UPTREND_STRONG", "DOWNTREND_STRONG"]:
            score += 15.0  # Tendencia fuerte = mayor probabilidad
        elif trend_class in ["UPTREND_WEAK", "DOWNTREND_WEAK"]:
            score += 5.0   # Tendencia débil = menor bonus
        elif trend_class == "SIDEWAYS":
            score -= 10.0  # Tendencia lateral = penalización (menor probabilidad)
        
        # Bonus adicional por strength_score (0-100 convertido a 0-10)
        score += (trend_strength["strength_score"] / 100.0) * 10.0

        return {
            "valid": True,
            "direction": direction,
            "score": score,
            "metadata": {
                "is_narrow": is_narrow,
                "in_doldrums": in_doldrums,
                "extension_pct": mid['extension_pct'],
                "stop_loss_ref": mid['low'] if direction == "BUY" else mid['high'],  # OV Original: Base de la vela
                "trend_classification": trend_class,
                "trend_strength_score": round(trend_strength["strength_score"], 1),
                "sma200_slope": round(trend_strength["slope_slow"], 3),
                "sma_separation_pct": round(trend_strength["separation_pct"], 2)
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
                       elephant_candle, low, high, sma20_slope, atr_pct, 
                       emas_separated_atr
        """
        if df.empty or len(df) < 200:
            return {
                "bullish": False,
                "bearish": False,
                "sma20_value": 0.0,
                "sma200_value": 0.0,
                "extension_pct": 100.0,
                "sma_diff_pct": 100.0,
                "elephant_candle": False,
                "low": 0.0,
                "high": 0.0,
                "sma20_slope": 0.0,
                "atr_pct": 0.0,
                "emas_separated_atr": False
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
        
        # Pendiente de SMA20 (slope) para detectar EMAs planas
        # Comparar SMA20 actual vs SMA20 hace 5 velas
        sma20_series = df['close'].rolling(20).mean()
        if len(sma20_series) >= 10:
            sma20_prev = sma20_series.iloc[-5]  # 5 velas atrás (ajustado para precisión)
            sma20_slope = abs(sma20 - sma20_prev) / sma20_prev * 100
        else:
            sma20_slope = 0.0
        
        # ATR (Average True Range) para separación adaptativa
        # TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        if len(df) >= 14:
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift(1)).abs()
            low_close = (df['low'] - df['close'].shift(1)).abs()
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]
            atr_pct = (atr / close) * 100 if close > 0 else 0.0
        else:
            atr_pct = 0.0
        
        # ADAPTATIVO: Separación mínima basada en ATR
        # Si ATR es alto (volátil), permitir menor separación relativa
        # Si ATR es bajo (consolidación), requerir más separación para confirmar tendencia
        # Umbral: separación debe ser > 30% del ATR
        min_separation_atr = atr_pct * 0.3 if atr_pct > 0 else 0.1  # Fallback 0.1%
        emas_separated_atr = sma_diff_pct >= min_separation_atr

        return {
            "bullish": close > sma20,
            "bearish": close < sma20,
            "sma20_value": sma20,      # Exponer para validación de jerarquía
            "sma200_value": sma200,    # Exponer para validación de jerarquía
            "extension_pct": extension_pct,
            "sma_diff_pct": sma_diff_pct,
            "elephant_candle": is_elephant,
            "low": low,
            "high": high,
            "sma20_slope": sma20_slope,
            "atr_pct": atr_pct,
            "emas_separated_atr": emas_separated_atr
        }
    
    def _ensure_required_timeframes(self) -> None:
        """
        Auto-habilita M1, M5, M15 en config.json si están deshabilitados.
        Coherente con Principio #1 de Autonomía de Aethelgard.
        
        Cambios se persisten a disco para que Scanner los detecte en próximo ciclo.
        """
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(
                    f"TrifectaAnalyzer: Config file {self.config_path} not found. "
                    f"Cannot auto-enable timeframes. Please enable {self.required_tfs} manually."
                )
                return
            
            # Read current config
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Get timeframes array from scanner config
            scanner_config = config.get("scanner", {})
            timeframes = scanner_config.get("timeframes", [])
            
            if not timeframes:
                logger.warning(
                    "TrifectaAnalyzer: No 'timeframes' array in config.json. "
                    "Cannot auto-enable. Please add M1, M5, M15 manually."
                )
                return
            
            # Check and enable required timeframes
            modified = False
            for tf_config in timeframes:
                tf_name = tf_config.get("timeframe")
                if tf_name in self.required_tfs and not tf_config.get("enabled", False):
                    logger.warning(
                        f"🔧 TrifectaAnalyzer: Auto-enabling {tf_name} "
                        f"(required for Oliver Velez Multi-Timeframe strategy)"
                    )
                    tf_config["enabled"] = True
                    modified = True
            
            # Persist changes to disk if any modifications were made
            if modified:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                logger.info(
                    f"✅ TrifectaAnalyzer: Required timeframes {self.required_tfs} enabled in {self.config_path}. "
                    f"Scanner will detect changes and reload automatically."
                )
            else:
                logger.debug("TrifectaAnalyzer: All required timeframes already enabled.")
        
        except Exception as e:
            logger.error(
                f"TrifectaAnalyzer: Failed to auto-enable timeframes: {e}. "
                f"Please enable {self.required_tfs} manually in {self.config_path}",
                exc_info=True
            )
