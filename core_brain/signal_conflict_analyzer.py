"""
Signal Conflict Analyzer - Análisis Multi-Timeframe de Confluencia
===================================================================

Responsabilidad única: Aplicar coincidencia de regímenes de múltiples 
timeframes para reforzar confianza de señal.
"""
import logging
from collections import defaultdict
from typing import List, Any, Dict

from models.signal import Signal, MarketRegime

logger = logging.getLogger(__name__)


class SignalConflictAnalyzer:
    """
    Analiza confluencia de regímenes multi-timeframe.
    
    Responsabilidad:
    - Agrupar regímenes por símbolo (excluyendo timeframe primario)
    - Aplicar lógica de confluencia: si 2+ timeframes están en TREND, 
      amplificar la señal
    - Solo modifica signals que pasan validación fundamental
    """
    
    def __init__(self, confluence_analyzer: Any):
        """
        Inicializa analizador.
        
        Args:
            confluence_analyzer: Instancia MultiTimeframeConfluenceAnalyzer
        """
        self.confluence_analyzer = confluence_analyzer
    
    def apply_confluence(
        self,
        signals: List[Signal],
        scan_results: Dict[str, Any]
    ) -> List[Signal]:
        """
        Aplica análisis de confluencia multi-timeframe.
        
        Agrupa regímenes por símbolo (excluyendo timeframe primario).
        Si hay 2+ timeframes en TREND, amplifica confianza.
        
        Args:
            signals: Lista de señales procesadas
            scan_results: Datos de escaneo con market_data[symbol][timeframe].regime
        
        Returns:
            Señales con confluencia aplicada (score modificado)
        """
        if not scan_results or not scan_results.get('market_data'):
            logger.debug("[CONFLUENCE] No market_data in scan_results")
            return signals
        
        market_data = scan_results['market_data']
        symbol_regimes = self._group_regimes_by_symbol(market_data, signals)
        
        for signal in signals:
            if signal.symbol not in symbol_regimes:
                continue
            
            regimes = symbol_regimes[signal.symbol]
            
            if not regimes or signal.confidence < 0.60:
                continue
            
            # Aplicar confluencia
            try:
                confluence_bonus = self.confluence_analyzer.analyze(regimes)
                original_score = signal.metadata.get('score', signal.confidence)
                new_score = original_score * (1 + confluence_bonus)
                
                signal.metadata['confluence_bonus'] = confluence_bonus
                signal.metadata['score'] = new_score
                signal.confidence = new_score
                
                logger.info(
                    f"[CONFLUENCE] {signal.symbol}: "
                    f"score {original_score:.2f} → {new_score:.2f} "
                    f"(+{confluence_bonus*100:.1f}%)"
                )
            except Exception as e:
                logger.warning(f"[CONFLUENCE] Error analyzing {signal.symbol}: {e}")
                # Mantener score original si hay error
        
        return signals
    
    @staticmethod
    def _group_regimes_by_symbol(
        market_data: Dict[str, Dict[str, Any]],
        signals: List[Signal]
    ) -> Dict[str, List[MarketRegime]]:
        """
        Agrupa regímenes por símbolo, excluyendo timeframe primario de cada signal.
        
        Ejemplo:
        - signal: EURUSD M5 (timeframe primario)
        - regímenes disponibles: EURUSD M1, M15, H1, H4
        - resultado: [M1, M15, H1, H4] (excluyendo M5)
        
        Args:
            market_data: {symbol: {timeframe: {regime, ...}}}
            signals: Lista de señales (para obtener timeframe primario)
        
        Returns:
            {symbol: [MarketRegime, ...]}
        """
        symbol_regimes = defaultdict(list)
        primary_timeframes = {signal.symbol: signal.timeframe for signal in signals}
        
        for symbol, timeframes_data in market_data.items():
            if not isinstance(timeframes_data, dict):
                continue
            
            primary_tf = primary_timeframes.get(symbol)
            
            for timeframe, tf_data in timeframes_data.items():
                if not isinstance(tf_data, dict):
                    continue
                
                # Excluir timeframe primario
                if timeframe == primary_tf:
                    continue
                
                # Extraer régimen
                regime = tf_data.get('regime')
                if regime:
                    symbol_regimes[symbol].append(regime)
        
        return symbol_regimes
