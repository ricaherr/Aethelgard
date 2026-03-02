"""
Process Communication Gateway (IPC Abstraction Layer)
Patrón: Repository/Adapter
Permite cambiar backend IPC (DB, Redis, etc.) sin afectar routers.

Trace_ID: ARCH-IPC-2026-001
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessGatewayInterface(ABC):
    """
    Interface agnóstica para comunicación entre procesos.
    Scanner (P1) → Database ← Routers (P2)
    """
    
    @abstractmethod
    async def get_latest_regime(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """
        Obtener régimen más reciente para símbolo+timeframe.
        
        Returns:
            Dict con {regime, timestamp, metrics} o None
        """
        raise NotImplementedError
    
    @abstractmethod
    async def get_scanner_state(self) -> Dict[str, Any]:
        """
        Obtener estado completo del scanner (todos los símbolos/timeframes).
        
        Returns:
            Dict con estructura: {
                "assets": [...],
                "timeframes": [...],
                "regimes": {symbol|tf: regime_data},
                "scan_times": {symbol|tf: unix_timestamp},
                "source": "database|redis|memory"
            }
        """
        raise NotImplementedError
    
    @abstractmethod
    async def get_market_heatmap_state(self) -> List[Dict[str, Any]]:
        """
        Obtener datos formateados para heatmap.
        
        Returns:
            Lista de celdas [{symbol, timeframe, regime, metrics, timestamp}]
        """
        raise NotImplementedError
    
    @abstractmethod
    async def publish_scan_result(self, symbol: str, timeframe: str, data: Dict[str, Any]) -> None:
        """
        Publicar nuevo resultado de escaneo (producer).
        Llamada por Scanner cuando termina de procesar.
        
        Args:
            symbol: Instrumento (EURUSD, etc.)
            timeframe: Temporalidad (M1, M5, H1, etc.)
            data: Resultado {regime, metrics, timestamp, etc.}
        """
        raise NotImplementedError
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Verificar si la gateway está operativa."""
        raise NotImplementedError


