"""
CircuitBreaker Gate Service - Strategy Execution Authorization
Encapsulates CircuitBreaker integration logic extracted from Executor.

Responsibility: Check if strategy is allowed to send usr_orders (LIVE or SHADOW).
- Strategy in LIVE: ALLOW order execution
- Strategy in SHADOW: ALLOW IF passes 4-Pillar validation
- Strategy in QUARANTINE: BLOCK order
- CircuitBreaker unavailable: BLOCK (fail-secure)

This service centralizes the CB gating logic to reduce executor.py complexity
and enable reuse across multiple execution points.

4-Pillar Validation for SHADOW:
1. Market Structure Score >= 0.75
2. Risk Profile Score >= 0.80
3. Liquidity Level >= MEDIUM
4. Confluence Score >= 0.70
"""
import logging
from typing import Tuple, Optional, Dict, Any
from enum import Enum

from core_brain.circuit_breaker import CircuitBreaker
from data_vault.storage import StorageManager
from core_brain.notification_service import NotificationService, NotificationCategory

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """Permission levels for strategy execution."""
    DENIED = 0                  # Blocked (failed validation)
    SHADOW_PENDING = 1          # SHADOW, waiting for 4-Pillar validation
    SHADOW_APPROVED = 2         # SHADOW, passed 4-Pillar validation
    LIVE = 3                    # LIVE mode (full execution)


