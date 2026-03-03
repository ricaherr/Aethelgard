"""
Market Structure Analyzer - Detección de HH/HL/LH/LL y Breaker Blocks

ESTRATEGIA: S-0006 (STRUCTURE BREAK SHIFT)
TRACE_ID: SENSOR-MARKET-STRUCT-001
VERSIÓN: 1.0

Responsabilidades:
1. Detectar Higher High (HH), Higher Low (HL) para tendencias alcistas
2. Detectar Lower High (LH), Lower Low (LL) para tendencias bajistas
3. Mapear Breaker Block (zona de quiebre de estructura)
4. Validar y detectar Break of Structure (BOS)
5. Calcular zonas de pullback para entrada confluencia
6. Caching de resultados para optimización

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage en constructor
Algoritmo: ZigZag institucional con pivot detection

TRACE_ID: SENSOR-MARKET-STRUCT-001
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Literal, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketStructureAnalyzer:
    """
    Analizador de estructura de mercado con detección de pivots y quiebres.
    
    Pilares:
    - Detección institucional de HH/HL/LH/LL
    - Mapeo automático de Breaker Blocks (zonas donde ocurrió el quiebre)
    - Validación de Break of Structure (BOS) con fuerza de vela
    - Cálculo de zona de pullback para entrada confluencia
    """
    
    def __init__(
        self,
        storage: Any,
        trace_id: str = None
    ):
        """
        Inicializa el analizador de estructura.
        
        Args:
            storage: StorageManager (SSOT para configuración)
            trace_id: Request trace ID para auditoría
        """
        self.storage = storage
        self.trace_id = trace_id or "SENSOR-MARKET-STRUCT-001"
        
        # Cache de estructuras detectadas
        self._structure_cache: Dict[str, Dict[str, Any]] = {}
        
        # Parámetros dinámicos desde BD
        self._load_config()
        
        logger.info(
            f"[{self.trace_id}] MarketStructureAnalyzer initialized. "
            f"Min pivots: {self.structure_min_pivots}, "
            f"Breaker buffer: {self.breaker_buffer_pips}pips, "
            f"Lookback: {self.structure_lookback_candles} candles"
        )
    
    
    def _load_config(self) -> None:
        """Carga configuración desde storage (SSOT)."""
        try:
            params = self.storage.get_dynamic_params()
            
            # Mínimo de pivots para validar estructura
            self.structure_min_pivots = params.get('structure_min_pivots', 3)
            
            # Buffer en pips para Breaker Block
            self.breaker_buffer_pips = params.get('breaker_buffer_pips', 5)
            
            # Cantidad de velas históricas a analizar
            self.structure_lookback_candles = params.get('structure_lookback_candles', 20)
            
            # Profundidad del ZigZag (candles entre pivots)
            self.zig_zag_depth = params.get('zig_zag_depth', 5)
            
            # Fuerza de ruptura mínima (en ATR)
            self.bos_strength_atr = params.get('bos_strength_atr', 2.0)
            
        except Exception as e:
            logger.warning(f"Failed to load config from storage: {e}. Using defaults.")
            self.structure_min_pivots = 3
            self.breaker_buffer_pips = 5
            self.structure_lookback_candles = 20
            self.zig_zag_depth = 5
            self.bos_strength_atr = 2.0
    
    
    # ============= DETECCIÓN DE PIVOTS =============
    
    def detect_higher_highs(self, candles: pd.DataFrame) -> List[int]:
        """
        Detecta Higher Highs (HH) en datos históricos.
        
        HH = cada high es superior al high anterior (tendencia alcista válida)
        
        Args:
            candles: DataFrame con columnas [high, low, close, ...]
            
        Returns:
            Lista de índices donde ocurren HH
        """
        if len(candles) < 3:
            return []
        
        higher_highs = []
        highs = candles['high'].values
        
        for i in range(1, len(highs)):
            # HH: high actual > high anterior
            if highs[i] > highs[i-1]:
                # Validar que no sea solo por ruido (comparar con 2 velas atrás si existe)
                if i >= 2:
                    # Debe ser más alto que ambas anteriores
                    if highs[i] > highs[i-1] and highs[i-1] > highs[i-2]:
                        higher_highs.append(i)
                else:
                    higher_highs.append(i)
        
        return higher_highs
    
    
    def detect_higher_lows(self, candles: pd.DataFrame) -> List[int]:
        """
        Detecta Higher Lows (HL) en datos históricos.
        
        HL = cada low es superior al low anterior (validación de tendencia alcista)
        
        Args:
            candles: DataFrame con columnas [high, low, close, ...]
            
        Returns:
            Lista de índices donde ocurren HL
        """
        if len(candles) < 3:
            return []
        
        higher_lows = []
        lows = candles['low'].values
        
        for i in range(1, len(lows)):
            # HL: low actual > low anterior
            if lows[i] > lows[i-1]:
                # Validar estructura (low actual > low anterior > low hace 2 velas)
                if i >= 2:
                    if lows[i] > lows[i-1] and lows[i-1] > lows[i-2]:
                        higher_lows.append(i)
                else:
                    higher_lows.append(i)
        
        return higher_lows
    
    
    def detect_lower_highs(self, candles: pd.DataFrame) -> List[int]:
        """
        Detecta Lower Highs (LH) para tendencias bajistas.
        
        LH = cada high es inferior al high anterior
        """
        if len(candles) < 3:
            return []
        
        lower_highs = []
        highs = candles['high'].values
        
        for i in range(1, len(highs)):
            if highs[i] < highs[i-1]:
                if i >= 2 and highs[i] < highs[i-1] and highs[i-1] < highs[i-2]:
                    lower_highs.append(i)
                elif i < 2:
                    lower_highs.append(i)
        
        return lower_highs
    
    
    def detect_lower_lows(self, candles: pd.DataFrame) -> List[int]:
        """
        Detecta Lower Lows (LL) para tendencias bajistas.
        
        LL = cada low es inferior al low anterior
        """
        if len(candles) < 3:
            return []
        
        lower_lows = []
        lows = candles['low'].values
        
        for i in range(1, len(lows)):
            if lows[i] < lows[i-1]:
                if i >= 2 and lows[i] < lows[i-1] and lows[i-1] < lows[i-2]:
                    lower_lows.append(i)
                elif i < 2:
                    lower_lows.append(i)
        
        return lower_lows
    
    
    # ============= DETECCIÓN DE ESTRUCTURA =============
    
    def detect_market_structure(self, candles: pd.DataFrame) -> Dict[str, Any]:
        """
        Detecta estructura de mercado (tendencia alcista o bajista).
        
        Lógica:
        - UPTREND: HH + HL (máximos y mínimos más altos)
        - DOWNTREND: LH + LL (máximos y mínimos más bajos)
        - INVALID: Datos insuficientes o sin patrón claro
        
        Args:
            candles: DataFrame con OHLC
            
        Returns:
            Dict con estructura detectada y metadatos
        """
        # Buscar en cache
        cache_key = f"struct_{hash(candles.iloc[-1, :].to_string())}"
        if cache_key in self._structure_cache:
            return self._structure_cache[cache_key]
        
        # Usar últimas N velas
        lookback = min(len(candles), self.structure_lookback_candles)
        recent_candles = candles.iloc[-lookback:].reset_index(drop=True)
        
        # Detectar pivots
        hh = self.detect_higher_highs(recent_candles)
        hl = self.detect_higher_lows(recent_candles)
        lh = self.detect_lower_highs(recent_candles)
        ll = self.detect_lower_lows(recent_candles)
        
        # Determinar tipo de estructura
        structure_type = "UNKNOWN"
        is_valid = False
        
        # UPTREND: más HH que LH, más HL que LL
        if len(hh) >= self.structure_min_pivots and len(hl) >= self.structure_min_pivots:
            if len(hh) >= len(lh) and len(hl) >= len(ll):
                structure_type = "UPTREND"
                is_valid = True
        
        # DOWNTREND: más LH que HH, más LL que HL
        elif len(lh) >= self.structure_min_pivots and len(ll) >= self.structure_min_pivots:
            if len(lh) >= len(hh) and len(ll) >= len(hl):
                structure_type = "DOWNTREND"
                is_valid = True
        
        # Construir resultado
        result = {
            'type': structure_type,
            'is_valid': is_valid,
            'hh_count': len(hh),
            'hl_count': len(hl),
            'lh_count': len(lh),
            'll_count': len(ll),
            'hh_indices': hh,
            'hl_indices': hl,
            'lh_indices': lh,
            'll_indices': ll,
            'last_hh_idx': hh[-1] if hh else None,
            'last_hl_idx': hl[-1] if hl else None,
            'last_lh_idx': lh[-1] if lh else None,
            'last_ll_idx': ll[-1] if ll else None,
            'analyzed_candles': lookback,
            'timestamp': datetime.now()
        }
        
        # Cachear resultado
        self._structure_cache[cache_key] = result
        
        logger.debug(
            f"[{self.trace_id}] Structure detected: {structure_type} "
            f"(HH={len(hh)}, HL={len(hl)}, LH={len(lh)}, LL={len(ll)})"
        )
        
        return result
    
    
    # ============= BREAKER BLOCK =============
    
    def calculate_breaker_block(
        self,
        structure: Dict[str, Any],
        candles: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Calcula la zona de Breaker Block (donde ocurrió el quiebre de estructura).
        
        Breaker Block en UPTREND:
        - High: Máximo del penúltimo HL
        - Low: Mínimo del último punto testeo
        - Zona donde el Smart Money confirmó cambio de sesgo
        
        Args:
            structure: Resultado de detect_market_structure()
            candles: DataFrame con OHLC
            
        Returns:
            Dict con high/low/midpoint del Breaker Block
        """
        if not structure['is_valid']:
            return {
                'high': None,
                'low': None,
                'midpoint': None,
                'range_pips': 0,
                'error': 'Invalid structure'
            }
        
        lookback = min(len(candles), self.structure_lookback_candles)
        recent_candles = candles.iloc[-lookback:].reset_index(drop=True)
        
        breaker_high = None
        breaker_low = None
        
        if structure['type'] == 'UPTREND':
            # En UPTREND, Breaker Block es la zona donde ocurrió el último HL
            if structure['last_hl_idx'] is not None:
                hl_idx = structure['last_hl_idx']
                
                # Zona alrededor del HL anterior
                if hl_idx > 0:
                    breaker_high = recent_candles.iloc[hl_idx:hl_idx+1]['high'].max()
                    breaker_low = recent_candles.iloc[max(0, hl_idx-2):hl_idx+1]['low'].min()
        
        elif structure['type'] == 'DOWNTREND':
            # En DOWNTREND, Breaker Block es la zona donde ocurrió el último LH
            if structure['last_lh_idx'] is not None:
                lh_idx = structure['last_lh_idx']
                
                breaker_low = recent_candles.iloc[lh_idx:lh_idx+1]['low'].min()
                breaker_high = recent_candles.iloc[max(0, lh_idx-2):lh_idx+1]['high'].max()
        
        # Si no hay breaker detectado, usar últimos pivots
        if breaker_high is None or breaker_low is None:
            breaker_high = recent_candles['high'].iloc[-5:].max()
            breaker_low = recent_candles['low'].iloc[-5:].min()
        
        # Aplicar buffer
        buffer = self.breaker_buffer_pips / 10000
        
        result = {
            'high': breaker_high + buffer,
            'low': breaker_low - buffer,
            'midpoint': (breaker_high + breaker_low) / 2,
            'range_pips': (breaker_high - breaker_low) * 10000,
            'buffer_applied': buffer
        }
        
        logger.debug(
            f"[{self.trace_id}] Breaker Block calculated: "
            f"{result['low']:.5f} - {result['high']:.5f}"
        )
        
        return result
    
    
    # ============= BREAK OF STRUCTURE (BOS) =============
    
    def detect_break_of_structure(
        self,
        structure: Dict[str, Any],
        breaker_block: Dict[str, float],
        current_candle: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Detecta si hay Break of Structure (BOS) en la vela actual.
        
        BOS en UPTREND: Cierre por debajo del HL (Breaker Block low)
        BOS en DOWNTREND: Cierre por encima del LH (Breaker Block high)
        
        Args:
            structure: Resultado de detect_market_structure()
            breaker_block: Resultado de calculate_breaker_block()
            current_candle: Vela actual con {high, low, close}
            
        Returns:
            Dict con {is_break: bool, direction: str, strength: float}
        """
        is_break = False
        direction = None
        strength = 0.0
        break_price = None
        
        if not structure['is_valid'] or breaker_block['range_pips'] == 0:
            return {
                'is_break': False,
                'direction': None,
                'strength': 0.0,
                'break_price': None,
                'breaker_level': None
            }
        
        close = current_candle.get('close')
        low = current_candle.get('low')
        high = current_candle.get('high')
        
        if structure['type'] == 'UPTREND':
            # BOS hacia abajo: cierre por debajo de HL
            if close and low and close < breaker_block['low']:
                is_break = True
                direction = 'DOWN'
                break_price = close
                
                # Calcular fuerza: qué % del Breaker Block fue roto
                breaker_range = breaker_block['high'] - breaker_block['low']
                if breaker_range > 0:
                    penetration = (breaker_block['low'] - close) / breaker_range
                    strength = min(penetration * 100, 100.0)  # Porcentaje
        
        elif structure['type'] == 'DOWNTREND':
            # BOS hacia arriba: cierre por encima de LH
            if close and high and close > breaker_block['high']:
                is_break = True
                direction = 'UP'
                break_price = close
                
                breaker_range = breaker_block['high'] - breaker_block['low']
                if breaker_range > 0:
                    penetration = (close - breaker_block['high']) / breaker_range
                    strength = min(penetration * 100, 100.0)
        
        result = {
            'is_break': is_break,
            'direction': direction,
            'strength': strength,
            'break_price': break_price,
            'breaker_level': breaker_block['low'] if structure['type'] == 'UPTREND' 
                            else breaker_block['high']
        }
        
        logger.debug(
            f"[{self.trace_id}] BOS Detection: "
            f"is_break={is_break}, direction={direction}, strength={strength:.1f}%"
        )
        
        return result
    
    
    # ============= PULLBACK ZONE =============
    
    def calculate_pullback_zone(
        self,
        breaker_block: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calcula la zona de pullback después de una ruptura.
        
        Zona de pullback = donde se espera que el precio retroceda a confirmar
        y busque entrada confluencia (Breaker Block).
        
        Args:
            breaker_block: Resultado de calculate_breaker_block()
            
        Returns:
            Dict con {entry_high, entry_low, midpoint}
        """
        if breaker_block['range_pips'] == 0:
            return {
                'entry_high': None,
                'entry_low': None,
                'midpoint': None,
                'range_pips': 0
            }
        
        # Zona de pullback = Breaker Block mismo (donde se esperamitigation retry)
        entry_high = breaker_block['high']
        entry_low = breaker_block['low']
        
        result = {
            'entry_high': entry_high,
            'entry_low': entry_low,
            'midpoint': (entry_high + entry_low) / 2,
            'range_pips': breaker_block['range_pips']
        }
        
        return result
