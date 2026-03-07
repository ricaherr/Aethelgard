"""
Motor de Unificación Temporal (Fractal Time Sense Engine).
Sincroniza regímenes entre M15, H1 y H4 para detectar conflictos fractales.

Regla de Veto Fractal (Regla 1.5):
- Si H4=Bearish Y M15=Bullish → RETRACEMENT_RISK
- Elevar confidence a 0.90 para evitar "Long suicidas"
"""

import logging
import uuid
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime

from models.signal import MarketRegime, FractalContext, Signal, SignalType
from core_brain.regime import RegimeClassifier
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class RegimeService:
    """
    Sincronizador de temporalidades (M15, H1, H4).
    Implementa el Fractal Time Sense para evitar operaciones contra tendencia multi-temporal.
    """

    # Fractal Conflict Matrix: (H4, M15) → veto signal
    FRACTAL_VETOES = {
        (MarketRegime.BEAR, MarketRegime.BULL): "RETRACEMENT_RISK",
        (MarketRegime.CRASH, MarketRegime.BULL): "CATASTROPHIC_CONFLICT",
        (MarketRegime.VOLATILE, MarketRegime.BULL): "VOLATILITY_TRAP",
    }

    def __init__(self, storage: StorageManager):
        """
        Initializa el RegimeService con inyección de dependencias.
        
        Args:
            storage: StorageManager para persistencia del ledger fractal.
        """
        self.storage = storage
        self.trace_id = f"REGIME-{uuid.uuid4().hex[:8].upper()}"
        
        # Clasificadores por timeframe
        self.m15_classifier: Optional[RegimeClassifier] = None
        self.h1_classifier: Optional[RegimeClassifier] = None
        self.h4_classifier: Optional[RegimeClassifier] = None
        
        # Cache de contexto fractal
        self._last_context: Optional[FractalContext] = None
        self._context_timestamp: Optional[datetime] = None
        
        logger.info(f"[RegimeService] Inicializado con Trace ID: {self.trace_id}")

    def initialize_classifiers(
        self,
        m15_df: Optional[Any] = None,
        h1_df: Optional[Any] = None,
        h4_df: Optional[Any] = None
    ) -> None:
        """
        Inicializa los clasificadores de régimen para las 3 temporalidades.
        
        Args:
            m15_df: DataFrame OHLCV para M15
            h1_df: DataFrame OHLCV para H1
            h4_df: DataFrame OHLCV para H4
        """
        self.m15_classifier = RegimeClassifier(storage=self.storage)
        self.h1_classifier = RegimeClassifier(storage=self.storage)
        self.h4_classifier = RegimeClassifier(storage=self.storage)
        
        if m15_df is not None:
            self.m15_classifier.load_ohlc(m15_df)
        if h1_df is not None:
            self.h1_classifier.load_ohlc(h1_df)
        if h4_df is not None:
            self.h4_classifier.load_ohlc(h4_df)
            
        logger.info(f"[{self.trace_id}] Clasificadores inicializados (M15, H1, H4)")

    def update_regime_data(
        self,
        m15_close: Optional[float] = None,
        m15_ohlc: Optional[Dict[str, float]] = None,
        h1_close: Optional[float] = None,
        h1_ohlc: Optional[Dict[str, float]] = None,
        h4_close: Optional[float] = None,
        h4_ohlc: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Actualiza datos de precios en los clasificadores.
        Garantiza sincronización de ledger tras la primera función.
        """
        if self.m15_classifier is None or self.h1_classifier is None or self.h4_classifier is None:
            logger.warning(f"[{self.trace_id}] Clasificadores no inicializados. Abortando update_regime_data.")
            return

        # M15
        if m15_ohlc:
            self.m15_classifier.add_candle(
                close=m15_ohlc.get("close", 0),
                high=m15_ohlc.get("high"),
                low=m15_ohlc.get("low"),
                open_price=m15_ohlc.get("open")
            )
        elif m15_close is not None:
            self.m15_classifier.add_candle(close=m15_close)
        
        # H1
        if h1_ohlc:
            self.h1_classifier.add_candle(
                close=h1_ohlc.get("close", 0),
                high=h1_ohlc.get("high"),
                low=h1_ohlc.get("low"),
                open_price=h1_ohlc.get("open")
            )
        elif h1_close is not None:
            self.h1_classifier.add_candle(close=h1_close)
        
        # H4
        if h4_ohlc:
            self.h4_classifier.add_candle(
                close=h4_ohlc.get("close", 0),
                high=h4_ohlc.get("high"),
                low=h4_ohlc.get("low"),
                open_price=h4_ohlc.get("open")
            )
        elif h4_close is not None:
            self.h4_classifier.add_candle(close=h4_close)
        
        # 🔄 SINCRONIZACIÓN DE LEDGER: Registrar cambios después de actualizar
        self._sync_ledger()

    def _sync_ledger(self) -> None:
        """
        Sincroniza el estado del régimen fractal con el ledger en la BD.
        Se invoca automáticamente tras update_regime_data() (primera función del servicio).
        """
        try:
            context = self.get_fractal_context()
            if context:
                # Persistir en sys_config bajo clave "regime_fractal_ledger"
                ledger_entry = {
                    "trace_id": self.trace_id,
                    "timestamp": datetime.now().isoformat(),
                    "m15_regime": context.m15_regime.value,
                    "h1_regime": context.h1_regime.value,
                    "h4_regime": context.h4_regime.value,
                    "veto_signal": context.veto_signal,
                    "confidence_threshold": context.confidence_threshold,
                    "alignment_score": context.alignment_score,
                }
                
                # Usar storage para persisten (esta es la SSOT)
                self.storage.set_sys_config(
                    key="regime_fractal_ledger",
                    value=ledger_entry
                )
                logger.debug(f"[{self.trace_id}] Ledger sincronizado: {context.veto_signal or 'ALIGNED'}")
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error sincronizando ledger: {e}")

    def get_fractal_context(self) -> Optional[FractalContext]:
        """
        Construye el contexto fractal actual a partir de las 3 temporalidades.
        Evalúa la Regla de Veto Fractal.
        
        Returns:
            FractalContext con información de alineación y vetoes.
        """
        if self.m15_classifier is None or self.h1_classifier is None or self.h4_classifier is None:
            logger.warning(f"[{self.trace_id}] Clasificadores no inicializados.")
            return None

        m15_regime = self.m15_classifier.classify()
        h1_regime = self.h1_classifier.classify()
        h4_regime = self.h4_classifier.classify()

        # Crear contexto
        context = FractalContext(
            m15_regime=m15_regime,
            h1_regime=h1_regime,
            h4_regime=h4_regime,
            trace_id=self.trace_id
        )

        # Evaluar matriz de vetoes
        veto_key = (h4_regime, m15_regime)
        if veto_key in self.FRACTAL_VETOES:
            context.veto_signal = self.FRACTAL_VETOES[veto_key]
            # Elevar confianza a 0.90 para todos los vetoes fractales
            context.confidence_threshold = 0.90
        else:
            context.veto_signal = "ALIGNED" if context.is_fractally_aligned else "PARTIAL_CONFLICT"

        self._last_context = context
        self._context_timestamp = datetime.now()
        return context

    def apply_veto_to_signal(self, signal: Signal) -> Signal:
        """
        Aplica la Regla de Veto Fractal a una señal.
        
        Si el veto está activo, modifica metadata y confianza:
        - Añade tag [RETRACEMENT_RISK] a metadatos
        - Eleva confidence a 0.90
        
        Args:
            signal: Señal a procesar
            
        Returns:
            Señal modificada con veto aplicado si aplica.
        """
        context = self.get_fractal_context()
        if context is None or context.veto_signal is None:
            return signal

        if context.veto_signal in ["RETRACEMENT_RISK", "CATASTROPHIC_CONFLICT", "VOLATILITY_TRAP"]:
            # Añadir tag en metadata
            if "tags" not in signal.metadata:
                signal.metadata["tags"] = []
            if isinstance(signal.metadata["tags"], list):
                signal.metadata["tags"].append(f"[{context.veto_signal}]")
            
            # Elevar confianza a threshold de veto
            signal.confidence = context.confidence_threshold
            
            # Log de auditoría
            logger.warning(
                f"[{self.trace_id}] VETO FRACTAL APLICADO: {context.veto_signal} "
                f"(H4={context.h4_regime.value}, M15={context.m15_regime.value}). "
                f"Confianza elevada a {context.confidence_threshold}"
            )

        return signal

    def get_alignment_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas de alineación para visualización en UI.
        
        Returns:
            Dict con información de alineación, vetoes y métricas de régimen.
        """
        context = self.get_fractal_context()
        if context is None:
            return {"status": "UNINITIALIZED"}

        metrics = {
            "m15_regime": context.m15_regime.value,
            "h1_regime": context.h1_regime.value,
            "h4_regime": context.h4_regime.value,
            "is_aligned": context.is_fractally_aligned,
            "alignment_score": context.alignment_score,
            "veto_signal": context.veto_signal,
            "confidence_threshold": context.confidence_threshold,
            "timestamp": context.timestamp.isoformat(),
        }

        # Añadir métricas técnicas de cada régimen
        if self.m15_classifier:
            metrics["m15_metrics"] = self.m15_classifier.get_metrics()
        if self.h1_classifier:
            metrics["h1_metrics"] = self.h1_classifier.get_metrics()
        if self.h4_classifier:
            metrics["h4_metrics"] = self.h4_classifier.get_metrics()

        return metrics

    def get_veto_status(self) -> Tuple[bool, Optional[str]]:
        """
        Retorna estado de veto para control de flujo.
        
        Returns:
            (is_vetoed: bool, veto_reason: Optional[str])
        """
        context = self.get_fractal_context()
        if context is None:
            return False, None

        is_vetoed = context.veto_signal in [
            "RETRACEMENT_RISK",
            "CATASTROPHIC_CONFLICT",
            "VOLATILITY_TRAP"
        ]
        return is_vetoed, context.veto_signal if is_vetoed else None

    def reload_params(self) -> None:
        """
        Recarga parámetros dinámicos desde Storage (SSOT).
        Propaga a los 3 clasificadores.
        """
        if self.m15_classifier:
            self.m15_classifier.reload_params()
        if self.h1_classifier:
            self.h1_classifier.reload_params()
        if self.h4_classifier:
            self.h4_classifier.reload_params()
        
        logger.info(f"[{self.trace_id}] Parámetros recargados desde Storage (SSOT)")
