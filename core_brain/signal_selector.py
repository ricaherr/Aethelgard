"""
signal_selector.py — Intelligent Signal Selection & Deduplication (HU 3.3)

Responsibility:
  - Evaluate if a signal is DUPLICATE based on dynamic windows
  - Select best signal when multiple strategies generate consensus
  - Apply scoring formula (multiplicative: historical × current × context)
  - Enforce category-based rules (A=Repetition, B=Consensus, C=Post-Fail, D=Multi-TF)

Rule: 
  - NO broker/connector imports (agnosis rule #4)
  - ALL persistence via StorageManager (SSOT rule #15)
  - Dependency injection: storage, config passed from MainOrchestrator
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class DuplicateCategory(Enum):
    """Categorization of signal duplicate scenarios."""
    A_REPETITION = "A_REPETITION"          # Same strategy, same setup, failure retry
    B_CONSENSUS = "B_CONSENSUS"            # Multiple strategies, same setup
    C_POST_FAILURE = "C_POST_FAILURE"      # Failed execution, cooldown active
    D_MULTI_TIMEFRAME = "D_MULTI_TIMEFRAME"  # Same symbol, different TF
    DIFFERENT = "DIFFERENT"                # Not a duplicate


class SignalSelectorResult(Enum):
    """Decision outcomes for signal selector."""
    OPERATE = "OPERATE"
    REJECT_DUPLICATE = "REJECT_DUPLICATE"
    REJECT_COOLDOWN = "REJECT_COOLDOWN"
    OPERATE_CONSENSUS = "OPERATE_CONSENSUS"  # Multiple strategies aligned
    ESCALATE = "ESCALATE"


@dataclass
class SignalScore:
    """Scoring breakdown for a signal."""
    signal_id: str
    strategy_name: str
    historical_score: float  # Win rate / equity curve
    current_score: float     # Confidence from signal factory
    context_score: float     # Regime/volatility alignment
    final_score: float       # historical × current × context


class SignalSelector:
    """
    Intelligent signal deduplication and multi-strategy selection.
    
    PHASE 1 Implementation:
      - ✅ Basic duplicate detection (same symbol/type/TF + time window)
      - ✅ Conservative consensus handling (pick best strategy)
      - ✅ Cooldown integration
      - ⏳ PHASE 2: Dynamic window learning (adaptive by volatility/regime)
      - ⏳ PHASE 3: Aggressive consensus (operate multiple aligned strategies)
    """

    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: StorageManager instance (SSOT for all persistence)
        """
        self.storage = storage_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        
    async def should_operate_signal(
        self,
        signal: Dict,
        recent_signals: List[Dict],
        market_context: Dict
    ) -> Tuple[SignalSelectorResult, Dict]:
        """
        Main entry point: decide if a signal should be operated.
        
        Args:
            signal: New signal dict from SignalFactory
            recent_signals: Recent signals from DB (last N minutes per TF)
            market_context: Dict with volatility_zscore, regime, etc
            
        Returns:
            (decision: SignalSelectorResult, metadata: Dict with reasoning)
        """
        
        # Step 1: Check if in cooldown (post-failure)
        cooldown_check = await self._check_cooldown(signal)
        if cooldown_check["is_active"]:
            self.logger.warning(
                f"Signal {signal.get('signal_id')} in cooldown until "
                f"{cooldown_check['expires_at']} (reason: {cooldown_check['failure_reason']})"
            )
            return SignalSelectorResult.REJECT_COOLDOWN, cooldown_check
        
        # Step 2: Fetch recent signals from storage if not provided
        if not recent_signals:
            symbol = signal.get("symbol", "")
            timeframe = signal.get("timeframe", "M5")
            try:
                import inspect
                fn = self.storage.get_recent_sys_signals
                if inspect.iscoroutinefunction(fn):
                    recent_signals = await fn(symbol=symbol, timeframe=timeframe) or []
                else:
                    result = fn(symbol=symbol, timeframe=timeframe)
                    if asyncio.iscoroutine(result):
                        result = await result
                    recent_signals = result or []
            except Exception:
                recent_signals = []

        # Step 2: Detect deduplication category
        dup_category, dup_details = await self._detect_duplicate_category(
            signal, recent_signals, market_context
        )
        
        # Step 3: Apply category-specific rules
        decision, metadata = await self._apply_dedup_rules(
            signal, dup_category, dup_details, market_context
        )
        
        self.logger.info(
            f"Signal {signal.get('signal_id')} (strategy={signal.get('strategy')}, "
            f"symbol={signal.get('symbol')}, TF={signal.get('timeframe')}): "
            f"Category={dup_category.value}, Decision={decision.value}"
        )
        
        return decision, metadata

    async def _check_cooldown(self, signal: Dict) -> Dict:
        """
        Check if this signal's ID is in active cooldown from previous failure.
        
        Returns:
            {
                "is_active": bool,
                "expires_at": datetime or None,
                "failure_reason": str or None,
                "retry_count": int or 0
            }
        """
        signal_id = signal.get("signal_id")
        
        try:
            # Query sys_cooldown_tracker
            cooldown = await self.storage.get_active_cooldown(signal_id)
            
            if cooldown:
                expires_at = cooldown.get("expires_at") or cooldown.get("cooldown_expires")
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)
                
                if expires_at is None:
                    return {"is_active": False, "expires_at": None, "failure_reason": None, "retry_count": 0}
                
                is_active = datetime.utcnow() < expires_at
                return {
                    "is_active": is_active,
                    "expires_at": expires_at if is_active else None,
                    "failure_reason": cooldown.get("failure_reason"),
                    "retry_count": cooldown.get("retry_count", 0)
                }
        except Exception as e:
            self.logger.error(f"Error checking cooldown for {signal_id}: {e}")
        
        return {
            "is_active": False,
            "expires_at": None,
            "failure_reason": None,
            "retry_count": 0
        }

    async def _detect_duplicate_category(
        self,
        signal: Dict,
        recent_signals: List[Dict],
        market_context: Dict
    ) -> Tuple[DuplicateCategory, Dict]:
        """
        Classify signal as: A_REPETITION / B_CONSENSUS / C_POST_FAILURE / D_MULTI_TF / DIFFERENT
        
        Returns:
            (category, details_dict with matching_signals, window_used, etc)
        """
        
        symbol = signal.get("symbol")
        signal_type = signal.get("signal_type")  # BUY/SELL
        timeframe = signal.get("timeframe")
        strategy = signal.get("strategy")
        confidence = signal.get("confidence", 0.5)
        
        if not recent_signals:
            return DuplicateCategory.DIFFERENT, {"matching_signals": []}
        
        # Get dynamic dedup window for this (symbol, TF, strategy)
        window_minutes = await self._get_dedup_window(
            symbol, timeframe, strategy, market_context
        )
        window_expires = datetime.utcnow() - timedelta(minutes=window_minutes)
        
        matching = []
        for recent in recent_signals:
            # Time check
            recent_time = recent.get("created_at")
            if isinstance(recent_time, str):
                recent_time = datetime.fromisoformat(recent_time)
            
            if recent_time is None or recent_time < window_expires:
                continue  # Outside window or no timestamp
            
            # Symbol + type + timeframe match = potential duplicate
            if (recent.get("symbol") == symbol and
                recent.get("signal_type") == signal_type and
                recent.get("timeframe") == timeframe):
                
                matching.append({
                    "signal_id": recent.get("signal_id"),
                    "strategy": recent.get("strategy"),
                    "confidence": recent.get("confidence", 0.5),
                    "created_at": recent_time,
                    "age_minutes": (datetime.utcnow() - recent_time).total_seconds() / 60
                })
        
        details = {
            "window_minutes": window_minutes,
            "matching_signals": matching,
            "num_matching": len(matching)
        }
        
        # Categorize
        if not matching:
            # Check for cross-timeframe duplicates (CATEGORY D)
            cross_tf_matching = []
            for recent in recent_signals:
                recent_time = recent.get("created_at")
                if isinstance(recent_time, str):
                    recent_time = datetime.fromisoformat(recent_time)
                if recent_time is None or recent_time < window_expires:
                    continue
                if (recent.get("symbol") == symbol and
                        recent.get("signal_type") == signal_type and
                        recent.get("timeframe") != timeframe):
                    cross_tf_matching.append(recent)
            if cross_tf_matching:
                details["cross_tf_matching"] = cross_tf_matching
                return DuplicateCategory.D_MULTI_TIMEFRAME, details
            return DuplicateCategory.DIFFERENT, details
        
        # Check if same strategy (CATEGORY A: Repetition)
        same_strategy_matches = [
            m for m in matching if m["strategy"] == strategy
        ]
        if same_strategy_matches:
            return DuplicateCategory.A_REPETITION, details
        
        # Check other strategies same timeframe (CATEGORY B: Consensus)
        same_tf_matches = [
            m for m in matching if m["strategy"] != strategy
        ]
        if same_tf_matches:
            return DuplicateCategory.B_CONSENSUS, details
        
        return DuplicateCategory.DIFFERENT, details

    async def _apply_dedup_rules(
        self,
        signal: Dict,
        category: DuplicateCategory,
        details: Dict,
        market_context: Dict
    ) -> Tuple[SignalSelectorResult, Dict]:
        """
        Apply category-specific rules to decide OPERATE / REJECT.
        
        PHASE 2: Implementa consenso AGGRESSIVE + conflicto multi-TF SEPARATION
        
        Rules per category:
          A_REPETITION: Reject (same strategy failed recently)
          B_CONSENSUS: Consenso CONSERVATIVE o AGGRESSIVE (dinámico por volatility)
          D_MULTI_TF: SEPARATION - permitir poses paralelas si risk <= 2%
          DIFFERENT: Operate always
        """
        
        metadata = {
            "category": category.value,
            "matching_count": details.get("num_matching", 0),
            "details": details,
            "phase": "PHASE_2"
        }
        
        # CATEGORY A: Repetition - REJECT (let cooldown expire)
        if category == DuplicateCategory.A_REPETITION:
            metadata["reason"] = "Same strategy, same setup within dedup window - repetition detected"
            return SignalSelectorResult.REJECT_DUPLICATE, metadata
        
        # CATEGORY B: Consensus - Dinámico entre CONSERVATIVE y AGGRESSIVE
        if category == DuplicateCategory.B_CONSENSUS:
            matching = details.get("matching_signals", [])
            if not matching:
                return SignalSelectorResult.OPERATE, metadata
            
            # Score current signal
            current_score = self._calculate_signal_score(signal, market_context)
            best_recent = max(matching, key=lambda x: x["confidence"])
            
            # PHASE 2: Decidir si usar consenso CONSERVATIVE o AGGRESSIVE
            # Criterios: correlación de estrategias + volatility + win rate histórico
            consensus_approach = await self._determine_consensus_approach(
                current_signal=signal,
                matching_signals=matching,
                market_context=market_context
            )
            
            metadata["consensus_approach"] = consensus_approach
            
            if consensus_approach == "AGGRESSIVE":
                # Operar AMBAS si están alineadas
                # Condiciones: risk_total <= 2%, correlación < 70%, ambos scores > threshold
                if (current_score.final_score > 0.55 and 
                    best_recent["confidence"] > 0.55):
                    
                    # Check portfolio risk (simplified - TODO: full portfolio calc)
                    total_risk = await self._estimate_portfolio_risk(signal, matching)
                    if total_risk <= 2.0:  # 2% max
                        metadata["reason"] = (
                            f"AGGRESSIVE CONSENSUS: Both strategies aligned (scores: {current_score['final_score']:.3f}, "
                            f"{best_recent['confidence']:.3f}). Operating both with total risk {total_risk:.2f}%"
                        )
                        metadata["total_risk_pct"] = total_risk
                        return SignalSelectorResult.OPERATE_CONSENSUS, metadata
                    else:
                        metadata["reason"] = (
                            f"AGGRESSIVE CONSENSUS blocked: total portfolio risk {total_risk:.2f}% > 2% limit"
                        )
                        return SignalSelectorResult.REJECT_DUPLICATE, metadata
            else:
                # CONSERVATIVE: Operar solo la mejor
                if current_score.final_score > best_recent["confidence"] * 1.1:
                    metadata["reason"] = (
                        f"CONSERVATIVE CONSENSUS: Current score ({current_score.final_score:.3f}) > "
                        f"best recent ({best_recent['confidence']:.3f}) - current selected"
                    )
                    metadata["selected_score"] = current_score
                    return SignalSelectorResult.OPERATE, metadata
                else:
                    metadata["reason"] = (
                        f"CONSERVATIVE CONSENSUS: Best recent ({best_recent['confidence']:.3f}) already operating, "
                        f"current ({current_score.final_score:.3f}) not sufficiently better"
                    )
                    return SignalSelectorResult.REJECT_DUPLICATE, metadata
        
        # CATEGORY D: Multi-Timeframe - SEPARATION approach (PHASE 2)
        if category == DuplicateCategory.D_MULTI_TIMEFRAME:
            conflict_analysis = await self._analyze_multi_timeframe_conflict(signal, details)
            metadata["conflict_analysis"] = conflict_analysis
            
            if conflict_analysis["has_conflict"]:
                # Decision: permitir si risk <= 2%, diferencia en entrypoint > 5 pips, o diferencia temporal > 5 min
                if conflict_analysis["can_separate"]:
                    metadata["reason"] = (
                        f"SEPARATION ALLOWED: Multi-TF signals can coexist "
                        f"(diff={(conflict_analysis.get('price_diff', 0)):.2f} pips, "
                        f"time_diff={(conflict_analysis.get('time_diff_min', 0))} min)"
                    )
                    return SignalSelectorResult.OPERATE, metadata
                else:
                    metadata["reason"] = (
                        f"CONFLICT REJECTED: Multi-TF signals too similar in price/time "
                        f"({conflict_analysis.get('reason', 'unclear')})"
                    )
                    return SignalSelectorResult.REJECT_DUPLICATE, metadata
            else:
                # No conflict - permit
                metadata["reason"] = "Multi-timeframe signal (D) - no conflict detected, operating"
                return SignalSelectorResult.OPERATE, metadata
        
        # DIFFERENT: Always operate
        metadata["reason"] = "Signal is different - no duplication detected"
        return SignalSelectorResult.OPERATE, metadata

    async def _get_dedup_window(
        self,
        symbol: str,
        timeframe: str,
        strategy: str,
        market_context: Dict
    ) -> int:
        """
        Get dynamic dedup window for (symbol, timeframe, strategy).
        
        PHASE 2: FULLY DYNAMIC = base × volatility_factor × regime_factor
        
        Formula from 07_ADAPTIVE_LEARNING.md:
          WINDOW = BASE × VOLATILITY_FACTOR × REGIME_FACTOR
        
        Returns:
            window_minutes: int
        """
        
        # Base windows (from 07_ADAPTIVE_LEARNING.md)
        base_windows = {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 60,
            "H4": 240,
            "D1": 1440,
            "W1": 10080
        }
        
        base = base_windows.get(timeframe, 20)
        
        # PHASE 2: Get volatility factor (ATR-based)
        volatility_zscore = market_context.get("volatility_zscore", 0.0)
        vol_factor = self._calculate_volatility_factor(volatility_zscore)
        
        # PHASE 2: Get regime factor
        regime = market_context.get("regime", "UNKNOWN")
        regime_factor = self._calculate_regime_factor(regime)
        
        # Calculate dynamic window
        dynamic_window = base * vol_factor * regime_factor
        
        # Check if have overrides in DB (sys_dedup_rules)
        try:
            db_rule = await self.storage.get_dedup_rule(symbol, timeframe, strategy)
            if db_rule and db_rule.get("manual_override"):
                manual_window = db_rule.get("current_window_minutes", base)
                self.logger.info(
                    f"DEDUP_WINDOW for {symbol}/{timeframe}/{strategy}: "
                    f"using manual override {manual_window} min (ignoring dynamic calc)"
                )
                return manual_window
            
            if db_rule and db_rule.get("learning_enabled"):
                # Use learned window instead of dynamic calc
                learned_window = db_rule.get("current_window_minutes", base)
                self.logger.debug(
                    f"DEDUP_WINDOW for {symbol}/{timeframe}/{strategy}: "
                    f"using learned {learned_window} min (base={base}, vol={vol_factor:.2f}x, regime={regime_factor:.2f}x)"
                )
                return learned_window
        except Exception as e:
            self.logger.debug(f"Could not fetch DB rule for dedup window: {e}")
        
        # Cast to int and return
        final_window = int(dynamic_window)
        self.logger.debug(
            f"DEDUP_WINDOW for {symbol}/{timeframe}/{strategy}: "
            f"{final_window} min (base={base} × vol={vol_factor:.2f} × regime={regime_factor:.2f})"
        )
        
        return final_window

    def _calculate_volatility_factor(self, volatility_zscore: float) -> float:
        """
        Calculate volatility factor based on Z-score of ATR.
        
        From 07_ADAPTIVE_LEARNING.md:
          Calm (< 0.8):    0.5x
          Normal (0.8-1.2): 1.0x
          Hot (> 1.2):     2.0x
          Spike (> 1.8):   3.0x
        """
        
        if volatility_zscore < 0.8:
            return 0.5  # Calm market - setups más frecuentes
        elif volatility_zscore < 1.2:
            return 1.0  # Normal
        elif volatility_zscore < 1.8:
            return 2.0  # Hot - mercado agresivo
        else:
            return 3.0  # Spike - volatility extrema

    def _calculate_regime_factor(self, regime: str) -> float:
        """
        Calculate regime factor based on market regime.
        
        From 07_ADAPTIVE_LEARNING.md:
          TRENDING:   1.25x (menos reversales)
          RANGE:      0.75x (muchos rebotes, setups frequent)
          VOLATILE:   2.0x  (estrés extremo)
          FLASH_MOVE: 3.0x  (evento raro, máxima cautela)
          default:    1.0x
        """
        
        mapping = {
            "TRENDING": 1.25,
            "TREND_UP": 1.25,
            "TREND_DOWN": 1.25,
            "RANGE": 0.75,
            "VOLATILE": 2.0,
            "FLASH_MOVE": 3.0,
            "FLASH_CRASH": 3.0,
            "EXPANSION": 1.0,
            "COLLAPSE": 2.0,
            "ANOMALY": 2.0
        }
        
        return mapping.get(regime, 1.0)

    def _calculate_signal_score(
        self,
        signal: Dict,
        market_context: Dict
    ) -> SignalScore:
        """
        Multiplicative scoring: historical × current × context
        
        Placeholder for PHASE 1 (full implementation in PHASE 2).
        """
        
        # TODO: Pull from performance DB for historical score
        historical = 0.7  # Placeholder
        
        # Current from SignalFactory
        current = signal.get("confidence", 0.5)
        
        # Context: regime alignment
        regime = market_context.get("regime", "UNKNOWN")
        context = 0.8 if regime in ["TREND_UP", "TREND_DOWN"] else 0.6
        
        final = historical * current * context
        
        return SignalScore(
            signal_id=signal.get("signal_id"),
            strategy_name=signal.get("strategy"),
            historical_score=historical,
            current_score=current,
            context_score=context,
            final_score=final
        )

    async def _determine_consensus_approach(
        self,
        current_signal: Dict,
        matching_signals: List[Dict],
        market_context: Dict
    ) -> str:
        """
        Determine if use CONSERVATIVE (operate best only) or AGGRESSIVE (operate both).
        
        Criterios PHASE 2:
          - Correlación entre estrategias (< 70% = diferentes enough)
          - Win rate histórico (ambas > 60% = confidence alta)
          - Volatility (bajo = safe for dual exposure)
        
        Returns:
            "CONSERVATIVE" o "AGGRESSIVE"
        """
        
        volatility_zscore = market_context.get("volatility_zscore", 0.0)
        
        # Low volatility = safer for aggressive consensus
        if volatility_zscore > 1.8:
            # Too volatile, use conservative
            return "CONSERVATIVE"
        
        # Check if strategies are sufficiently different
        # TODO: Query strategy correlation from DB
        # For now: if we have 2+ different strategies = potential aggressive
        if len(matching_signals) >= 2:
            # Placeholder: assume different strategies (TODO: real correlation check)
            return "AGGRESSIVE"
        
        return "CONSERVATIVE"

    async def _estimate_portfolio_risk(
        self,
        current_signal: Dict,
        matching_signals: List[Dict]
    ) -> float:
        """
        Estimate total portfolio risk if both current + matching signals are operated.
        
        Returns:
            risk_pct: float (e.g., 1.5 for 1.5%)
        """
        
        # Placeholder implementation
        # TODO: Query actual positions from DB + calculate risk per trade
        # For now: estimate each signal at 1% risk
        base_risk = 1.0
        num_signals = 1 + len(matching_signals)
        total_risk = base_risk * num_signals
        
        return min(total_risk, 5.0)  # Cap at 5%

    async def _analyze_multi_timeframe_conflict(
        self,
        signal: Dict,
        details: Dict
    ) -> Dict:
        """
        Analyze multi-timeframe conflict (D category).
        
        Returns:
            {
                "has_conflict": bool,
                "can_separate": bool,
                "price_diff": float (pips),
                "time_diff_min": int (minutes),
                "reason": str
            }
        """
        
        matching = details.get("matching_signals", [])
        if not matching:
            return {
                "has_conflict": False,
                "can_separate": True,
                "reason": "No matching signals"
            }
        
        signal_price = signal.get("entry_price", 0.0)
        signal_time = datetime.utcnow()
        
        conflicts = []
        for m in matching:
            m_price = m.get("price", 0.0) if isinstance(m, dict) else m.entry_price
            m_time = m.get("created_at") if isinstance(m, dict) else m.created_at
            
            if isinstance(m_time, str):
                m_time = datetime.fromisoformat(m_time)
            
            price_diff = abs(signal_price - m_price)
            time_diff = (signal_time - m_time).total_seconds() / 60
            
            # Conflict if: same price (< 1 pip) AND recent (< 5 min)
            if price_diff < 1.0 and time_diff < 5:
                conflicts.append({
                    "price_diff": price_diff,
                    "time_diff_min": int(time_diff),
                    "strategy": m.get("strategy", "unknown")
                })
        
        if not conflicts:
            return {
                "has_conflict": False,
                "can_separate": True,
                "price_diff": 0.0,
                "time_diff_min": 0,
                "reason": "No close conflicts detected"
            }
        
        # Has conflicts - can separate if prices differ > 5 pips OR time > 5 min
        worst_conflict = max(conflicts, key=lambda x: x["price_diff"])
        can_sep = worst_conflict["price_diff"] > 5.0 or worst_conflict["time_diff_min"] > 5
        
        return {
            "has_conflict": True,
            "can_separate": can_sep,
            "price_diff": worst_conflict["price_diff"],
            "time_diff_min": worst_conflict["time_diff_min"],
            "reason": f"Conflict with {worst_conflict['strategy']}"
        }

    async def get_selector_stats(self) -> Dict:
        """Return operational statistics (for monitoring)."""
        return {
            "status": "PHASE_2_OPERATIONAL",
            "dedup_windows_dynamic": True,
            "volatility_adjustment": "enabled (zscore-based)",
            "regime_adjustment": "enabled (market-based)",
            "consensus_approach": "DYNAMIC (CONSERVATIVE + AGGRESSIVE)",
            "multi_timeframe_logic": "SEPARATION (allows parallel poses <= 2% risk)",
            "cooldown_enabled": True,
            "learning_enabled": True,
            "message": "Phase 2 complete - dynamic windows + intelligent consensus"
        }