class DatabaseGateway(ProcessGatewayInterface):
    """
    Implementación basada en SQLite (SSOT).
    Síncrona, atomic, auditoria integrada.
    
    Ventajas:
    - ✅ SSOT: Aethelgard ya usa SQLite
    - ✅ Atomic: Transacciones ACID
    - ✅ Auditoria: Timestamp persistente
    - ✅ Fallback automático si multiprocesos
    
    Desventajas:
    - ❌ Latencia disco (~1-5ms vs memoria <1µs)
    - ❌ Lock contention si muchos writers
    """
    
    def __init__(self, storage):
        """
        Args:
            storage: StorageManager instance (inyección de dependencia)
        """
        self.storage = storage
        logger.info("[ProcessGateway] Initialized with Database backend")
    
    async def get_latest_regime(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """
        Consultar market_state table directamente.
        ATOMIC: Single query, no race conditions.
        """
        try:
            result = self.storage.get_market_state(symbol, timeframe=timeframe)
            if result:
                return {
                    "symbol": result["symbol"],
                    "timeframe": result.get("timeframe", timeframe),
                    "regime": result["data"].get("regime", "NORMAL"),
                    "metrics": result["data"].get("metrics", {}),
                    "timestamp": result["data"].get("timestamp", datetime.now().isoformat()),
                }
            return None
        except Exception as e:
            logger.error(f"[DatabaseGateway] Error fetching regime {symbol}/{timeframe}: {e}")
            return None
    
    async def get_scanner_state(self) -> Dict[str, Any]:
        """
        Agregación de market_state para reconstruir scanner state.
        Fallback cuando scanner está en otro proceso.
        """
        try:
            states = self.storage.get_all_market_states()
            if not states:
                return {"error": "no_data", "source": "database"}
            
            # Agrupar por símbolo y timeframe
            regimes = {}
            scan_times = {}
            assets = set()
            timeframes = set()
            
            for state in states:
                symbol = state.get("symbol")
                tf = state.get("data", {}).get("timeframe", "M1")
                key = f"{symbol}|{tf}"
                
                regimes[key] = state.get("data", {}).get("regime", "NORMAL")
                scan_times[key] = state.get("data", {}).get("scan_time", 0)
                assets.add(symbol)
                timeframes.add(tf)
            
            return {
                "assets": sorted(list(assets)),
                "timeframes": sorted(list(timeframes)),
                "regimes": regimes,
                "scan_times": scan_times,
                "source": "database",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[DatabaseGateway] Error getting scanner state: {e}")
            return {"error": str(e), "source": "database"}
    
    async def get_market_heatmap_state(self) -> List[Dict[str, Any]]:
        """
        Formato directo para heatmap (sin transformaciones).
        Queda en manos del heatmap service formatear para UI.
        """
        try:
            states = self.storage.get_all_market_states()
            cells = []
            
            for state in states:
                data = state.get("data", {})
                cell = {
                    "symbol": state.get("symbol"),
                    "timeframe": data.get("timeframe", "M1"),
                    "regime": data.get("regime", "NORMAL"),
                    "metrics": data.get("metrics", {}),
                    "timestamp": data.get("timestamp", datetime.now().isoformat()),
                    "scan_time": data.get("scan_time", 0),
                    "source": "database"
                }
                cells.append(cell)
            
            return cells
        except Exception as e:
            logger.error(f"[DatabaseGateway] Error getting heatmap state: {e}")
            return []
    
    async def publish_scan_result(self, symbol: str, timeframe: str, data: Dict[str, Any]) -> None:
        """
        Guardar resultado de escaneo en market_state.
        Llamado por Scanner después de procesar.
        """
        try:
            market_data = {
                "timeframe": timeframe,
                "regime": data.get("regime", "NORMAL"),
                "metrics": data.get("metrics", {}),
                "timestamp": datetime.now().isoformat(),
                "scan_time": data.get("scan_time", 0),
                "details": data.get("details", {})
            }
            
            self.storage.update_market_state(symbol, market_data)
            logger.debug(f"[DatabaseGateway] Published scan result: {symbol}|{timeframe}")
        except Exception as e:
            logger.error(f"[DatabaseGateway] Error publishing scan result: {e}")
    
    async def health_check(self) -> bool:
        """Verificar conectividad a la base de datos."""
        try:
            _ = self.storage.get_system_state()
            return True
        except Exception as e:
            logger.error(f"[DatabaseGateway] Health check failed: {e}")
            return False


class RedisGateway(ProcessGatewayInterface):
    """
    Implementación basada en Redis (opcional, para escala futura).
    Asíncrona, ultra-rápida, pub/sub integrado.
    
    TODO: Implementar cuando escala lo requiera.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        logger.info("[ProcessGateway] Initialized with Redis backend")
    
    async def get_latest_regime(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("Redis gateway not yet implemented")
    
    async def get_scanner_state(self) -> Dict[str, Any]:
        raise NotImplementedError("Redis gateway not yet implemented")
    
    async def get_market_heatmap_state(self) -> List[Dict[str, Any]]:
        raise NotImplementedError("Redis gateway not yet implemented")
    
    async def publish_scan_result(self, symbol: str, timeframe: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError("Redis gateway not yet implemented")
    
    async def health_check(self) -> bool:
        raise NotImplementedError("Redis gateway not yet implemented")


def get_process_gateway(storage: 'StorageManager', db_type: str = "database") -> ProcessGatewayInterface:
    """
    Factory function para obtener la gateway apropiada.
    Patrón: Factory + Dependency Injection.
    
    Args:
        storage: StorageManager instance para acceso a datos
        db_type: Tipo de gateway ('database' o 'redis')
    
    Returns:
        ProcessGatewayInterface implementation
    
    En el futuro:
    - Chequear si Redis disponible
    - Fallback a Database
    """
    # Por ahora, siempre usar Database
    return DatabaseGateway(storage)