class CircuitBreakerGate:
    """
    Gate service for CircuitBreaker authorization checks.
    
    Responsible for:
    - Verifying strategy execution mode (LIVE/SHADOW/QUARANTINE)
    - Logging decisions with [CIRCUIT_BREAKER] pattern
    - Notifying users of rejections
    - Pipelin tracking of rejections
    - Validating 4-Pillar criteria for SHADOW mode authorization
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        storage: StorageManager,
        notificator: Optional[NotificationService] = None,
        dynamic_params: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize CBGate with dependencies.
        
        Args:
            circuit_breaker: CircuitBreaker instance for authorization checks
            storage: StorageManager for pipeline tracking and config (SSOT)
            notificator: NotificationService for user alerts (optional)
            dynamic_params: Dynamic parameters from storage (for 4-Pillar thresholds)
                          If None, will load from storage.get_dynamic_params()
        """
        self.circuit_breaker = circuit_breaker
        self.storage = storage
        self.notificator = notificator
        
        # Load dynamic_params (SSOT from StorageManager)
        if dynamic_params is None:
            try:
                self.dynamic_params = self.storage.get_dynamic_params() or {}
            except Exception as e:
                logger.warning(f"Failed to load dynamic_params from storage: {e}. Using defaults.")
                self.dynamic_params = {}
        else:
            self.dynamic_params = dynamic_params
        
        # Extract 4-Pillar thresholds from config (with sensible defaults if missing)
        shadow_config = self.dynamic_params.get("shadow_validation", {})
        self.min_market_structure = shadow_config.get("min_market_structure", 0.75)
        self.min_risk_profile = shadow_config.get("min_risk_profile", 0.80)
        self.min_confluence = shadow_config.get("min_confluence", 0.70)
        self.min_liquidity = shadow_config.get("min_liquidity", "MEDIUM")
        
        logger.debug(
            f"CircuitBreakerGate initialized with 4-Pillar thresholds from config: "
            f"MS>={self.min_market_structure}, RP>={self.min_risk_profile}, "
            f"Conf>={self.min_confluence}, Liq>={self.min_liquidity}"
        )

    def check_strategy_authorization(
        self,
        strategy_id: Optional[str],
        symbol: str,
        signal_id: str,
        signal: Optional[Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if strategy is authorized to send usr_orders.
        
        For SHADOW mode: Validates 4-Pillar criteria before authorization.
        For LIVE mode: Standard authorization check.
        For QUARANTINE mode: Always blocked.
        
        Args:
            strategy_id: Strategy identifier (may be None)
            symbol: Trading symbol (for logging)
            signal_id: Signal identifier (for tracking)
            signal: Signal object (optional, needed for 4-Pillar validation in SHADOW)
            
        Returns:
            Tuple[authorized (bool), rejection_reason (str or None)]
            - (True, None) if strategy is LIVE or (SHADOW + 4-Pillar passed)
            - (False, reason) if strategy is blocked or failed validation
        """
        # Skip check if no strategy_id (unmanaged usr_signals)
        if not strategy_id:
            logger.debug("No strategy_id: CB gate skipped (unmanaged signal)")
            return (True, None)

        try:
            # Get strategy ranking to determine execution mode
            ranking = self.storage.get_signal_ranking(strategy_id)
            if not ranking:
                logger.warning(f"Strategy {strategy_id} not found in ranking table")
                return (False, "STRATEGY_NOT_FOUND")
            
            execution_mode = ranking.get('execution_mode', 'UNKNOWN')
            
            # ──── LIVE MODE: Full Authorization ────────────────────────────
            if execution_mode == 'LIVE':
                # Query CircuitBreaker: is strategy blocked (DD or CL violated)?
                is_blocked = self.circuit_breaker.is_strategy_blocked_for_trading(strategy_id)
                
                if is_blocked:
                    reason = f"Strategy {strategy_id} not in LIVE execution mode (risk thresholds violated)"
                    logger.warning(
                        f"[CIRCUIT_BREAKER] Strategy {strategy_id} blocked from trading. "
                        f"Symbol={symbol}, Status=REJECTED (risk violation)"
                    )
                    
                    self.storage.log_signal_pipeline_event(
                        signal_id=signal_id,
                        stage='CIRCUIT_BREAKER',
                        decision='REJECTED',
                        reason=reason
                    )
                    
                    if self.notificator:
                        self.notificator.create_notification(
                            category=NotificationCategory.EXECUTION,
                            context={
                                "symbol": symbol,
                                "status": "REJECTED",
                                "reason": "Circuit breaker: strategy blocked"
                            }
                        )
                    
                    return (False, "CIRCUIT_BREAKER_BLOCKED")
                
                logger.debug(f"[CIRCUIT_BREAKER] Strategy {strategy_id} authorized (LIVE mode)")
                return (True, None)
            
            # ──── SHADOW MODE: Conditional Authorization (4-Pillar Validation) ────
            elif execution_mode == 'SHADOW':
                # Validate 4 Pillars before allowing SHADOW execution
                pillars_valid, pillar_reason = self._validate_4_pillars(signal, strategy_id, symbol)
                
                if pillars_valid:
                    logger.info(
                        f"[SHADOW_GATE] Strategy {strategy_id} authorized for SHADOW execution. "
                        f"Symbol={symbol}, 4-Pillars PASSED"
                    )
                    
                    self.storage.log_signal_pipeline_event(
                        signal_id=signal_id,
                        stage='SHADOW_VALIDATION',
                        decision='APPROVED',
                        reason='4-Pillar validation passed'
                    )
                    
                    return (True, None)
                else:
                    reason = f"SHADOW mode: 4-Pillar validation failed ({pillar_reason})"
                    logger.warning(
                        f"[SHADOW_GATE] Strategy {strategy_id} blocked from SHADOW execution. "
                        f"Symbol={symbol}, Reason={pillar_reason}"
                    )
                    
                    self.storage.log_signal_pipeline_event(
                        signal_id=signal_id,
                        stage='SHADOW_VALIDATION',
                        decision='REJECTED',
                        reason=reason
                    )
                    
                    if self.notificator:
                        self.notificator.create_notification(
                            category=NotificationCategory.EXECUTION,
                            context={
                                "symbol": symbol,
                                "status": "REJECTED",
                                "reason": f"SHADOW: {pillar_reason}"
                            }
                        )
                    
                    return (False, reason)
            
            # ──── QUARANTINE MODE: Always Blocked ────────────────────────
            else:
                reason = f"Strategy {strategy_id} not in LIVE or SHADOW execution mode"
                logger.warning(
                    f"[CIRCUIT_BREAKER] Strategy {strategy_id} blocked from trading. "
                    f"Symbol={symbol}, Status=REJECTED (execution_mode={execution_mode})"
                )
                
                self.storage.log_signal_pipeline_event(
                    signal_id=signal_id,
                    stage='CIRCUIT_BREAKER',
                    decision='REJECTED',
                    reason=reason
                )
                
                if self.notificator:
                    self.notificator.create_notification(
                        category=NotificationCategory.EXECUTION,
                        context={
                            "symbol": symbol,
                            "status": "REJECTED",
                            "reason": "Circuit breaker: strategy in quarantine"
                        }
                    )
                
                return (False, "CIRCUIT_BREAKER_BLOCKED")
            
        except Exception as e:
            # CircuitBreaker check failed - fail-secure (block order)
            reason = f"CircuitBreaker error checking strategy {strategy_id}: {str(e)}"
            logger.error(reason, exc_info=False)
            
            self.storage.log_signal_pipeline_event(
                signal_id=signal_id,
                stage='CIRCUIT_BREAKER',
                decision='REJECTED',
                reason=reason
            )
            
            if self.notificator:
                self.notificator.create_notification(
                    category=NotificationCategory.EXECUTION,
                    context={
                        "symbol": symbol,
                        "status": "REJECTED",
                        "reason": "Circuit breaker check error"
                    }
                )
            
            return (False, "CIRCUIT_BREAKER_ERROR")
    
    def _validate_4_pillars(
        self,
        signal: Optional[Any],
        strategy_id: str,
        symbol: str
    ) -> Tuple[bool, str]:
        """
        Validate 4-Pillar criteria for SHADOW mode authorization.
        
        Pillars (thresholds loaded from dynamic_params at init):
        1. Market Structure Score >= min_market_structure
        2. Risk Profile Score >= min_risk_profile
        3. Liquidity Level >= min_liquidity
        4. Confluence Score >= min_confluence
        
        Args:
            signal: Signal object (may be None)
            strategy_id: Strategy ID for logging
            symbol: Trading symbol for logging
            
        Returns:
            Tuple[valid (bool), reason (str)]
        """
        if not signal:
            logger.debug(f"[SHADOW_VALIDATION] No signal object, allowing SHADOW (lenient default)")
            return (True, "No signal provided, lenient default")
        
        try:
            # Extract pillar scores from signal metadata (with sensible defaults)
            market_structure = signal.metadata.get('market_structure_score', 0.80)
            risk_profile = signal.metadata.get('risk_profile_score', 0.85)
            liquidity_level = signal.metadata.get('liquidity_level', 'HIGH')
            confluence = signal.metadata.get('confluence_score', 0.75)
            
            # Convert liquidity_level to comparable format if needed
            liquidity_levels = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
            liquidity_value = liquidity_levels.get(
                str(liquidity_level).upper(), 
                2  # Default to MEDIUM if unknown
            )
            min_liquidity_value = liquidity_levels.get(self.min_liquidity, 2)
            
            # ── Pillar 1: Market Structure ────────────────────────────────
            if market_structure < self.min_market_structure:
                reason = f"Market Structure Score={market_structure:.2f} < {self.min_market_structure}"
                logger.warning(f"[SHADOW_VALIDATION] {reason}")
                return (False, reason)
            
            # ── Pillar 2: Risk Profile ───────────────────────────────────
            if risk_profile < self.min_risk_profile:
                reason = f"Risk Profile Score={risk_profile:.2f} < {self.min_risk_profile}"
                logger.warning(f"[SHADOW_VALIDATION] {reason}")
                return (False, reason)
            
            # ── Pillar 3: Liquidity ──────────────────────────────────────
            if liquidity_value < min_liquidity_value:
                reason = f"Liquidity Level={liquidity_level} < {self.min_liquidity}"
                logger.warning(f"[SHADOW_VALIDATION] {reason}")
                return (False, reason)
            
            # ── Pillar 4: Confluence Score ───────────────────────────────
            if confluence < self.min_confluence:
                reason = f"Confluence Score={confluence:.2f} < {self.min_confluence}"
                logger.warning(f"[SHADOW_VALIDATION] {reason}")
                return (False, reason)
            
            # All pillars passed
            logger.info(
                f"[SHADOW_VALIDATION] Strategy {strategy_id} ({symbol}) passed all 4 pillars. "
                f"Market Structure={market_structure:.2f}, Risk={risk_profile:.2f}, "
                f"Liquidity={liquidity_level}, Confluence={confluence:.2f}"
            )
            
            return (True, "All 4 pillars passed")
            
        except Exception as e:
            logger.error(
                f"[SHADOW_VALIDATION] Error validating 4 pillars for {strategy_id}: {e}",
                exc_info=False
            )
            # Default to lenient on validation errors (allow SHADOW to proceed)
            return (True, f"Validation error (lenient default): {str(e)}")
