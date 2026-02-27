import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

class LiquidityService:
    """
    Motor de detección de Huellas Institucionales.
    Identifica Gaps de Valor Justo (FVG) y Bloques de Órdenes (OB)
    para advertir sobre la ejecución en zonas de baja probabilidad.
    """
    
    def __init__(self, storage: StorageManager):
        """
        Inicializa con Dependency Injection estricto.
        """
        self.storage = storage
        
    def _get_tenant_thresholds(self) -> Dict[str, Any]:
        """
        Obtiene los umbrales configurables multitenant.
        Carga desde StorageManager (dynamic_params) si existe.
        """
        try:
            params = self.storage.get_dynamic_params()
            if isinstance(params, dict) and "liquidity_thresholds" in params:
                return params["liquidity_thresholds"]
        except Exception as e:
            logger.debug(f"Could not load liquidity thresholds from storage: {e}")
            
        # Default fallbacks
        return {
            "fvg_min_size_pips": 5.0, # Minimum pip size to be considered an FVG
            "ob_volume_multiplier": 1.5, # Volume must be 1.5x average
            "max_lookback_candles": 20 # Candles to look back for zones
        }
        
    def detect_fvg(self, ohlcv_data: List[Dict[str, float]], pip_size: float) -> List[Dict[str, Any]]:
        """
        Detecta Fair Value Gaps (Imbalances) recientes en los datos provistos.
        Un FVG ocurre cuando hay un vacío de precio entre la mecha de la vela 1 y la vela 3.
        
        Args:
            ohlcv_data: Lista de velas [oldest, ..., newest] con keys 'high', 'low', etc.
            pip_size: Tamaño del pip para cálculos de umbral.
            
        Returns:
            Lista de FVGs detectados (tipo, techo, piso).
        """
        fvgs = []
        if not ohlcv_data or len(ohlcv_data) < 3:
            return fvgs
            
        thresholds = self._get_tenant_thresholds()
        min_size_price = thresholds.get("fvg_min_size_pips", 5.0) * pip_size
        
        # Iterar buscando patrón de 3 velas. [i] es vela 1, [i+1] es vela 2, [i+2] es vela 3
        for i in range(len(ohlcv_data) - 2):
            candle1 = ohlcv_data[i]
            # candle2 = ohlcv_data[i+1] # La vela de expansión
            candle3 = ohlcv_data[i+2]
            
            # Bullish FVG (Low of candle 3 is higher than High of candle 1)
            bullish_gap = candle3.get('low', 0) - candle1.get('high', 0)
            if bullish_gap >= min_size_price:
                fvgs.append({
                    "type": "bullish_fvg",
                    "top": candle3.get('low', 0),
                    "bottom": candle1.get('high', 0),
                    "size_pips": bullish_gap / pip_size if pip_size > 0 else 0,
                    "index": i+1 # Guardamos el índice de la vela de expansión
                })
                continue
                
            # Bearish FVG (High of candle 3 is lower than Low of candle 1)
            bearish_gap = candle1.get('low', 0) - candle3.get('high', 0)
            if bearish_gap >= min_size_price:
                fvgs.append({
                    "type": "bearish_fvg",
                    "top": candle1.get('low', 0),
                    "bottom": candle3.get('high', 0),
                    "size_pips": bearish_gap / pip_size if pip_size > 0 else 0,
                    "index": i+1
                })
                
        return fvgs

    def detect_order_blocks(self, ohlcv_data: List[Dict[str, float]]) -> List[Dict[str, Any]]:
        """
        Detecta Order Blocks basados en velas de reversión con alto volumen.
        
        Args:
            ohlcv_data: Lista de velas.
            
        Returns:
            Lista de Order Blocks (tipo, high, low).
        """
        obs = []
        if not ohlcv_data or len(ohlcv_data) < 3:
            return obs
            
        thresholds = self._get_tenant_thresholds()
        vol_multiplier = thresholds.get("ob_volume_multiplier", 1.5)
        
        # Calcular volumen promedio (Excluyendo la vela actual si se está formando)
        volumes = [c.get('volume', 0) for c in ohlcv_data[:-1]]
        avg_vol = sum(volumes) / len(volumes) if volumes else 0
        
        if avg_vol <= 0:
            return obs
            
        for i in range(1, len(ohlcv_data) - 1):
            prev_candle = ohlcv_data[i-1]
            curr_candle = ohlcv_data[i]
            next_candle = ohlcv_data[i+1]
            
            # Velas alcistas/bajistas (close > open)
            prev_is_bearish = prev_candle.get('close', 0) < prev_candle.get('open', 0)
            prev_is_bullish = prev_candle.get('close', 0) > prev_candle.get('open', 0)
            curr_is_bullish = curr_candle.get('close', 0) > curr_candle.get('open', 0)
            curr_is_bearish = curr_candle.get('close', 0) < curr_candle.get('open', 0)
            
            # Para simplificar: Buscamos un cambio de dirección fuerte respaldado por volumen
            if curr_candle.get('volume', 0) > avg_vol * vol_multiplier:
                # Bullish OB: Última vela bajista antes de un movimiento alcista fuerte
                if prev_is_bearish and curr_is_bullish:
                     obs.append({
                         "type": "bullish_ob",
                         "top": prev_candle.get('high', 0),
                         "bottom": prev_candle.get('low', 0),
                         "index": i-1
                     })
                # Bearish OB: Última vela alcista antes de un movimiento bajista fuerte
                elif prev_is_bullish and curr_is_bearish:
                     obs.append({
                         "type": "bearish_ob",
                         "top": prev_candle.get('high', 0),
                         "bottom": prev_candle.get('low', 0),
                         "index": i-1
                     })
                     
        return obs
        
    def is_in_high_probability_zone(
        self, 
        symbol: str, 
        price: float, 
        side: str, 
        ohlcv_data: List[Dict[str, float]], 
        pip_size: float
    ) -> Tuple[bool, str]:
        """
        Evalúa si la entrada sugerida se encuentra dentro/cerca de una zona de alta probabilidad (FVG o OB).
        
        Args:
            symbol: Símbolo analizado.
            price: Precio de entrada planeado.
            side: "BUY" o "SELL".
            ohlcv_data: Datos recientes para análisis.
            pip_size: Valor del pip.
            
        Returns:
            Tuple (is_high_prob, reason)
        """
        try:
            thresholds = self._get_tenant_thresholds()
            lookback = thresholds.get("max_lookback_candles", 20)
            recent_data = ohlcv_data[-lookback:] if len(ohlcv_data) > lookback else ohlcv_data
            
            fvgs = self.detect_fvg(recent_data, pip_size)
            obs = self.detect_order_blocks(recent_data)
            
            # Tolerancia de proximidad (Ej: Dentro de la zona o a +- 2 pips)
            tolerance = 2.0 * pip_size
            
            if side.upper() == "BUY":
                # Para BUY, buscamos que el precio esté interactuando con Bullish FVG o Bullish OB (Soporte)
                for fvg in fvgs:
                    if fvg["type"] == "bullish_fvg":
                        if fvg["bottom"] - tolerance <= price <= fvg["top"] + tolerance:
                            return True, f"Price at Bullish FVG zone ({fvg['bottom']:.4f} - {fvg['top']:.4f})"
                
                for ob in obs:
                    if ob["type"] == "bullish_ob":
                        if ob["bottom"] - tolerance <= price <= ob["top"] + tolerance:
                            return True, f"Price at Bullish Order Block ({ob['bottom']:.4f} - {ob['top']:.4f})"
                            
                return False, "Not at any known Bullish Liquidity Zone"
                
            elif side.upper() == "SELL":
                # Para SELL, buscamos interacción con Bearish FVG o Bearish OB (Resistencia)
                for fvg in fvgs:
                    if fvg["type"] == "bearish_fvg":
                        if fvg["bottom"] - tolerance <= price <= fvg["top"] + tolerance:
                            return True, f"Price at Bearish FVG zone ({fvg['bottom']:.4f} - {fvg['top']:.4f})"
                
                for ob in obs:
                    if ob["type"] == "bearish_ob":
                        if ob["bottom"] - tolerance <= price <= ob["top"] + tolerance:
                            return True, f"Price at Bearish Order Block ({ob['bottom']:.4f} - {ob['top']:.4f})"
                            
                return False, "Not at any known Bearish Liquidity Zone"
                
            return False, "Unknown side provided."
            
        except Exception as e:
            logger.error(f"Error checking probability zone for {symbol}: {e}")
            return False, "Error validating liquidity zones."
