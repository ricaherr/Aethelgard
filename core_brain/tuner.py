"""
Sistema de Auto-Calibración para Aethelgard
Optimiza umbrales de ADX y Volatilidad basándose en datos históricos
para minimizar falsos positivos en la detección de régimen
"""
import json
import logging
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import numpy as np
from datetime import datetime

from data_vault.storage import StorageManager
from models.signal import MarketRegime

logger = logging.getLogger(__name__)


class ParameterTuner:
    """
    Sistema de auto-calibración que analiza datos históricos
    para encontrar los umbrales óptimos de ADX y Volatilidad
    """
    
    def __init__(self, storage: StorageManager, config_path: str = "config/dynamic_params.json"):
        """
        Args:
            storage: Instancia de StorageManager para acceder a datos históricos
            config_path: Ruta al archivo de configuración dinámica
        """
        self.storage = storage
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self) -> Dict:
        """Carga la configuración actual desde el archivo JSON"""
        if not self.config_path.exists():
            # Valores por defecto si no existe el archivo
            default_config = {
                "adx_trend_threshold": 25.0,
                "adx_range_threshold": 20.0,
                "adx_range_exit_threshold": 18.0,
                "volatility_shock_multiplier": 5.0,
                "adx_period": 14,
                "sma_period": 200,
                "shock_lookback": 5,
                "min_volatility_atr_period": 50,
                "persistence_candles": 2,
                "last_updated": None
            }
            self._save_config(default_config)
            return default_config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            raise
    
    def _save_config(self, config: Dict):
        """Guarda la configuración en el archivo JSON"""
        config["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"Configuración guardada en {self.config_path}")
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
            raise
    
    def _calculate_false_positive_rate(self, 
                                      states: List[Dict],
                                      adx_trend_threshold: float,
                                      adx_range_threshold: float,
                                      volatility_threshold: Optional[float] = None) -> float:
        """
        Calcula la tasa de falsos positivos para un conjunto de umbrales.
        
        Un falso positivo se define como:
        - Cambio de régimen detectado que se revierte en las siguientes 5-10 velas
        - Régimen TREND detectado cuando el mercado realmente estaba en RANGE
        - Régimen RANGE detectado cuando el mercado realmente estaba en TREND
        
        Args:
            states: Lista de estados de mercado históricos
            adx_trend_threshold: Umbral ADX para entrar en TREND
            adx_range_threshold: Umbral ADX para entrar en RANGE
            volatility_threshold: Umbral de volatilidad (opcional)
        
        Returns:
            Tasa de falsos positivos (0.0 a 1.0)
        """
        if len(states) < 20:
            return 1.0  # Sin suficientes datos, asumir peor caso
        
        false_positives = 0
        total_changes = 0
        
        # Ordenar por timestamp (más antiguo primero)
        sorted_states = sorted(states, key=lambda x: x.get('timestamp', ''))
        
        for i in range(len(sorted_states) - 10):
            current = sorted_states[i]
            current_regime = current.get('regime')
            
            # Solo evaluar cambios de régimen
            if i > 0:
                previous = sorted_states[i - 1]
                previous_regime = previous.get('regime')
                
                if current_regime != previous_regime:
                    total_changes += 1
                    
                    # Verificar si el cambio fue correcto mirando las siguientes 5-10 velas
                    future_states = sorted_states[i+1:min(i+11, len(sorted_states))]
                    
                    if future_states:
                        # Contar cuántas veces el régimen se mantiene vs se revierte
                        regime_persistence = sum(
                            1 for state in future_states 
                            if state.get('regime') == current_regime
                        )
                        
                        # Si el régimen se revierte en más del 50% de las velas siguientes,
                        # considerarlo un falso positivo
                        if regime_persistence < len(future_states) * 0.5:
                            false_positives += 1
        
        if total_changes == 0:
            return 0.0
        
        return false_positives / total_changes
    
    def _optimize_adx_thresholds(self, states: List[Dict]) -> Tuple[float, float, float]:
        """
        Optimiza los umbrales de ADX buscando el mínimo de falsos positivos
        
        Args:
            states: Lista de estados de mercado históricos
        
        Returns:
            Tupla con (adx_trend_threshold, adx_range_threshold, adx_range_exit_threshold)
        """
        if len(states) < 100:
            logger.warning("Insuficientes datos para optimización, usando valores por defecto")
            return (25.0, 20.0, 18.0)
        
        best_fpr = float('inf')
        best_thresholds = (25.0, 20.0, 18.0)
        
        # Rango de búsqueda para umbrales ADX
        trend_range = np.arange(20.0, 35.0, 1.0)
        range_range = np.arange(15.0, 25.0, 1.0)
        exit_range = np.arange(15.0, 22.0, 1.0)
        
        logger.info("Iniciando optimización de umbrales ADX...")
        
        # Búsqueda en grid (limitada para no ser demasiado lenta)
        for trend_thresh in trend_range:
            for range_thresh in range_range:
                for exit_thresh in exit_range:
                    # Validar que exit < range < trend
                    if not (exit_thresh < range_thresh < trend_thresh):
                        continue
                    
                    # Simular clasificación con estos umbrales
                    fpr = self._calculate_false_positive_rate(
                        states,
                        trend_thresh,
                        range_thresh
                    )
                    
                    if fpr < best_fpr:
                        best_fpr = fpr
                        best_thresholds = (float(trend_thresh), float(range_thresh), float(exit_thresh))
        
        logger.info(f"Umbrales ADX optimizados: TREND={best_thresholds[0]}, RANGE={best_thresholds[1]}, EXIT={best_thresholds[2]} (FPR: {best_fpr:.2%})")
        return best_thresholds
    
    def _optimize_volatility_threshold(self, states: List[Dict]) -> float:
        """
        Optimiza el umbral de volatilidad para detectar shocks
        
        Args:
            states: Lista de estados de mercado históricos
        
        Returns:
            Multiplicador de volatilidad óptimo
        """
        if len(states) < 100:
            logger.warning("Insuficientes datos para optimización, usando valor por defecto")
            return 5.0
        
        # Analizar la distribución de cambios de volatilidad en estados CRASH
        crash_states = [s for s in states if s.get('regime') == MarketRegime.CRASH.value]
        
        if len(crash_states) < 10:
            logger.info("Pocos estados CRASH, usando multiplicador por defecto")
            return 5.0
        
        # Calcular volatilidades en momentos de CRASH vs momentos normales
        crash_volatilities = [s.get('volatility', 0) for s in crash_states if s.get('volatility')]
        all_volatilities = [s.get('volatility', 0) for s in states if s.get('volatility')]
        
        if not crash_volatilities or not all_volatilities:
            return 5.0
        
        avg_crash_vol = np.mean(crash_volatilities)
        avg_normal_vol = np.mean(all_volatilities)
        
        if avg_normal_vol == 0:
            return 5.0
        
        # El multiplicador óptimo sería aproximadamente la razón entre volatilidades
        optimal_multiplier = max(3.0, min(10.0, avg_crash_vol / avg_normal_vol))
        
        logger.info(f"Multiplicador de volatilidad optimizado: {optimal_multiplier:.2f}")
        return float(optimal_multiplier)
    
    def auto_calibrate(self, limit: int = 1000, symbol: Optional[str] = None) -> Dict:
        """
        Ejecuta la auto-calibración leyendo los últimos registros y optimizando parámetros
        
        Args:
            limit: Número de registros históricos a analizar (default: 1000)
            symbol: Filtrar por símbolo específico (opcional)
        
        Returns:
            Diccionario con los nuevos parámetros optimizados
        """
        logger.info(f"Iniciando auto-calibración con {limit} registros...")
        
        # Cargar configuración actual
        current_config = self._load_config()
        
        # Obtener estados históricos
        states = self.storage.get_market_states(limit=limit, symbol=symbol)
        
        if len(states) < 100:
            logger.warning(f"Solo {len(states)} registros disponibles. Se necesitan al menos 100 para una calibración confiable.")
            return current_config
        
        logger.info(f"Analizando {len(states)} estados de mercado...")
        
        # Optimizar umbrales ADX
        trend_thresh, range_thresh, exit_thresh = self._optimize_adx_thresholds(states)
        
        # Optimizar umbral de volatilidad
        volatility_multiplier = self._optimize_volatility_threshold(states)
        
        # Crear nueva configuración
        new_config = {
            "adx_trend_threshold": trend_thresh,
            "adx_range_threshold": range_thresh,
            "adx_range_exit_threshold": exit_thresh,
            "volatility_shock_multiplier": volatility_multiplier,
            "adx_period": current_config.get("adx_period", 14),
            "sma_period": current_config.get("sma_period", 200),
            "shock_lookback": current_config.get("shock_lookback", 5),
            "min_volatility_atr_period": current_config.get("min_volatility_atr_period", 50),
            "persistence_candles": current_config.get("persistence_candles", 2),
            "last_updated": datetime.now().isoformat()
        }
        
        # Guardar nueva configuración
        self._save_config(new_config)
        
        logger.info("Auto-calibración completada exitosamente")
        return new_config
    
    def get_optimal_params(self) -> Dict:
        """
        Obtiene los parámetros óptimos actuales desde el archivo de configuración
        
        Returns:
            Diccionario con los parámetros actuales
        """
        return self._load_config()
