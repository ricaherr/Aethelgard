"""
Imbalance Detector (HU 3.3: Detector de Ineficiencias).
Trace_ID: EXEC-STRAT-OPEN-001

Detección asíncrona de Fair Value Gaps (FVG) en M5/M15 con validación
de volumen para confirmar huella institucional.

Arquitectura:
- Inyección de dependencias estricta (StorageManager)
- Métodos asíncrónos para detección no-bloqueante
- FVG + Volume Confirmation = Señal de Imbalance
- Cada señal incluye UUID v4 como Instance ID (SSOT de Mnemonic)
"""

import logging
import asyncio
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

from data_vault.storage import StorageManager
from models.signal import Signal, SignalType

logger = logging.getLogger(__name__)


class ImbalanceDetector:
    """
    Motor de Detección de Ineficiencias de Mercado.
    
    Responsabilidades:
    1. Identificar Fair Value Gaps (FVGs) asíncronamente
    2. Validar FVGs con confirmnación de volumen
    3. Generar señales de imbalance para estrategias
    4. Persistir hallazgos en DB
    """
    
    def __init__(self, storage: StorageManager):
        """
        Inicializa ImbalanceDetector con inyección de dependencias.
        
        Args:
            storage: StorageManager para persistencia y configuración
        """
        self.storage = storage
        self.trace_id = f"IMBALANCE-{uuid.uuid4().hex[:8].upper()}"
        
        logger.info(f"[ImbalanceDetector] Inicializado con Trace_ID: {self.trace_id}")
    
    def _load_thresholds(self) -> Dict[str, float]:
        """
        Carga umbrales de detección desde storage o usa defaults.
        
        Returns:
            Dict con thresholds (fvg_min_size_pips, volume_confirmation_ratio, etc.)
        """
        try:
            params = self.storage.get_dynamic_params()
            if isinstance(params, dict) and "imbalance_thresholds" in params:
                return params["imbalance_thresholds"]
        except Exception as e:
            logger.debug(f"Could not load imbalance thresholds: {e}")
        
        # Defaults
        return {
            "fvg_min_size_pips": 5.0,
            "volume_confirmation_ratio": 1.3,  # Volumen debe ser 1.3x el promedio
            "max_lookback_candles": 20,
            "min_volume_avg": 50
        }
    
    def detect_fvg(self, ohlcv_data: List[Dict[str, float]], pip_size: float, 
                   timeframe: str) -> List[Dict[str, Any]]:
        """
        Detecta Fair Value Gaps (imbalances de precio) en datos OHLCV.
        
        Un FVG bullish ocurre cuando: Low[n+2] > High[n] (gap arriba)
        Un FVG bearish ocurre cuando: High[n+2] < Low[n] (gap abajo)
        
        Args:
            ohlcv_data: Lista de velas OHLCV
            pip_size: Tamaño del pip para cálculos (ej. 0.0001 para Forex)
            timeframe: Timeframe de los datos ("M5", "M15", "H1", etc.)
            
        Returns:
            Lista de FVGs detectados con estructura:
            {
                "type": "bullish_fvg" | "bearish_fvg",
                "top": float,      # Techo del gap
                "bottom": float,   # Piso del gap
                "size_pips": float,
                "index": int,      # Índice en la lista de velas
                "timeframe": str
            }
        """
        fvgs = []
        thresholds = self._load_thresholds()
        min_size_price = thresholds.get("fvg_min_size_pips", 5.0) * pip_size
        
        if not ohlcv_data or len(ohlcv_data) < 3:
            return fvgs
        
        # Iterar buscando patrón de 3 velas
        for i in range(len(ohlcv_data) - 2):
            candle1 = ohlcv_data[i]
            candle3 = ohlcv_data[i + 2]
            
            high1 = candle1.get("high", 0)
            low1 = candle1.get("low", 0)
            high3 = candle3.get("high", 0)
            low3 = candle3.get("low", 0)
            
            # Bullish FVG: Low[3] > High[1]
            bullish_gap = low3 - high1
            if bullish_gap >= min_size_price:
                fvgs.append({
                    "type": "bullish_fvg",
                    "top": low3,
                    "bottom": high1,
                    "size_pips": bullish_gap / pip_size if pip_size > 0 else 0,
                    "index": i + 1,
                    "timeframe": timeframe
                })
                continue
            
            # Bearish FVG: High[3] < Low[1]
            bearish_gap = low1 - high3
            if bearish_gap >= min_size_price:
                fvgs.append({
                    "type": "bearish_fvg",
                    "top": low1,
                    "bottom": high3,
                    "size_pips": bearish_gap / pip_size if pip_size > 0 else 0,
                    "index": i + 1,
                    "timeframe": timeframe
                })
        
        logger.debug(f"[{self.trace_id}] FVGs detectados: {len(fvgs)} en {timeframe}")
        return fvgs
    
    def validate_institutional_footprint(self, ohlcv_data: List[Dict[str, float]], 
                                        fvg_index: int) -> bool:
        """
        Valida que un FVG tenga huella institucional confirmada por volumen.
        
        La vela de expansión (que crea el FVG) debe tener volumen significativo
        para considerarse una movida institucional real vs. ruido.
        
        Args:
            ohlcv_data: Lista de velas OHLCV
            fvg_index: Índice de la vela de expansión
            
        Returns:
            True si hay confirmación institucional, False en caso contrario
        """
        thresholds = self._load_thresholds()
        volume_ratio = thresholds.get("volume_confirmation_ratio", 1.3)
        min_volume_avg = thresholds.get("min_volume_avg", 50)
        lookback = thresholds.get("max_lookback_candles", 20)
        
        if fvg_index < 1 or fvg_index >= len(ohlcv_data):
            return False
        
        # Volumen de la vela de expansión
        expansion_candle = ohlcv_data[fvg_index]
        expansion_volume = expansion_candle.get("volume", 0)
        
        if expansion_volume < min_volume_avg:
            return False
        
        # Volumen promedio de velas anteriores
        lookback_start = max(0, fvg_index - lookback)
        preceding_volumes = [
            ohlcv_data[i].get("volume", 0) 
            for i in range(lookback_start, fvg_index)
        ]
        
        if not preceding_volumes:
            return expansion_volume >= min_volume_avg
        
        avg_volume = sum(preceding_volumes) / len(preceding_volumes)
        
        # Confirmación: volumen expansión debe ser 1.3x + promedio anterior
        is_confirmed = expansion_volume >= (avg_volume * volume_ratio)
        
        logger.debug(
            f"[{self.trace_id}] Volume validation: "
            f"expansion={expansion_volume}, avg={avg_volume:.1f}, "
            f"ratio={volume_ratio}, confirmed={is_confirmed}"
        )
        
        return is_confirmed
    
    async def detect_imbalances_async(self, ohlcv_data: List[Dict[str, float]], 
                                     pip_size: float, timeframe: str) -> Dict[str, Any]:
        """
        Detecta imbalances de forma asíncrona (no-bloqueante).
        
        Args:
            ohlcv_data: Lista de velas OHLCV
            pip_size: Tamaño del pip
            timeframe: Timeframe de los datos
            
        Returns:
            Dict con resultado de detección
            {
                "fvgs": [lista de FVGs],
                "timeframe": "M5",
                "confirmed_fvgs": [FVGs con validación de volumen],
                "timestamp": datetime,
                "trace_id": string
            }
        """
        # Ejecutar en executor para no bloquear
        loop = asyncio.get_event_loop()
        
        fvgs = await loop.run_in_executor(
            None,
            self.detect_fvg,
            ohlcv_data,
            pip_size,
            timeframe
        )
        
        # Validar cada FVG con volumen
        confirmed_fvgs = []
        for fvg in fvgs:
            is_confirmed = self.validate_institutional_footprint(
                ohlcv_data,
                fvg["index"]
            )
            if is_confirmed:
                fvg["institutional_footprint_confirmed"] = True
                confirmed_fvgs.append(fvg)
        
        result = {
            "fvgs": fvgs,
            "confirmed_fvgs": confirmed_fvgs,
            "timeframe": timeframe,
            "fvg_count": len(fvgs),
            "confirmed_count": len(confirmed_fvgs),
            "timestamp": datetime.now(tz=ZoneInfo("UTC")),
            "trace_id": self.trace_id
        }
        
        logger.debug(
            f"[{self.trace_id}] Async detection complete: "
            f"{len(fvgs)} FVGs ({len(confirmed_fvgs)} confirmed) in {timeframe}"
        )
        
        return result
    
    def generate_signal(self, instrument: str, fvgs: List[Dict[str, Any]], 
                       timeframe: str, confidence: float) -> Dict[str, Any]:
        """
        Genera señal de imbalance para el SignalFactory.
        
        Args:
            instrument: Símbolo del instrumento (ej. "EURUSD")
            fvgs: Lista de FVGs detectados
            timeframe: Timeframe de la señal
            confidence: Nivel de confianza (0-1)
            
        Returns:
            Dict con estructura de señal (incluye UUID v4 como instance_id)
            {
                "strategy_class_id": "BRK_OPEN_0001",
                "mnemonic": "BRK_OPEN_NY_STRIKE",
                "instance_id": "<UUID v4>",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "fvg_count": 3,
                "confidence": 0.85,
                "timestamp": datetime,
                "trace_id": string
            }
        """
        instance_id = str(uuid.uuid4())  # UUID v4
        
        signal = {
            "strategy_class_id": "IMBALANCE_DETECTOR_BASE",
            "mnemonic": f"IMBALANCE_{timeframe}_{instrument}",
            "instance_id": instance_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "fvg_count": len(fvgs),
            "fvgs": fvgs,
            "confidence": confidence,
            "timestamp": datetime.now(tz=ZoneInfo("UTC")),
            "trace_id": self.trace_id
        }
        
        logger.debug(
            f"[{self.trace_id}] Signal generated: "
            f"instance_id={instance_id}, fvgs={len(fvgs)}, confidence={confidence}"
        )
        
        return signal
    
    def persist_imbalances(self, instrument: str, fvgs: List[Dict[str, Any]], 
                          timeframe: str) -> bool:
        """
        Persiste imbalances detectados en la base de datos.
        
        Args:
            instrument: Símbolo del instrumento
            fvgs: Lista de FVGs detectados
            timeframe: Timeframe de los datos
            
        Returns:
            True si persistencia fue exitosa, False en caso contrario
        """
        if not fvgs:
            return True  # Nada que persistir
        
        try:
            state_key = f"imbalances_{instrument}_{timeframe}"
            state_value = {
                "instrument": instrument,
                "timeframe": timeframe,
                "fvgs": fvgs,
                "timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
                "trace_id": self.trace_id
            }
            
            self.storage.set_system_state(state_key, state_value)
            logger.debug(
                f"[{self.trace_id}] Persisted {len(fvgs)} imbalances "
                f"for {instrument}/{timeframe}"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error persisting imbalances: {e}"
            )
            return False
    
    def sync_ledger(self, instrument: str, fvgs: List[Dict[str, Any]], 
                   timeframe: str) -> Dict[str, Any]:
        """
        Sincroniza ledger de detecciones de imbalance.
        
        Args:
            instrument: Símbolo del instrumento
            fvgs: Lista de FVGs detectados
            timeframe: Timeframe de los datos
            
        Returns:
            Dict con resultado de sincronización y trazabilidad
        """
        sync_data = {
            "instrument": instrument,
            "timeframe": timeframe,
            "fvg_count": len(fvgs),
            "fvgs": fvgs,
            "timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
            "trace_id": self.trace_id
        }
        
        try:
            self.storage.set_system_state(
                f"imbalance_ledger_{instrument}_{timeframe}",
                sync_data
            )
            logger.debug(
                f"[{self.trace_id}] Ledger synced: "
                f"{instrument}/{timeframe} ({len(fvgs)} FVGs)"
            )
        except Exception as e:
            logger.error(f"[{self.trace_id}] Ledger sync error: {e}")
        
        return sync_data
