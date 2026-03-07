"""
Signal Deduplicator - Detección y Prevención de Señales Duplicadas
===================================================================

Responsabilidad única: Verificar si una señal es duplicado basado en:
1. Posición abierta existente (conflict check)
2. Señales recientes (temporal check)
3. Reconciliación con MT5 (reality check)
"""
import logging
from typing import Optional

from models.signal import Signal, ConnectorType
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class SignalDeduplicator:
    """
    Detecta si una señal es duplicado y previene execuciones inválidas.
    
    Responsabilidades:
    1. Normalizar símbolos según connector type
    2. Verificar posiciones abiertas
    3. Reconciliar con MT5 reality
    4. Detectar ghost usr_positions
    5. Filtrar señales recientes
    """
    
    def __init__(
        self,
        storage_manager: StorageManager,
        mt5_connector: Optional[object] = None
    ):
        """
        Inicializa el deduplicador.
        
        Args:
            storage_manager: Para acceder a BD
            mt5_connector: Para reconciliación (opcional)
        """
        self.storage_manager = storage_manager
        self.mt5_connector = mt5_connector
    
    def is_duplicate(self, signal: Signal) -> bool:
        """
        Verifica si la señal es un duplicado.
        
        Criterios de deduplicación (clave única: symbol + signal_type + timeframe):
        - Ya existe posición abierta para el símbolo
        - Ya existe señal reciente para el mismo (symbol, signal_type, timeframe)
        
        Esto permite señales del MISMO instrumento en DIFERENTES timeframes.
        Ejemplo: EURUSD BUY en M5 (scalping) y EURUSD BUY en H4 (swing) son válidas.
        
        Args:
            signal: Señal a validar
        
        Returns:
            True si es duplicado, False si es válida
        """
        # Normalizar símbolo según connector type
        normalized_symbol = self._normalize_symbol(signal)
        signal_type_str = self._get_signal_type_str(signal)
        
        # ──────────────────────────────────────────────────────────────────────────────────
        # Verificar 1: Posición Abierta (conflict check)
        # ──────────────────────────────────────────────────────────────────────────────────
        if self.storage_manager.has_open_position(normalized_symbol, signal.timeframe):
            if self._handle_open_position(signal, normalized_symbol):
                return True
        
        # ──────────────────────────────────────────────────────────────────────────────────
        # Verificar 2: Señales Recientes (temporal check)
        # ──────────────────────────────────────────────────────────────────────────────────
        if self.storage_manager.has_recent_signal(
            normalized_symbol, 
            signal_type_str, 
            timeframe=signal.timeframe
        ):
            logger.info(
                f"[DUPLICATE] Signal for {normalized_symbol} ({signal_type_str} {signal.timeframe}) "
                f"skipped (Normalized from {signal.symbol})"
            )
            return True
        
        return False
    
    def _normalize_symbol(self, signal: Signal) -> str:
        """
        Normaliza símbolo según connector type.
        
        Ejemplo: "GBPUSD=X" (Yahoo) → "GBPUSD" (MT5)
        """
        normalized_symbol = signal.symbol
        
        if signal.connector_type == ConnectorType.METATRADER5:
            try:
                from connectors.mt5_connector import MT5Connector
                normalized_symbol = MT5Connector.normalize_symbol(signal.symbol)
            except ImportError:
                normalized_symbol = signal.symbol.replace("=X", "")
            except Exception as e:
                logger.warning(f"Normalization failed: {e}")
        
        return normalized_symbol
    
    @staticmethod
    def _get_signal_type_str(signal: Signal) -> str:
        """Extrae string del tipo de señal (BUY/SELL)."""
        return (
            signal.signal_type.value 
            if hasattr(signal.signal_type, 'value') 
            else str(signal.signal_type)
        )
    
    def _handle_open_position(self, signal: Signal, normalized_symbol: str) -> bool:
        """
        Maneja caso de posición abierta existente.
        
        Intenta reconciliar con MT5, limpia ghost usr_positions.
        
        Returns:
            True si debe bloquearse la señal, False para permitir
        """
        if self.mt5_connector:
            return self._reconcile_with_mt5(signal, normalized_symbol)
        else:
            # Sin MT5, asumir existe la posición
            self._log_rejection_dump(
                signal,
                "Posición abierta (sin MT5 para verificar)"
            )
            return True
    
    def _reconcile_with_mt5(self, signal: Signal, normalized_symbol: str) -> bool:
        """
        Reconcilia posición en BD con realidad en MT5.
        
        Detecta y limpia ghost usr_positions.
        
        Returns:
            True si debe bloquearse, False para permitir
        """
        logger.debug(f"[CHECK] Reconciling position for {signal.symbol} with MT5")
        
        # Obtener todas las operaciones abiertas (usr_signals con status=EXECUTED)
        open_ops = self.storage_manager.get_open_operations()
        matching_op = next(
            (op for op in open_ops if op.get('symbol') == normalized_symbol),
            None
        )
        
        if not matching_op:
            return False
        
        open_signal_id = matching_op.get('id')
        
        # Obtener posiciones reales de MT5
        real_usr_positions = self.mt5_connector.get_open_usr_positions()
        if real_usr_positions is None:
            logger.warning("Failed to get MT5 usr_positions for reconciliation")
            return True
        
        real_symbols = {pos.get('symbol') for pos in real_usr_positions}
        
        if normalized_symbol not in real_symbols:
            # Ghost position detected - limpiar
            self.storage_manager._clear_ghost_position_inline(normalized_symbol)
            logger.info(f"[CLEAN] Cleared ghost position for {normalized_symbol} (ID: {open_signal_id})")
            
            # Registrar EDGE Learning
            self.storage_manager.save_edge_learning(
                detection=f"Discrepancia DB vs MT5: {signal.symbol} en DB pero no en MT5",
                action_taken="Limpieza de registros fantasma",
                learning="El delay de cierre en MT5 es ~200ms, ajustar timeout",
                details=f"Signal ID: {open_signal_id}"
            )
            
            # Permitir signal después de limpiar
            return False
        else:
            # Posición existe realmente en MT5
            self._log_rejection_dump(signal, "Posición abierta existente")
            return True
    
    @staticmethod
    def _log_rejection_dump(signal: Signal, reason: str) -> None:
        """Registra volcado de diagnóstico cuando se rechaza signal."""
        score = signal.metadata.get('score', 0)
        lot_size = signal.volume
        risk_usd = abs(signal.entry_price - signal.stop_loss) * lot_size * 100000
        
        dump = {
            "Razon": reason,
            "Score": score,
            "LotSize": lot_size,
            "Riesgo_$": round(risk_usd, 2)
        }
        logger.info(f"[DUMP] VOLCADO EXCEPCION: Signal rechazada: {dump}")
