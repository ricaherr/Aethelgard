"""
Servicio de análisis profundo de instrumentos para Aethelgard.
Implementa resiliencia mediante graceful degradation - nunca lanza excepciones, retorna datos parciales.
"""
import logging
from typing import Dict, Any, List, Optional
from data_vault.market_db import MarketMixin
from data_vault.storage import StorageManager
from core_brain.regime import RegimeClassifier

logger = logging.getLogger(__name__)

class InstrumentAnalysisService:
    def __init__(self, storage: StorageManager, tenant_id: str = "default"):
        """
        Inicializa InstrumentAnalysisService.
        
        Args:
            storage: StorageManager inyectado (DI pattern)
            tenant_id: ID del tenant para aislación multi-tenant
        """
        self.tenant_id = tenant_id
        self.storage = storage
        
        try:
            self.market_db = MarketMixin()
        except Exception as e:
            logger.warning(f"[AnalysisService] Failed to initialize MarketMixin: {e}")
            self.market_db = None
        
        try:
            self.regime_classifier = RegimeClassifier(storage=storage)
        except Exception as e:
            logger.warning(f"[AnalysisService] Failed to initialize RegimeClassifier: {e}")
            self.regime_classifier = None

    def get_analysis(self, symbol: str) -> Dict[str, Any]:
        """
        Retorna análisis completo de un instrumento (régimen, tendencia, trifecta, estrategias).
        Implementa graceful degradation: nunca lanza excepciones, retorna datos parciales.
        
        Returns:
            Dict con análisis de régimen, tendencia, trifecta y estrategias aplicables
        """
        try:
            # Validar input
            if not symbol or not isinstance(symbol, str):
                return self._empty_analysis(symbol or "UNKNOWN")
            
            # 1. Obtener último estado de mercado desde BD
            last_state = {}
            try:
                if self.market_db:
                    history = self.market_db.get_sys_market_pulse_history(symbol, limit=1)
                    last_state = history[0]["data"] if history else {}
            except Exception as e:
                logger.debug(f"[AnalysisService] Failed to fetch market state for {symbol}: {e}")
            
            # 2. Régimen y tendencia (con fallback)
            regime = last_state.get("regime", "NEUTRAL")
            adx = last_state.get("adx")
            volatility = last_state.get("volatility")
            trend_strength = last_state.get("trend_strength")
            sma20_slope = last_state.get("sma20_slope")
            sma200_slope = last_state.get("sma200_slope")
            separation_pct = last_state.get("separation_pct")
            price_position = last_state.get("price_position")
            
            # 3. Trifecta (si hay datos)
            trifecta_result = None
            try:
                if last_state.get("trifecta_data"):
                    trifecta_result = last_state["trifecta_data"]
            except Exception as e:
                logger.debug(f"[AnalysisService] Trifecta extraction failed: {e}")
            
            # 4. Estrategias aplicables
            usr_strategies = self._get_applicable_usr_strategies(regime)
            
            return {
                "symbol": symbol,
                "regime": {
                    "current": regime,
                    "adx": adx,
                    "volatility": volatility
                },
                "trend": {
                    "strength": trend_strength,
                    "sma20_slope": sma20_slope,
                    "sma200_slope": sma200_slope,
                    "separation_pct": separation_pct,
                    "price_position": price_position
                },
                "trifecta": trifecta_result,
                "applicable_usr_strategies": usr_strategies,
                "metadata": {
                    "freshness": "cached",
                    "source": "market_db"
                }
            }
        
        except Exception as e:
            logger.error(f"[AnalysisService] Unexpected error in get_analysis({symbol}): {e}", exc_info=True)
            return self._empty_analysis(symbol)

    def _get_applicable_usr_strategies(self, regime: str) -> List[Dict[str, Any]]:
        """
        Obtiene módulos estratégicos aplicables para un régimen.
        
        Returns:
            Lista de estrategias aplicables (vacía si falla)
        """
        try:
            if not self.storage:
                logger.warning("[AnalysisService] StorageManager not available")
                return []
            
            modules = self.storage.get_modules_config()
            result = []
            
            for name, mod in modules.get("active_modules", {}).items():
                try:
                    if not mod.get("enabled", False):
                        continue
                    
                    required_regimes = mod.get("required_regime", [])
                    if isinstance(required_regimes, str):
                        required_regimes = [required_regimes]
                    
                    if regime in required_regimes:
                        result.append({
                            "name": name,
                            "description": mod.get("description", "N/A"),
                            "membership_required": mod.get("membership_required", "basic"),
                            "enabled": True
                        })
                except Exception as e:
                    logger.debug(f"[AnalysisService] Failed to process module {name}: {e}")
                    continue
            
            return result
        
        except Exception as e:
            logger.warning(f"[AnalysisService] Failed to get applicable usr_strategies for regime {regime}: {e}")
            return []

    def _empty_analysis(self, symbol: str) -> Dict[str, Any]:
        """Retorna análisis vacío pero válido cuando no hay datos."""
        return {
            "symbol": symbol,
            "regime": {
                "current": "NEUTRAL",
                "adx": None,
                "volatility": None
            },
            "trend": {
                "strength": None,
                "sma20_slope": None,
                "sma200_slope": None,
                "separation_pct": None,
                "price_position": None
            },
            "trifecta": None,
            "applicable_usr_strategies": [],
            "metadata": {
                "freshness": "stale",
                "source": "empty"
            }
        }
