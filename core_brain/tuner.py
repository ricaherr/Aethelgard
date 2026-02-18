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
    
    def __init__(self, storage: StorageManager):
        """
        Args:
            storage: Instancia de StorageManager para acceder a datos históricos
        """
        self.storage = storage
    
    def _load_config(self) -> Dict:
        """Carga la configuración actual desde Storage (SSOT)"""
        params = self.storage.get_dynamic_params()
        if not params:
            # Fallback a defaults si no hay nada en DB todavía
            return {
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
        return params
    
    def _save_config(self, config: Dict) -> None:
        """Guarda la configuración en Storage (SSOT)"""
        config["last_updated"] = datetime.now().isoformat()
        self.storage.update_dynamic_params(config)
        logger.info("[OK] Configuración guardada en DB (dynamic_params)")
    
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


# ============================================================================
# EDGE TUNER: Auto-ajuste de parámetros de señales basado en resultados reales
# ============================================================================

class EdgeTuner:
    """
    Sistema EDGE de auto-calibración que ajusta parámetros de generación de señales
    basándose en el rendimiento real de los trades ejecutados.
    
    Filosofía:
    - Racha de pérdidas → Modo CONSERVADOR (filtros más estrictos)
    - Racha de ganancias → Modo AGRESIVO (capturar más oportunidades)
    - Win rate cercano al target → Ajustes graduales (estabilidad)
    """
    
    def __init__(self, storage: StorageManager):
        """
        Args:
            storage: StorageManager para acceder a resultados de trades
        """
        self.storage = storage
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self) -> Dict:
        """Carga configuración desde Storage (SSOT)"""
        return self.storage.get_dynamic_params()
    
    def _save_config(self, config: Dict) -> None:
        """Guarda configuración actualizada en Storage"""
        self.storage.update_dynamic_params(config)
        self.logger.info("[OK] Configuración dinámica actualizada en DB")
    
    def _calculate_stats(self, trades: List[Dict]) -> Dict:
        """
        Calcula estadísticas de rendimiento
        
        Returns:
            {
                "total_trades": int,
                "wins": int,
                "losses": int,
                "win_rate": float,
                "avg_pips_win": float,
                "avg_pips_loss": float,
                "profit_factor": float,
                "consecutive_losses": int,
                "consecutive_wins": int
            }
        """
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0}
        
        wins = [t for t in trades if t.get("is_win", False)]
        losses = [t for t in trades if not t.get("is_win", True)]
        
        win_rate = len(wins) / len(trades) if trades else 0.0
        
        avg_pips_win = np.mean([t["pips"] for t in wins]) if wins else 0.0
        avg_pips_loss = abs(np.mean([t["pips"] for t in losses])) if losses else 0.0
        
        total_profit = sum([t["profit_loss"] for t in wins])
        total_loss = abs(sum([t["profit_loss"] for t in losses]))
        profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
        
        # Calcular rachas consecutivas (más recientes primero)
        consecutive_losses = 0
        consecutive_wins = 0
        
        for trade in trades:  # Ya vienen ordenados por timestamp desc
            if not trade.get("is_win", True):
                consecutive_losses += 1
                if consecutive_wins > 0:
                    break
            else:
                consecutive_wins += 1
                if consecutive_losses > 0:
                    break
        
        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "avg_pips_win": float(avg_pips_win),
            "avg_pips_loss": float(avg_pips_loss),
            "profit_factor": float(profit_factor),
            "consecutive_losses": consecutive_losses,
            "consecutive_wins": consecutive_wins
        }
    
    def adjust_parameters(self, limit_trades: int = 100) -> Optional[Dict]:
        """
        Analiza resultados recientes y ajusta parámetros automáticamente.
        
        Lógica de ajuste:
        - Win rate < 45% → CONSERVADOR (subir filtros)
        - Win rate > 65% → AGRESIVO (bajar filtros)
        - Win rate 45-65% → Ajuste gradual hacia target (55%)
        - Racha de 5+ pérdidas → Modo defensivo inmediato
        
        Args:
            limit_trades: Número de trades recientes a analizar
        
        Returns:
            Dictionary con detalles del ajuste o None si no se hizo nada
        """
        config = self._load_config()
        
        # Verificar si tuning está habilitado
        if not config.get("tuning_enabled", False):
            self.logger.info("[INFO] Tuning deshabilitado en config")
            return {"skipped_reason": "tuning_disabled"}
        
        # Obtener trades recientes
        trades = self.storage.get_recent_trades(limit=limit_trades)
        
        min_trades = config.get("min_trades_for_tuning", 20)
        if len(trades) < min_trades:
            self.logger.info(f"[INFO] Insuficientes trades para ajuste ({len(trades)}/{min_trades})")
            return {"skipped_reason": "insufficient_data"}
        
        # Calcular estadísticas
        stats = self._calculate_stats(trades)
        self.logger.info(f"[INFO] Stats: Win Rate={stats['win_rate']:.1%}, Trades={stats['total_trades']}, "
                        f"Consecutive Losses={stats['consecutive_losses']}")
        
        # Guardar parámetros actuales para comparación
        old_params = {
            "adx_threshold": config.get("adx_threshold", 25),
            "elephant_atr_multiplier": config.get("elephant_atr_multiplier", 0.3),
            "sma20_proximity_percent": config.get("sma20_proximity_percent", 1.5),
            "min_signal_score": config.get("min_signal_score", 60),
            "risk_per_trade": config.get("risk_per_trade", 0.01)
        }
        
        # === DETERMINAR MODO DE AJUSTE ===
        trigger = "normal_adjustment"
        adjustment_factor = 1.0  # 1.0 = sin cambio, >1.0 = más conservador, <1.0 = más agresivo
        
        target_win_rate = config.get("target_win_rate", 0.55)
        conservative_threshold = config.get("conservative_mode_threshold", 0.45)
        aggressive_threshold = config.get("aggressive_mode_threshold", 0.65)
        
        # Load max_consecutive_losses from risk_settings (Single Source of Truth)
        max_consecutive_losses = config.get('max_consecutive_losses', 3)
        
        # RACHA DE PÉRDIDAS → Defensivo inmediato
        if stats["consecutive_losses"] >= max_consecutive_losses:
            trigger = "consecutive_losses"
            adjustment_factor = 1.7  # +70% más conservador
            self.logger.warning(f"MODO DEFENSIVO: {stats['consecutive_losses']} pérdidas consecutivas")
        
        # WIN RATE MUY BAJO → Conservador
        elif stats["win_rate"] < conservative_threshold:
            trigger = "low_win_rate"
            adjustment_factor = 1.5  # +50% más conservador
            self.logger.warning(f"[WARNING] Win rate bajo ({stats['win_rate']:.1%}) -> Modo conservador")
        
        # WIN RATE MUY ALTO → Agresivo
        elif stats["win_rate"] > aggressive_threshold:
            trigger = "high_win_rate"
            adjustment_factor = 0.7  # -30% menos filtros
            self.logger.info(f"[INFO] Win rate alto ({stats['win_rate']:.1%}) -> Modo agresivo")
        
        # WIN RATE CERCANO AL TARGET → Ajuste gradual
        else:
            # Ajuste proporcional: cuanto más lejos del target, mayor el ajuste
            deviation = stats["win_rate"] - target_win_rate
            adjustment_factor = 1.0 - (deviation * 0.5)  # Max ±25% ajuste
            self.logger.info(f"[INFO] Ajuste gradual: win_rate={stats['win_rate']:.1%}, target={target_win_rate:.1%}")
        
        # === APLICAR AJUSTES ===
        new_params = old_params.copy()
        
        # ADX Threshold: más alto = más conservador (solo tendencias fuertes)
        base_adx = 25
        new_params["adx_threshold"] = max(20, min(35, base_adx * adjustment_factor))
        
        # ATR Multiplier: más alto = más conservador (solo velas grandes)
        base_atr = 0.3
        new_params["elephant_atr_multiplier"] = max(0.15, min(0.7, base_atr * adjustment_factor))
        
        # SMA20 Proximity: más bajo = más conservador (pullback más preciso)
        base_proximity = 1.5
        new_params["sma20_proximity_percent"] = max(0.8, min(2.5, base_proximity / adjustment_factor))
        
        # Min Score: más alto = más conservador
        base_score = 60
        new_params["min_signal_score"] = max(50, min(80, int(base_score * adjustment_factor)))

        # Risk Per Trade: Dinámico EDGE
        # Base 1.0%. Bajamos a 0.5% si factor > 1.2 (conservador/rachas). Subimos a 1.25% si factor < 0.8 (agresivo).
        base_risk = 0.01 # 1.0%
        if adjustment_factor >= 1.5: # MODO DEFENSIVO / LOW WR
            new_params["risk_per_trade"] = 0.005 # 0.5%
        elif adjustment_factor <= 0.7: # MODO AGRESIVO / HIGH WR
            new_params["risk_per_trade"] = 0.0125 # 1.25%
        else:
            # Ajuste lineal suave hacia el target
            new_params["risk_per_trade"] = max(0.005, min(0.0125, base_risk / adjustment_factor))
        
        # Actualizar configuración
        config.update(new_params)
        self._save_config(config)
        
        # Guardar ajuste en historial
        adjustment_record = {
            "trigger": trigger,
            "old_params": old_params,
            "new_params": new_params,
            "stats": stats,
            "adjustment_factor": float(adjustment_factor)
        }
        
        self.storage.save_tuning_adjustment(adjustment_record)
        
        self.logger.info(f"[OK] Parámetros ajustados:")
        self.logger.info(f"   ADX: {old_params['adx_threshold']:.1f} -> {new_params['adx_threshold']:.1f}")
        self.logger.info(f"   ATR: {old_params['elephant_atr_multiplier']:.2f} -> {new_params['elephant_atr_multiplier']:.2f}")
        self.logger.info(f"   SMA20: {old_params['sma20_proximity_percent']:.1f}% -> {new_params['sma20_proximity_percent']:.1f}%")
        self.logger.info(f"   RISK: {old_params['risk_per_trade']*100:.2f}% -> {new_params['risk_per_trade']*100:.2f}%")
        
        return adjustment_record
