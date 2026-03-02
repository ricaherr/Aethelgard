"""
Heatmap Data Service - Graceful Degradation Pipeline
Nunca falla (503): siempre retorna respuesta válida.

Patrón: Pipeline, Resilience, Graceful Degradation
Trace_ID: ARCH-HEATMAP-2026-001
"""

import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from core_brain.infrastructure import ProcessGatewayInterface
from data_vault.default_instruments import DEFAULT_INSTRUMENTS_CONFIG
from models.signal import MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class HeatmapCell:
    """Una celda del heatmap (símbolo x timeframe)."""
    symbol: str
    timeframe: str
    regime: str
    metrics: Dict[str, Any]
    signal: Optional[Dict[str, Any]] = None
    last_scan: Optional[float] = None
    is_stale: bool = True
    confluence: Optional[str] = None
    status: str = "ACTIVE"
    source: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "metrics": self.metrics,
            "signal": self.signal,
            "last_scan": self.last_scan,
            "is_stale": self.is_stale,
            "confluence": self.confluence,
            "status": self.status,
            "source": self.source,
        }


class HeatmapDataService:
    """
    Servicio de datos para heatmap con 4 niveles de resiliencia.
    NUNCA retorna 503 (siempre degrada gracefully).
    """
    
    FRESHNESS_THRESHOLDS = {
        "REALTIME": 60,      # <1 min: datos muy frescos
        "WARM": 300,          # <5 min: caché reciente
        "STALE": 3600,        # <1 hora: BD vieja pero válida
        "EXPIRED": 86400,     # >24h: datos muy viejos (usa síntesis)
    }
    
    def __init__(
        self,
        process_gateway: ProcessGatewayInterface,
        storage: Any,
        scanner: Optional[Any] = None
    ):
        """
        Args:
            process_gateway: IPC abstraction (DB, Redis, etc.)
            storage: StorageManager
            scanner: CandleScanner (opcional, puede ser None)
        """
        self.gateway = process_gateway
        self.storage = storage
        self.scanner = scanner
        logger.info("[HeatmapService] Initialized with resilience pipeline")
    
    async def get_heatmap(self) -> Dict[str, Any]:
        """
        Pipeline principal: intenta 4 niveles, siempre retorna algo válido.
        
        Level 1: Scanner local (tiempo real, <100ms)
        Level 2: Base de datos (reciente, 1-5ms)
        Level 3: Síntesis (fallback, siempre disponible)
        ← RESULTADO: success + metadata {source, freshness}
        """
        now = time.time()
        
        # Level 1: Scanner local en memoria
        cells = await self._fetch_from_scanner()
        if cells:
            return self._format_heatmap(
                cells=cells,
                source="scanner",
                freshness="REALTIME",
                timestamp=now
            )
        
        # Level 2: Base de datos (fallback cross-process)
        cells = await self._fetch_from_database()
        if cells:
            return self._format_heatmap(
                cells=cells,
                source="database",
                freshness="WARM",
                timestamp=now
            )
        
        # Level 3: Síntesis (graceful degradation)
        cells = await self._synthesize_default_heatmap()
        return self._format_heatmap(
            cells=cells,
            source="synthetic",
            freshness="EMPTY",
            timestamp=now,
            message="System initializing. Data collection in progress..."
        )
    
    async def _fetch_from_scanner(self) -> Optional[List[HeatmapCell]]:
        """
        Nivel 1: Obtener datos del scanner en memoria (mismo proceso).
        RÁPIDO: <100ms, datos reales.
        """
        if self.scanner is None:
            return None
        
        try:
            with self.scanner._lock:
                assets = list(self.scanner.assets)
                timeframes = list(self.scanner.active_timeframes)
                regimes = dict(self.scanner.last_regime)
                last_scans = dict(self.scanner.last_scan_time)
                classifiers = dict(self.scanner.classifiers)
                
                cells = []
                now = time.monotonic()
                
                for symbol in assets:
                    for tf in timeframes:
                        key = f"{symbol}|{tf}"
                        
                        regime_val = regimes.get(key, MarketRegime.NORMAL)
                        if hasattr(regime_val, 'value'):
                            regime_val = regime_val.value
                        
                        last_scan = last_scans.get(key, 0)
                        is_stale = (now - last_scan) > 300 if last_scan > 0 else True
                        
                        metrics = {}
                        classifier = classifiers.get(key)
                        if classifier:
                            try:
                                metrics = classifier.get_metrics()
                            except Exception:
                                pass
                        
                        cell = HeatmapCell(
                            symbol=symbol,
                            timeframe=tf,
                            regime=regime_val,
                            metrics=metrics,
                            last_scan=last_scan,
                            is_stale=is_stale,
                            source="scanner"
                        )
                        cells.append(cell)
                
                logger.info(f"[HeatmapService] Fetched {len(cells)} cells from scanner")
                return cells if cells else None
        
        except Exception as e:
            logger.warning(f"[HeatmapService] Error fetching from scanner: {e}")
            return None
    
    async def _fetch_from_database(self) -> Optional[List[HeatmapCell]]:
        """
        Nivel 2: Obtener datos de la BD (cross-process fallback).
        CONFIABLE: atomic, auditado. Latencia 1-5ms.
        """
        try:
            state = await self.gateway.get_market_heatmap_state()
            if not state:
                return None
            
            cells = []
            now_ts = time.time()
            
            for s in state:
                ts_str = s.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str).timestamp() if ts_str else 0
                except (ValueError, TypeError):
                    ts = 0
                
                is_stale = (now_ts - ts) > 300 if ts > 0 else True
                
                cell = HeatmapCell(
                    symbol=s.get("symbol"),
                    timeframe=s.get("timeframe", "M1"),
                    regime=s.get("regime", "NORMAL"),
                    metrics=s.get("metrics", {}),
                    last_scan=ts,
                    is_stale=is_stale,
                    source="database"
                )
                cells.append(cell)
            
            logger.info(f"[HeatmapService] Fetched {len(cells)} cells from database")
            return cells if cells else None
        
        except Exception as e:
            logger.error(f"[HeatmapService] Error fetching from database: {e}")
            return None
    
    async def _synthesize_default_heatmap(self) -> List[HeatmapCell]:
        """
        Nivel 3: Síntesis (graceful degradation).
        FALLBACK FINAL: retorna matriz de valores por defecto.
        
        Garantías:
        - ✅ No lanza excepciones
        - ✅ Símbolos de configuración por defecto
        - ✅ Timeframes estándar
        - ✅ Régimen neutral (NORMAL)
        - ✅ UI puede renderizar normalmente
        """
        try:
            symbols = DEFAULT_INSTRUMENTS_CONFIG.get("symbols", [])
            timeframes = ["M1", "M5", "M15", "H1", "H4", "D1"]
            
            cells = []
            for symbol in symbols:
                for tf in timeframes:
                    cell = HeatmapCell(
                        symbol=symbol,
                        timeframe=tf,
                        regime="NORMAL",
                        metrics={},
                        last_scan=None,
                        is_stale=True,
                        status="PENDING_DATA_COLLECTION",
                        source="synthetic"
                    )
                    cells.append(cell)
            
            logger.warning(f"[HeatmapService] Synthesized {len(cells)} default cells (NO DATA)")
            return cells
        
        except Exception as e:
            logger.error(f"[HeatmapService] Error synthesizing heatmap: {e}")
            # ÚLTIMO RECURSO: retornar lista vacía (UI renderiza grid vacío)
            return []
    
    def _format_heatmap(
        self,
        cells: List[HeatmapCell],
        source: str,
        freshness: str,
        timestamp: float,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Formatear respuesta del heatmap con metadata.
        
        Metadata indica al cliente:
        - source: Dónde vienen los datos (scanner/database/synthetic)
        - freshness: Qué tan frescos son (REALTIME/WARM/STALE/EMPTY)
        - timestamp: Cuándo se generó esta respuesta
        """
        # Agrupar por símbolo para análisis de confluencia
        cells_by_symbol = {}
        for cell in cells:
            if cell.symbol not in cells_by_symbol:
                cells_by_symbol[cell.symbol] = []
            cells_by_symbol[cell.symbol].append(cell)
        
        # Calcular confluencia (mismo sesgo en 2+ timeframes)
        for symbol, symbol_cells in cells_by_symbol.items():
            biases = [c.metrics.get("bias") for c in symbol_cells if c.metrics.get("bias")]
            
            if len(biases) >= 2:
                bullish_count = biases.count("BULLISH")
                bearish_count = biases.count("BEARISH")
                
                if bullish_count >= 2:
                    for c in symbol_cells:
                        c.confluence = "BULLISH"
                        c.status = "CONFLUENCE_BULLISH"
                elif bearish_count >= 2:
                    for c in symbol_cells:
                        c.confluence = "BEARISH"
                        c.status = "CONFLUENCE_BEARISH"
        
        # Extraer assets y timeframes únicos
        assets = sorted(list(set(c.symbol for c in cells)))
        timeframes = sorted(list(set(c.timeframe for c in cells)))
        
        return {
            "symbols": assets,
            "timeframes": timeframes,
            "cells": [c.to_dict() for c in cells],
            "metadata": {
                "source": source,
                "freshness": freshness,
                "total_cells": len(cells),
                "total_assets": len(assets),
                "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                "message": message or f"Heatmap from {source} ({freshness})"
            }
        }
