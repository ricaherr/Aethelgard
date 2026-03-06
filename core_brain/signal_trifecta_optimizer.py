"""
Signal Trifecta Optimizer - Filtrado Oliver Velez Multi-Timeframe
==================================================================

Responsabilidad única: Aplicar lógica Oliver Velez de M2-M5-M15 para 
filtrar señales según patrón trifecta y reforzar confianza.
"""
import logging
from collections import defaultdict
from typing import List, Any, Dict

from models.signal import Signal

logger = logging.getLogger(__name__)


class SignalTrifectaOptimizer:
    """
    Optimiza señales aplicando estrategia Oliver Velez.
    
    Lógica Oliver Velez:
    - M2 (dirección): identifica tendencia corta
    - M5 (confirmación): verifica fuerza
    - M15 (macro contexto): valida setup válido
    
    Si 2+ de 3 timeframes alineados: señal REFORZADA
    Si <2: señal DEBILITADA (DEGRADED MODE)
    
    Score final = 40% original + 60% trifecta bonus
    Filtro: solo pasar si final_score >= 60
    """
    
    def __init__(self, trifecta_analyzer: Any):
        """
        Inicializa optimizador.
        
        Args:
            trifecta_analyzer: Instancia TrifectaAnalyzer
        """
        self.trifecta_analyzer = trifecta_analyzer
    
    def optimize(
        self,
        signals: List[Signal],
        scan_results: Dict[str, Any]
    ) -> List[Signal]:
        """
        Aplica análisis trifecta Oliver Velez a señales "oliver".
        
        Algoritmo:
        1. Agrupar market_data por símbolo normalizado
        2. Para cada signal con strategy_id == "oliver":
            a. Obtener datos trifecta (M2, M5, M15)
            b. Analizar alineación
            c. Calcular bonus/penalty
            d. Score final = 40% original + 60% trifecta
            e. Filtrar: si score < 60 → eliminar
        
        Args:
            signals: Lista de señales
            scan_results: {market_data: {symbol: {timeframe: {...}}}}
        
        Returns:
            Señales filtradas y optimizadas
        """
        if not scan_results or not scan_results.get('market_data'):
            logger.debug("[TRIFECTA] No market_data in scan_results")
            return signals
        
        market_data = scan_results['market_data']
        symbol_data = self._build_symbol_data(market_data)
        
        optimized_signals = []
        
        for signal in signals:
            # Solo aplicar trifecta a estrategia "oliver"
            strategy_id = signal.metadata.get('strategy_id', 'unknown')
            
            if strategy_id != 'oliver':
                optimized_signals.append(signal)
                continue
            
            if signal.symbol not in symbol_data:
                logger.debug(f"[TRIFECTA] No market data for {signal.symbol}")
                optimized_signals.append(signal)
                continue
            
            # Obtener datos trifecta
            trifecta_data = symbol_data[signal.symbol]
            
            # Analizar alineación M2-M5-M15
            trifecta_result = self.trifecta_analyzer.analyze(trifecta_data)
            
            if not trifecta_result:
                logger.warning(f"[TRIFECTA] Failed to analyze {signal.symbol}")
                optimized_signals.append(signal)
                continue
            
            # Calcular score final
            original_score = signal.metadata.get('score', signal.confidence)
            trifecta_score = trifecta_result.get('score', 0)
            
            # 40% original + 60% trifecta
            final_score = (original_score * 0.4) + (trifecta_score * 0.6)
            
            # Filtrar: solo pasar si final_score >= 60
            if final_score < 0.60:
                logger.info(
                    f"[TRIFECTA] {signal.symbol} filtered: "
                    f"score {original_score:.2f} + trifecta {trifecta_score:.2f} "
                    f"= {final_score:.2f} < 0.60 (MIN)"
                )
                continue
            
            # Actualizar signal con resultado trifecta
            signal.metadata['trifecta_score'] = trifecta_score
            signal.metadata['trifecta_alignment'] = trifecta_result.get('alignment', 'none')
            signal.metadata['score'] = final_score
            signal.confidence = final_score
            
            logger.info(
                f"[TRIFECTA] {signal.symbol} optimized: "
                f"{original_score:.2f} + {trifecta_score:.2f} → {final_score:.2f}"
            )
            
            optimized_signals.append(signal)
        
        return optimized_signals
    
    @staticmethod
    def _build_symbol_data(market_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict]:
        """
        Construye estructura de datos trifecta: {symbol: {M2: {...}, M5: {...}, M15: {...}}}.
        
        Extrae información de M2, M5, M15 para análisis Oliver Velez.
        
        Args:
            market_data: {symbol: {timeframe: {data}}}
        
        Returns:
            {symbol: {M2: {...}, M5: {...}, M15: {...}}} (solo si existen)
        """
        symbol_data = defaultdict(dict)
        trifecta_timeframes = ['M2', 'M5', 'M15']
        
        for symbol, timeframes in market_data.items():
            if not isinstance(timeframes, dict):
                continue
            
            for timeframe in trifecta_timeframes:
                if timeframe in timeframes:
                    symbol_data[symbol][timeframe] = timeframes[timeframe]
        
        return symbol_data
