"""
Servicio de análisis profundo de instrumentos para Aethelgard.
Expone funciones para obtener análisis de régimen, tendencia, trifecta y estrategias aplicables.
"""
from typing import Dict, Any
from data_vault.market_db import MarketMixin
from data_vault.storage import StorageManager
from core_brain.regime import RegimeClassifier
from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
from pathlib import Path
import json

class InstrumentAnalysisService:
    def __init__(self, storage: StorageManager, db_path: str = "data_vault/aethelgard.db"):
        self.market_db = MarketMixin(db_path)
        self.regime_classifier = RegimeClassifier(storage=storage)
        self.trifecta = TrifectaAnalyzer(storage=storage)
        self.storage = storage

    def get_analysis(self, symbol: str) -> Dict[str, Any]:
        # 1. Último estado de mercado
        history = self.market_db.get_market_state_history(symbol, limit=1)
        last_state = history[0]["data"] if history else {}

        # 2. Análisis de régimen y tendencia
        regime = last_state.get("regime", "NEUTRAL")
        adx = last_state.get("adx", None)
        volatility = last_state.get("volatility", None)
        trend_strength = last_state.get("trend_strength", None)
        sma20_slope = last_state.get("sma20_slope", None)
        sma200_slope = last_state.get("sma200_slope", None)
        separation_pct = last_state.get("separation_pct", None)
        price_position = last_state.get("price_position", None)

        # 3. Trifecta (si hay datos)
        trifecta_result = None
        if last_state.get("trifecta_data"):
            trifecta_result = last_state["trifecta_data"]
        # Si no, intentar ejecutar análisis en tiempo real (opcional)

        # 4. Estrategias aplicables (leer de config/modules.json)
        strategies = self._get_applicable_strategies(regime)

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
            "applicable_strategies": strategies
        }

    def _get_applicable_strategies(self, regime: str) -> list[dict]:
        # Lee config/modules.json y filtra estrategias por régimen
        modules_path = Path("config/modules.json")
        if not modules_path.exists():
            return []
        with open(modules_path, "r", encoding="utf-8") as f:
            modules = json.load(f)
        result = []
        for name, mod in modules.get("active_modules", {}).items():
            if not mod.get("enabled", False):
                continue
            if regime in mod.get("required_regime", []):
                result.append({
                    "name": name,
                    "description": mod.get("description", ""),
                    "membership_required": mod.get("membership_required", "basic")
                })
        return result
