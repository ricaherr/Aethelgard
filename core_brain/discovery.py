import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger(__name__)

class DiscoveryEngine:
    """
    Motor de descubrimiento para escanear mercados y generar dinámicamente assets.json.
    Filtra activos por volumen mínimo para asegurar liquidez.
    Actualmente soporta MetaTrader 5.
    """

    def __init__(self, config_path: str = "config/config.json", mt5_init: bool = True):
        self.config_path = Path(config_path)
        self.assets_output_path = self.config_path.parent / "assets.json"
        
        self._initialized = False
        if mt5_init and mt5 and not mt5.initialize():
            logger.warning("MT5 no pudo inicializarse para DiscoveryEngine: %s", mt5.last_error())
            return
        if mt5:
            self._initialized = True
            logger.info("DiscoveryEngine MT5 inicializado. Versión MT5: %s", mt5.version())

    def shutdown(self) -> None:
        """Cierra la conexión con MT5 si fue inicializada por este motor."""
        if mt5 and self._initialized:
            mt5.shutdown()
            self._initialized = False
            logger.info("DiscoveryEngine MT5 cerrado.")

    def _get_mt5_symbols(self, min_volume: int = 0) -> List[Dict[str, Any]]:
        """
        Obtiene todos los símbolos de MT5 y filtra por volumen mínimo.
        """
        if not mt5 or not self._initialized:
            logger.error("MT5 no disponible o no inicializado.")
            return []

        symbols_info = mt5.symbols_get()
        if symbols_info is None:
            logger.error("No se pudieron obtener símbolos de MT5: %s", mt5.last_error())
            return []

        filtered_symbols = []
        for s in symbols_info:
            if s.visible and s.volume >= min_volume: # Solo símbolos visibles y con volumen
                filtered_symbols.append({
                    "name": s.name,
                    "description": s.description,
                    "volume": s.volume,
                    "type": self._determine_market_type(s.name) # Asignar tipo de mercado
                })
        return filtered_symbols

    def _determine_market_type(self, symbol_name: str) -> str:
        """
        Heurística simple para determinar el tipo de mercado basado en el nombre del símbolo.
        Esto puede necesitar ser más sofisticado o configurable.
        """
        # Ejemplo de heurística, ajustar según la nomenclatura de símbolos de MT5/Rithmic
        if "USD" in symbol_name or "EUR" in symbol_name or "GBP" in symbol_name or "JPY" in symbol_name or "CAD" in symbol_name or "AUD" in symbol_name or "NZD" in symbol_name or "CHF" in symbol_name:
            return "Forex"
        elif any(crypto_tag in symbol_name for crypto_tag in ["BTC", "ETH", "XRP", "LTC", "ADA", "DOGE"]):
            return "Cripto"
        elif any(future_tag in symbol_name for future_tag in ["_F", "F", "YM", "ES", "NQ", "RTY", "GC", "CL", "NG"]): # Ejemplos de futuros
            return "Futuros"
        else: # Por defecto, acciones o similar
            return "Acciones"

    def generate_assets_json(self, min_volume: int = 1000) -> Optional[Path]:
        """
        Escanea mercados y genera el archivo assets.json.
        
        Args:
            min_volume: Volumen mínimo requerido para que un activo sea incluido.
        
        Returns:
            Path al archivo assets.json generado, o None si hubo un error.
        """
        logger.info("Iniciando escaneo de mercados para generar assets.json...")
        
        all_assets = []
        mt5_assets = self._get_mt5_symbols(min_volume)
        all_assets.extend(mt5_assets)

        # Aquí se podría añadir lógica para Rithmic o otros conectores en el futuro
        # rithmic_assets = self._get_rithmic_symbols(min_volume)
        # all_assets.extend(rithmic_assets)
        
        if not all_assets:
            logger.warning("No se encontraron activos elegibles después del filtrado.")
            return None
            
        assets_by_market = {}
        for asset in all_assets:
            market_type = asset.get("type", "Unknown")
            if market_type not in assets_by_market:
                assets_by_market[market_type] = []
            assets_by_market[market_type].append(asset)

        try:
            with open(self.assets_output_path, "w", encoding="utf-8") as f:
                json.dump(assets_by_market, f, indent=4)
            logger.info("assets.json generado exitosamente en: %s con %d activos.", self.assets_output_path, len(all_assets))
            return self.assets_output_path
        except IOError as e:
            logger.error("Error escribiendo assets.json: %s", e)
            return None

if __name__ == "__main__":
    # Configuración básica de logging para probar el módulo
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Ejemplo de uso
    discovery_engine = DiscoveryEngine()
    try:
        # Generar assets.json con un volumen mínimo de 1000
        generated_path = discovery_engine.generate_assets_json(min_volume=1000)
        if generated_path:
            with open(generated_path, 'r', encoding='utf-8') as f:
                print("Contenido de assets.json:")
                print(f.read())
    finally:
        discovery_engine.shutdown()
