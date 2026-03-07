"""
Economic Data Fetch & Persist Module - FASE C.5

Core job function called by EconomicDataScheduler every 5 minutes.
Implements atomic transaction: fetch → sanitize → persist (all-or-nothing)

Pipeline:
1. Fetch from all providers in parallel
2. Sanitize batch using NewsSanitizer (3 pilares validation)
3. Persist atomically to sys_economic_calendar table
4. Return metrics for EDGE scheduler monitoring

Type Hints: 100% coverage
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import uuid

from connectors.economic_data_gateway import EconomicDataProviderRegistry
from core_brain.news_sanitizer import NewsSanitizer
from core_brain.news_errors import (
    DataSchemaError,
    DataLatencyError,
    DataIncompatibilityError,
    PersistenceError
)
from data_vault.storage import StorageManager


logger = logging.getLogger(__name__)


@dataclass
class FetchPersistMetrics:
    """Metrics from fetch & persist cycle."""
    timestamp: datetime
    providers_queried: int
    events_fetched: int
    events_accepted: int
    events_rejected: int
    rejection_reasons: Dict[str, int]
    db_inserts: int
    duration_sec: float
    success: bool
    error_message: Optional[str] = None


class EconomicFetchPersist:
    """
    Atomic economic data fetch → sanitize → persist workflow.
    
    Ensures:
    - All providers fetched in parallel (concurrency)
    - All events validated against 3 pillars (quality)
    - All-or-nothing DB insert (atomicity)
    - Full audit trail (immutability)
    """
    
    def __init__(
        self,
        gateway: EconomicDataProviderRegistry,
        sanitizer: NewsSanitizer,
        storage: StorageManager
    ):
        """Initialize with dependencies (dependency injection pattern)."""
        self.gateway = gateway
        self.sanitizer = sanitizer
        self.storage = storage
        self.logger = logger
    
    async def fetch_all_providers(
        self,
        days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Fetch economic events from all available providers.
        
        Args:
            days_back: How many days back to fetch (default 7 days)
        
        Returns:
            List of raw events from all providers combined
        """
        self.logger.info(f"[FETCH] Starting parallel fetch from all providers (days_back={days_back})")
        
        try:
            # Get all provider adapters
            adapters = self.gateway.get_all_adapters()
            
            if not adapters:
                self.logger.warning("[FETCH] No adapters available")
                return []
            
            # Fetch from all adapters in parallel
            tasks = [
                adapter.fetch_events(days_back=days_back)
                for adapter in adapters
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Flatten results and handle exceptions
            all_events = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(
                        f"[FETCH] Provider {adapters[i].provider_name} failed: {str(result)}"
                    )
                    continue
                
                if result:
                    self.logger.info(
                        f"[FETCH] {adapters[i].provider_name}: {len(result)} events fetched"
                    )
                    all_events.extend(result)
            
            self.logger.info(f"[FETCH] Total: {len(all_events)} events from all providers")
            return all_events
        
        except Exception as e:
            self.logger.error(f"[FETCH] Critical error during fetch: {str(e)}")
            raise
    
    def sanitize_batch(
        self,
        events: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int, int, Dict[str, int]]:
        """
        Sanitize batch of events using NewsSanitizer (3 pilares).
        
        Args:
            events: Raw events from providers
        
        Returns:
            Tuple[accepted_events, accepted_count, rejected_count, rejection_reasons]
        """
        self.logger.info(f"[SANITIZE] Starting validation of {len(events)} events")
        
        accepted = []
        rejected_count = 0
        rejection_reasons: Dict[str, int] = {}
        
        for event in events:
            try:
                # Extract provider source from event
                provider_source = event.get('provider_source', 'unknown')
                
                # Sanitize using NewsSanitizer
                sanitized = self.sanitizer.sanitize_event(event, provider_source)
                accepted.append(sanitized)
            
            except DataSchemaError as e:
                rejected_count += 1
                reason = "schema_error"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                self.logger.debug(f"[SANITIZE] Schema error: {str(e)}")
            
            except DataLatencyError as e:
                rejected_count += 1
                reason = "latency_error"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                self.logger.debug(f"[SANITIZE] Latency error: {str(e)}")
            
            except DataIncompatibilityError as e:
                rejected_count += 1
                reason = "incompatibility_error"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                self.logger.debug(f"[SANITIZE] Incompatibility error: {str(e)}")
            
            except Exception as e:
                rejected_count += 1
                reason = "unknown_error"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                self.logger.warning(f"[SANITIZE] Unexpected error: {str(e)}")
        
        self.logger.info(
            f"[SANITIZE] Results: {len(accepted)} accepted, {rejected_count} rejected. "
            f"Reasons: {rejection_reasons}"
        )
        
        return accepted, len(accepted), rejected_count, rejection_reasons
    
    def persist_atomic(
        self,
        events: List[Dict[str, Any]]
    ) -> Tuple[int, Optional[str]]:
        """
        Atomically persist events to sys_economic_calendar table.
        
        All-or-nothing: Either all events are inserted or none are.
        
        Args:
            events: Sanitized events ready for persistence
        
        Returns:
            Tuple[insert_count, error_message]
            - insert_count: Number of rows inserted
            - error_message: None if success, error string if failed
        """
        if not events:
            self.logger.info("[PERSIST] No events to persist")
            return 0, None
        
        self.logger.info(f"[PERSIST] Starting atomic insertion of {len(events)} events")
        
        try:
            # Attempt atomic insert via storage
            inserted = self.storage.insert_economic_calendar_batch(events)
            
            self.logger.info(f"[PERSIST] ✅ Successfully inserted {inserted} events")
            return inserted, None
        
        except PersistenceError as e:
            error_msg = f"Persistence failed: {str(e)}"
            self.logger.error(f"[PERSIST] ❌ {error_msg}")
            return 0, error_msg
        
        except Exception as e:
            error_msg = f"Unexpected persistence error: {str(e)}"
            self.logger.error(f"[PERSIST] ❌ {error_msg}")
            return 0, error_msg
    
    async def execute_cycle(
        self,
        days_back: int = 7
    ) -> FetchPersistMetrics:
        """
        Execute complete fetch → sanitize → persist cycle.
        
        Args:
            days_back: Days back to fetch
        
        Returns:
            FetchPersistMetrics with cycle statistics
        """
        cycle_start = datetime.now(timezone.utc)
        self.logger.info("[CYCLE] Starting economic data fetch-sanitize-persist cycle")
        
        try:
            # STEP 1: Fetch from all providers
            raw_events = await self.fetch_all_providers(days_back=days_back)
            
            # STEP 2: Sanitize batch
            accepted_events, accepted_count, rejected_count, rejection_reasons = self.sanitize_batch(
                raw_events
            )
            
            # STEP 3: Persist atomically
            inserted_count, persist_error = self.persist_atomic(accepted_events)
            
            # STEP 4: Calculate metrics
            duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            
            metrics = FetchPersistMetrics(
                timestamp=datetime.now(timezone.utc),
                providers_queried=len(self.gateway.get_all_adapters()),
                events_fetched=len(raw_events),
                events_accepted=accepted_count,
                events_rejected=rejected_count,
                rejection_reasons=rejection_reasons,
                db_inserts=inserted_count,
                duration_sec=duration,
                success=(persist_error is None),
                error_message=persist_error
            )
            
            # Log cycle completion
            if metrics.success:
                self.logger.info(
                    f"[CYCLE] ✅ Cycle completed: fetched={metrics.events_fetched}, "
                    f"accepted={metrics.events_accepted}, rejected={metrics.events_rejected}, "
                    f"persisted={metrics.db_inserts}, duration={duration:.2f}s"
                )
            else:
                self.logger.error(
                    f"[CYCLE] ❌ Cycle failed: {persist_error}"
                )
            
            return metrics
        
        except Exception as e:
            duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            error_msg = f"Cycle failed with exception: {str(e)}"
            
            self.logger.error(f"[CYCLE] ❌ {error_msg}")
            
            return FetchPersistMetrics(
                timestamp=datetime.now(timezone.utc),
                providers_queried=0,
                events_fetched=0,
                events_accepted=0,
                events_rejected=0,
                rejection_reasons={},
                db_inserts=0,
                duration_sec=duration,
                success=False,
                error_message=error_msg
            )


# Async job function for scheduler
async def fetch_and_persist_economic_data(
    gateway: Optional[EconomicDataProviderRegistry] = None,
    sanitizer: Optional[NewsSanitizer] = None,
    storage: Optional[StorageManager] = None,
    days_back: int = 7
) -> FetchPersistMetrics:
    """
    Async job for EconomicDataScheduler.
    
    Called every 5 minutes to fetch → sanitize → persist economic calendar events.
    
    Args:
        gateway: EconomicDataProviderRegistry instance
        sanitizer: NewsSanitizer instance
        storage: StorageManager instance
        days_back: Days back to fetch
    
    Returns:
        FetchPersistMetrics with cycle statistics
    
    Note:
        If dependencies not provided, will be injected by scheduler.
    """
    if not all([gateway, sanitizer, storage]):
        logger.error("[JOB] Missing dependencies for fetch_and_persist")
        return FetchPersistMetrics(
            timestamp=datetime.now(timezone.utc),
            providers_queried=0,
            events_fetched=0,
            events_accepted=0,
            events_rejected=0,
            rejection_reasons={},
            db_inserts=0,
            duration_sec=0,
            success=False,
            error_message="Missing dependencies"
        )
    
    executor = EconomicFetchPersist(
        gateway=gateway,
        sanitizer=sanitizer,
        storage=storage
    )
    
    return await executor.execute_cycle(days_back=days_back)
