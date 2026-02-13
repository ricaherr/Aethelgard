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
            
            # DEGRADED MODE: Allow signal to pass without Trifecta filtering
            logger.warning(
                f"⚠️ [{symbol}] TrifectaAnalyzer operating in DEGRADED MODE: "
                f"Missing {missing_tfs}. Signal quality is REDUCED. "
                f"Enable {missing_tfs} in config.json for full Trifecta filtering."
            )
            
            return {
                "valid": True,  # ← Allow signal to pass
                "direction": "UNKNOWN",  # No puede determinar dirección sin 3 TFs
                "score": 50.0,  # Neutral score (ni bonifica ni penaliza)
                "metadata": {
                    "degraded_mode": True,
                    "missing_timeframes": missing_tfs,
                    "reason": "Insufficient Data - Operating in fallback mode"
                }
            }

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
