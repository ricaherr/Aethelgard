def to_utc(dt, source_tz=None) -> str:
from utils.time_utils import to_utc
"""
Market Utils - Utilidades Globales para Mercados y Símbolos
==========================================================

Centraliza la lógica de normalización de precios, volúmenes y pips
siguiendo el principio de agnosticismo de Aethelgard.

Jerarquía de Normalización:
1. Datos reales del Broker (digits, point, volume_step).
2. Deducción técnica (digits calculados desde point).
3. Clasificación de InstrumentManager (Fallback agnóstico).
4. Defaults seguros de industria.
"""
import logging
import math
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

def normalize_price(
    price: float, 
    symbol_info: Any = None, 
    symbol: str = None, 
    instrument_manager: Any = None
) -> float:
    """
    Normaliza el precio de un instrumento con fallback jerárquico.
    
    Args:
        price: Precio a normalizar.
        symbol_info: Objeto de información del símbolo del broker (opcional).
        symbol: Nombre del símbolo (opcional, para fallback por categoría).
        instrument_manager: Instancia de InstrumentManager (opcional, para fallback).
        
    Returns:
        float: Precio redondeado a la precisión correcta.
    """
    if price is None:
        return 0.0
        
    digits = None
    
    # Nivel 1: Datos directos del Broker
    if symbol_info and hasattr(symbol_info, 'digits'):
        digits = symbol_info.digits
        
    # Nivel 2: Deducción desde point (si digits no está disponible)
    if digits is None and symbol_info and hasattr(symbol_info, 'point') and symbol_info.point > 0:
        # point = 0.00001 -> log10(100000) = 5
        try:
            digits = round(-math.log10(symbol_info.point))
        except (ValueError, OverflowError):
            pass
            
    # Nivel 3: Fallback por categoría (InstrumentManager)
    if digits is None and symbol and instrument_manager:
        digits = instrument_manager.get_default_precision(symbol)
        
    # Nivel 4: Defaults de industria seguros
    if digits is None:
        # Fallback ultra-conservador si no hay NADA de información
        if symbol:
            symbol_up = symbol.upper()
            if 'JPY' in symbol_up:
                digits = 3
            elif any(m in symbol_up for m in ['XAU', 'XAG', 'GOLD', 'SILVER']):
                digits = 2
            elif len(symbol_up) == 6 or '.X' in symbol_up or '=X' in symbol_up:
                digits = 5
            else:
                digits = 2 # Usualmente índices o cryptos
        else:
            digits = 5 # Default forex estándar
            
    return round(float(price), digits)

def normalize_volume(
    volume: float, 
    symbol_info: Any
) -> float:
    """
    Normaliza el volumen del lote según los límites y el step del broker.
    
    Args:
        volume: Volumen sugerido.
        symbol_info: Objeto de información del símbolo del broker.
        
    Returns:
        float: Volumen normalizado y clamped dentro de los límites del broker.
    """
    try:
        if not symbol_info:
            return round(volume, 2)
            
        min_lot = getattr(symbol_info, 'volume_min', 0.01)
        max_lot = getattr(symbol_info, 'volume_max', 100.0)
        step = getattr(symbol_info, 'volume_step', 0.01)
        
        # Clamp a rango min/max inicial
        normalized = max(min_lot, min(volume, max_lot))
        
        # Redondear al step más cercano
        if step > 0:
            steps_count = round(normalized / step)
            normalized = steps_count * step
            
            # Asegurar que no bajamos del mínimo por el redondeo
            if normalized < min_lot:
                normalized = min_lot
        else:
            normalized = round(normalized, 2)
            
        # Re-clamping final por seguridad
        return round(max(min_lot, min(normalized, max_lot)), 8)
        
    except Exception as e:
        logger.error(f"Error normalizando volumen: {e}")
        return round(volume, 2)

def calculate_pip_size(
    symbol_info: Any = None, 
    symbol: str = None,
    instrument_manager: Any = None
) -> float:
    """
    Calcula el tamaño del pip (unidad de movimiento mínima relevante).
    Para Forex: 4to o 2do decimal (0.0001 o 0.01).
    Para otros: Usa el point del broker.
    """
    digits = None
    point = getattr(symbol_info, 'point', 0.0)
    
    # 1. Obtener dígitos
    if symbol_info and hasattr(symbol_info, 'digits'):
        digits = symbol_info.digits
    elif symbol and instrument_manager:
        digits = instrument_manager.get_default_precision(symbol)
        
    # 2. Lógica de Pip vs Point
    if digits is not None:
        digits = int(digits)
        if digits in [3, 5]: # Forex con pips fraccionales (pips = 10 * point)
            if point > 0:
                return point * 10
            # Fallback si no hay point pero sabemos los digits (estándar forex)
            return 0.0001 if digits == 5 else 0.01
            
        if digits in [2, 4]: # Forex sin pips fraccionales o Índices
            if point > 0:
                return point
            return 0.0001 if digits == 4 else 0.01

    # 3. Fallback final al point del broker o pips estándar
    if point > 0:
        return point
        
    # 4. Fallback manual por nombre (ultimo recurso)
    if symbol and 'JPY' in symbol.upper():
        return 0.01
    return 0.0001
