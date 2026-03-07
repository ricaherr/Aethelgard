"""
Conflict Resolver - Resolución de Señales Conflictivas

Responsabilidad:
  - Detectar conflictos cuando múltiples estrategias envían señales
    contradictorias en el mismo activo (e.g., S-0004 SELL, S-0006 BUY)
  - Seleccionar la estrategia ganadora basada en:
    1. Asset Affinity Score (importancia del activo para la estrategia)
    2. Signal Confluence Strength (fuerza de la señal detectada)
    3. Market Regime Alignment (alineación con régimen actual)
  - Bloqueado por FundamentalGuard (veto absoluto)

Principio: Exclusión Mutua
  - Solo UNA estrategia ejecuta por activo en cualquier momento
  - Las demás entran en estado PENDING hasta que se cierre la posición

Architecture:
  - Agnóstico de broker (sin imports broker-specific)
  - Inyección de dependencias: StorageManager, RegimeClassifier
  - Logging con TRACE_ID para auditoría

TRACE_ID: EXEC-ORCHESTRA-001
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from models.signal import Signal, MarketRegime

logger = logging.getLogger(__name__)


class ConflictResolver:
    """
    Resuelve conflictos entre señales de múltiples estrategias
    aplicando una jerarquía de prioridades determinista.
    
    NOTA: Este es el "árbitro" que implementa la Ley de Orquestación
    descrita en MANIFESTO Sección XI.
    """
    
    def __init__(self, storage, regime_classifier, fundamental_guard=None):
        """
        Inicializa ConflictResolver con inyección de dependencias.
        
        Args:
            storage: StorageManager (para affinity scores)
            regime_classifier: RegimeClassifier (para validación régimen)
            fundamental_guard: FundamentalGuardService (opcional, para veto)
        """
        self.storage = storage
        self.regime_classifier = regime_classifier
        self.fundamental_guard = fundamental_guard
        self._pending_usr_signals: Dict[str, List[Signal]] = {}  # asset -> [usr_signals]
        self._active_usr_signals: Dict[str, Signal] = {}  # asset -> winner signal
        
        logger.info("[RESOLVER] ConflictResolver initialized with DI")
    
    def resolve_conflicts(
        self,
        usr_signals: List[Signal],
        current_regime: MarketRegime,
        trace_id: str = ""
    ) -> Tuple[List[Signal], Dict[str, List[Signal]]]:
        """
        Resuelve conflictos entre señales y devuelve:
        1. Señales aprobadas para ejecución (ganadores)
        2. Señales en PENDING (perdedores)
        
        ALGORITMO (Sección XI MANIFESTO):
        ─────────────────────────────────
        
        PASO 1: FundamentalGuard (Veto Absoluto)
        IF fundamental_guard.is_active():
            IF veto_level == ABSOLUTE:
                RETURN [], {all_assets: [all_usr_signals]}  # TODO: NADA
        
        PASO 2: Detectar Conflictos (mismo activo, direcciones opuestas)
        FOR each asset IN [EUR/USD, GBP/USA, etc]:
            conflicting_usr_signals = [s for s in usr_signals if s.symbol == asset]
            IF len(conflicting_usr_signals) > 1:
                CREAR CONFLICTO
        
        PASO 3: Validar Régimen
        FOR each signal:
            IF signal.strategy NOT in regime_classifier.compatible_usr_strategies(regime):
                BLOQUEAR signal por régimen
        
        PASO 4: Computar Prioridades
        FOR each signal:
            priority = Asset_Affinity * Signal_Confluence * Regime_Alignment
        
        PASO 5: Seleccionar Gananador por Activo
        FOR each asset:
            winner = signal_with_highest_priority
            losers = [other_usr_signals]
        
        PASO 6: Aplicar Risk Scaling
        FOR each winner:
            winner.risk_adjusted = winner.risk * regime_risk_multiplier(regime)
        
        Args:
            usr_signals: Lista de señales a procesar
            current_regime: Régimen de mercado actual
            trace_id: ID de traza para auditoría
            
        Returns:
            Tuple (approved_usr_signals, pending_usr_signals_by_asset)
        """
        
        if not usr_signals:
            return [], {}
        
        try:
            logger.info(f"[RESOLVER] Processing {len(usr_signals)} usr_signals | Regime={current_regime} | Trace={trace_id}")
            
            # PASO 1: Validar FundamentalGuard
            if self.fundamental_guard and self._is_fundamental_guard_blocking():
                logger.warning("[RESOLVER] ⛔ FUNDAMENTAL GUARD ACTIVE - LOCKDOWN. All usr_signals rejected.")
                return [], {s.symbol: [s] for s in usr_signals}
            
            # PASO 2: Agrupar señales por activo
            usr_signals_by_asset = self._group_usr_signals_by_asset(usr_signals)
            
            # PASO 3: Validar régimen y calcular prioridades
            priority_map = self._compute_signal_priorities(
                usr_signals,
                current_regime,
                trace_id
            )
            
            # PASO 4: Seleccionar ganadores y perdedores
            approved_usr_signals = []
            pending_usr_signals_by_asset = {}
            
            for asset, asset_usr_signals in usr_signals_by_asset.items():
                if len(asset_usr_signals) == 1:
                    # Sin conflicto, automáticamente aprobada
                    signal = asset_usr_signals[0]
                    if priority_map.get(signal.symbol, -1) >= 0:  # No bloqueada por régimen
                        approved_usr_signals.append(signal)
                        # Guardar como activa
                        self._active_usr_signals[asset] = signal
                        logger.info(f"[RESOLVER] [OK] {asset}: {signal.strategy} APPROVED (no conflict)")
                    else:
                        # Bloqueada por régimen
                        pending_usr_signals_by_asset.setdefault(asset, []).append(signal)
                        logger.info(f"[RESOLVER] [VETO] {asset}: {signal.strategy} BLOCKED (regime mismatch)")
                else:
                    # Conflicto detectado: múltiples estrategias en mismo activo
                    winner = self._select_winner_by_priority(
                        asset_usr_signals,
                        priority_map,
                        trace_id
                    )
                    
                    if winner:
                        approved_usr_signals.append(winner)
                        self._active_usr_signals[asset] = winner
                        logger.info(f"[RESOLVER] [WINNER] {asset}: {winner.strategy} (priority={priority_map.get(winner.symbol, 0):.3f})")
                        
                        # Losers go to PENDING
                        for signal in asset_usr_signals:
                            if signal.symbol != winner.symbol:
                                pending_usr_signals_by_asset.setdefault(asset, []).append(signal)
                                logger.info(f"[RESOLVER] [PENDING] {asset}: {signal.strategy} (will execute when {winner.strategy} closes)")
                    else:
                        # Todos bloqueados por régimen
                        pending_usr_signals_by_asset[asset] = asset_usr_signals
                        logger.warning(f"[RESOLVER] [REGIME_VETO] {asset}: All {len(asset_usr_signals)} usr_signals blocked by regime")
            
            # PASO 5: Aplicar Risk Scaling por régimen
            for signal in approved_usr_signals:
                signal.risk_adjusted = self._apply_risk_scaling(signal, current_regime)
            
            logger.info(f"[RESOLVER] Result: {len(approved_usr_signals)} approved, "
                       f"{sum(len(v) for v in pending_usr_signals_by_asset.values())} pending")
            
            return approved_usr_signals, pending_usr_signals_by_asset
        
        except Exception as e:
            logger.error(f"[RESOLVER] EXCEPTION in resolve_conflicts: {str(e)} | Trace={trace_id}")
            # Fallback seguro: rechazar todos
            return [], {s.symbol: [s] for s in usr_signals if usr_signals}
    
    def _is_fundamental_guard_blocking(self) -> bool:
        """Verifica si FundamentalGuard está activo con VETO ABSOLUTO."""
        if not self.fundamental_guard:
            return False
        
        if hasattr(self.fundamental_guard, 'is_active'):
            if not self.fundamental_guard.is_active():
                return False
            
            # Verificar nivel de veto
            veto_level = getattr(self.fundamental_guard, 'veto_level', 'CAUTION')
            if veto_level == 'ABSOLUTE':
                reason = getattr(self.fundamental_guard, 'reason', 'Unknown')
                logger.warning(f"[FUNDAMENTAL_GUARD] ABSOLUTE VETO: {reason}")
                return True
        
        return False
    
    def _group_usr_signals_by_asset(self, usr_signals: List[Signal]) -> Dict[str, List[Signal]]:
        """Agrupa señales por símbolo/activo."""
        grouped = {}
        for signal in usr_signals:
            asset = signal.symbol
            if asset not in grouped:
                grouped[asset] = []
            grouped[asset].append(signal)
        return grouped
    
    def _compute_signal_priorities(
        self,
        usr_signals: List[Signal],
        regime: MarketRegime,
        trace_id: str
    ) -> Dict[str, float]:
        """
        Calcula Priority Score para cada señal usando:
        
        Priority = Asset_Affinity * Signal_Confluence * Regime_Alignment_Factor
        
        Returns:
            Dict[signal.symbol] = priority_score (or -1 if regime-blocked)
        """
        priority_map = {}
        
        for signal in usr_signals:
            asset = signal.symbol
            strategy_id = getattr(signal, 'strategy', 'UNKNOWN')
            
            # 1. Asset Affinity Score
            affinity_score = self._get_asset_affinity_score(strategy_id, asset)
            if affinity_score <= 0:
                priority_map[signal.symbol] = -1  # Asset not in whitelist
                logger.debug(f"[PRIORITY] {asset}/{strategy_id}: Affinity=0 (not in whitelist)")
                continue
            
            # 2. Signal Confluence Strength (0-1)
            confluence = self._get_signal_confluence(signal)
            
            # 3. Regime Alignment Factor (1 or 0)
            regime_alignment = self._check_regime_alignment(strategy_id, regime)
            
            if regime_alignment == 0:
                # Blocked by regime
                priority_map[signal.symbol] = -1
                logger.debug(f"[PRIORITY] {asset}/{strategy_id}: Regime={regime} not compatible -> BLOCKED")
                continue
            
            # Computar prioridad
            priority = affinity_score * confluence * regime_alignment
            priority_map[signal.symbol] = priority
            
            logger.debug(
                f"[PRIORITY] {asset}/{strategy_id}: "
                f"priority={priority:.4f} (affinity={affinity_score:.3f}, "
                f"confluence={confluence:.3f}, regime_align={regime_alignment})"
            )
        
        return priority_map
    
    def _get_asset_affinity_score(self, strategy_id: str, asset: str) -> float:
        """
        Obtiene el Asset Affinity Score de una estrategia para un activo.
        
        Rango: 0-1 (0=no autorizado, 1=óptimo)
        """
        try:
            scores = self.storage.get_strategy_affinity_scores()
            if not scores:
                return 0.5  # Default si no hay scores registrados
            
            # Acces nested dict: scores[strategy_id][asset]
            if isinstance(scores, dict) and strategy_id in scores:
                strategy_scores = scores[strategy_id]
                if isinstance(strategy_scores, dict) and asset in strategy_scores:
                    return float(strategy_scores[asset])
            
            return 0.0  # No autorizado para este activo
        except Exception as e:
            logger.warning(f"Error getting affinity score for {strategy_id}/{asset}: {e}")
            return 0.0
    
    def _get_signal_confluence(self, signal: Signal) -> float:
        """
        Obtiene la fuerza de confluencia de la señal (0-1).
        
        Basado en:
        - Número de confirmadores (pivots, patrones, indicadores)
        - Completitud de datos
        """
        # Usar atributo 'confidence' si disponible
        confidence = getattr(signal, 'confidence', 0.70)
        return min(1.0, max(0.0, confidence))
    
    def _check_regime_alignment(self, strategy_id: str, regime: MarketRegime) -> int:
        """
        Verifica si una estrategia es compatible con el régimen actual.
        
        Returns:
            1 si compatible, 0 si bloqueada por régimen
        """
        try:
            # Obtener estrategias compatibles con este régimen
            compatible = self._get_compatible_usr_strategies_for_regime(regime)
            
            # Verificar si strategy_id está en la lista
            is_compatible = strategy_id in compatible
            
            return 1 if is_compatible else 0
        except Exception as e:
            logger.warning(f"Error checking regime alignment for {strategy_id}: {e}")
            return 0
    
    def _get_compatible_usr_strategies_for_regime(self, regime: MarketRegime) -> List[str]:
        """
        Retorna lista de estrategias compatibles con el régimen.
        
        Matriz definida en MANIFESTO Sección XI:
        ─────────────────────────────────────────
        TREND_UP → [BRK_OPEN, STRUC_SHIFT_UP, SESS_EXT]
        TREND_DOWN → [STRUC_SHIFT_DOWN, CONV_STRIKE_DOWN]
        RANGE → [MOM_BIAS, CONV_STRIKE_RANGE]
        VOLATILE → [BRK_OPEN, SESS_EXT]
        """
        regime_matrix = {
            MarketRegime.TREND: [
                "BRK_OPEN_0001", "STRUC_SHIFT_0001", "SESS_EXT_0001"
            ],
            MarketRegime.RANGE: [
                "MOM_BIAS_0001", "CONV_STRIKE_0001"
            ],
            MarketRegime.VOLATILE: [
                "BRK_OPEN_0001", "SESS_EXT_0001"
            ],
            MarketRegime.SHOCK: [
                "SESS_EXT_0001"  # Only extension usr_strategies in shock
            ],
            MarketRegime.EXPANSION: [
                "BRK_OPEN_0001", "SESS_EXT_0001"
            ]
        }
        
        return regime_matrix.get(regime, [])
    
    def _select_winner_by_priority(
        self,
        conflicting_usr_signals: List[Signal],
        priority_map: Dict[str, float],
        trace_id: str
    ) -> Optional[Signal]:
        """
        Selecciona la señal ganadora entre conflictivas.
        
        Logic:
        1. Filtrar señales bloqueadas por régimen (priority == -1)
        2. Seleccionar con máxima prioridad
        """
        # Filtrar no-bloqueadas
        valid_usr_signals = [
            s for s in conflicting_usr_signals
            if priority_map.get(s.symbol, -1) >= 0
        ]
        
        if not valid_usr_signals:
            return None
        
        # Seleccionar máxima prioridad
        winner = max(valid_usr_signals, key=lambda s: priority_map.get(s.symbol, 0))
        return winner
    
    def _apply_risk_scaling(self, signal: Signal, regime: MarketRegime) -> float:
        """
        Aplica ajuste de riesgo según el régimen.
        
        Matriz de escalado (Sección XI MANIFESTO):
        ──────────────────────────────────────────
        TREND → 1.0× (Risk normal)
        RANGE → 0.75× (Reducido, menos tendencia)
        VOLATILE → 0.5× (Muy reducido, slippage alto)
        EXPANSION → 0.5× (Reducido, volatilidad extrema)
        SHOCK → 0.5× (Minimizado)
        """
        base_risk = getattr(signal, 'risk_per_trade', 0.01)  # Default 1%
        
        risk_multiplier = {
            MarketRegime.TREND: 1.0,
            MarketRegime.RANGE: 0.75,
            MarketRegime.VOLATILE: 0.5,
            MarketRegime.EXPANSION: 0.5,
            MarketRegime.SHOCK: 0.5,
        }.get(regime, 0.75)
        
        adjusted_risk = base_risk * risk_multiplier
        
        logger.debug(
            f"[RISK_SCALING] {signal.symbol}/{getattr(signal, 'strategy', 'UNKNOWN')}: "
            f"{base_risk:.2%} × {risk_multiplier} = {adjusted_risk:.2%} ({regime})"
        )
        
        return adjusted_risk
    
    def get_active_usr_signals(self) -> Dict[str, Signal]:
        """Retorna todas las señales activas (ganadoras) por activo."""
        return self._active_usr_signals.copy()
    
    def get_pending_usr_signals(self, asset: Optional[str] = None) -> List[Signal]:
        """Retorna todas las señales en PENDING, opcionalmente filtradas por activo."""
        if asset:
            return self._pending_usr_signals.get(asset, [])
        
        all_pending = []
        for usr_signals_list in self._pending_usr_signals.values():
            all_pending.extend(usr_signals_list)
        
        return all_pending
    
    def clear_active_signal(self, asset: str) -> None:
        """Limpia la señal activa cuando una posición se cierra."""
        if asset in self._active_usr_signals:
            del self._active_usr_signals[asset]
            logger.info(f"[RESOLVER] Active signal cleared for {asset}")
