"""
Coherence Monitor
Tracks end-to-end consistency: Scanner -> Signal -> Strategy -> Execution -> Ticket.
DB-first and connector-agnostic.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from data_vault.storage import StorageManager
from models.signal import ConnectorType

logger = logging.getLogger(__name__)


@dataclass
class CoherenceEvent:
    signal_id: Optional[str]
    symbol: str
    stage: str
    status: str
    reason: str
    connector_type: Optional[str]
    timestamp: str


class CoherenceMonitor:
    """
    Detects inconsistencies between signals and execution.

    Rules implemented:
    - EXECUTED without ticket/order_id (MT5)
    - Unnormalized symbol for MT5 (e.g., USDJPY=X)
    - PENDING older than threshold
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        pending_timeout_minutes: int = 15,
        lookback_minutes: int = 120
    ):
        self.storage = storage or StorageManager()
        self.pending_timeout_minutes = pending_timeout_minutes
        self.lookback_minutes = lookback_minutes

    def run_once(self) -> List[CoherenceEvent]:
        events: List[CoherenceEvent] = []
        recent_signals = self.storage.get_recent_signals(minutes=self.lookback_minutes)

        now = datetime.now()
        for sig in recent_signals:
            signal_id = sig.get("id")
            symbol = sig.get("symbol") or "UNKNOWN"
            status = (sig.get("status") or "").upper()
            connector = (sig.get("connector_type") or "").upper()
            order_id = sig.get("order_id")
            timestamp = sig.get("timestamp")

            # Parse timestamp
            ts = None
            try:
                ts = datetime.fromisoformat(timestamp) if timestamp else None
            except Exception:
                ts = None

            # Rule 1: EXECUTED without ticket for MT5
            if connector == ConnectorType.METATRADER5.value and status == "EXECUTED":
                if not order_id:
                    events.append(self._emit(
                        signal_id=signal_id,
                        symbol=symbol,
                        stage="EXECUTION",
                        status="INCONSISTENT",
                        reason="EXECUTED_WITHOUT_TICKET",
                        connector_type=connector
                    ))

            # Rule 2: Unnormalized symbol for MT5
            if connector == ConnectorType.METATRADER5.value and "=X" in symbol:
                events.append(self._emit(
                    signal_id=signal_id,
                    symbol=symbol,
                    stage="EXECUTION",
                    status="INCONSISTENT",
                    reason="UNNORMALIZED_SYMBOL",
                    connector_type=connector
                ))

            # Rule 3: PENDING too long
            if status == "PENDING" and ts:
                age_minutes = (now - ts).total_seconds() / 60.0
                if age_minutes >= self.pending_timeout_minutes:
                    events.append(self._emit(
                        signal_id=signal_id,
                        symbol=symbol,
                        stage="EXECUTION",
                        status="INCONSISTENT",
                        reason="PENDING_TIMEOUT",
                        connector_type=connector
                    ))

        return events

    def _emit(
        self,
        signal_id: Optional[str],
        symbol: str,
        stage: str,
        status: str,
        reason: str,
        connector_type: Optional[str]
    ) -> CoherenceEvent:
        event = CoherenceEvent(
            signal_id=signal_id,
            symbol=symbol,
            stage=stage,
            status=status,
            reason=reason,
            connector_type=connector_type,
            timestamp=datetime.now().isoformat()
        )
        try:
            self.storage.log_coherence_event(
                signal_id=signal_id,
                symbol=symbol,
                stage=stage,
                status=status,
                reason=reason,
                connector_type=connector_type
            )
        except Exception as e:
            logger.error(f"Error logging coherence event: {e}")
        return event
