"""
FASE C.5 Integration: Economic Scheduler + Fetch-Persist in MainOrchestrator
PHASE 8: Economic Veto Interface (News-Based Trading Lockdown)

This module provides:
1. EconomicDataScheduler (EDGE-enabled scheduler for fetching economic data)
2. EconomicFetchPersist (fetch → sanitize → persist pipeline)
3. EconomicVetoInterface via get_trading_status() (gates trading decisions)

Integration pattern:
- Scheduler runs in background thread (non-blocking)
- Job executes every 5 minutes
- Graceful degradation: trading never blocked by scheduler
- Autonomous: self-learning, self-healing
- Agnosis preserved: MainOrchestrator only calls get_trading_status(), never knows provider sources

Type Hints: 100% coverage
"""

import logging
import time
from typing import Optional, Callable, Any, Dict, List
from datetime import datetime, timezone, timedelta

from core_brain.economic_scheduler import EconomicDataScheduler, SchedulerConfig
from core_brain.economic_fetch_persist import (
    EconomicFetchPersist,
    FetchPersistMetrics,
    fetch_and_persist_economic_data
)
from connectors.economic_data_gateway import EconomicDataProviderRegistry
from core_brain.news_sanitizer import NewsSanitizer
from data_vault.storage import StorageManager


logger = logging.getLogger(__name__)

# ============================================================================
# Symbol-to-Currency Mapping (Extensible, JSON/DB-Driven)
# ============================================================================

DEFAULT_EVENT_SYMBOL_MAPPING = {
    # NFP (Non-Farm Payroll) - USA
    "NFP": ["USD", "EURUSD", "GBPUSD", "USDCAD", "AUDUSD"],
    "UNEMPLOYMENT": ["USD", "EURUSD", "GBPUSD"],
    "INITIAL_CLAIMS": ["USD", "EURUSD"],
    "RETAIL_SALES": ["USD", "EURUSD", "GBPUSD"],
    "CPI": ["USD", "EURUSD", "GBPUSD"],
    "PPI": ["USD", "EURUSD"],
    "FOMC": ["USD", "EURUSD", "GBPUSD", "USDCAD", "AUDUSD"],
    "FED_RATE": ["USD", "EURUSD", "GBPUSD", "USDCAD", "AUDUSD"],
    
    # ECB (European Central Bank)
    "ECB": ["EUR", "EURUSD", "EURGBP", "EURJPY", "EURCHF"],
    "ECB_RATE": ["EUR", "EURUSD", "EURGBP", "EURJPY"],
    "EUROZONE_CPI": ["EUR", "EURUSD", "EURGBP"],
    
    # BOE (Bank of England)
    "BOE": ["GBP", "GBPUSD", "EURGBP", "GBPJPY", "GBPCHF"],
    "BOE_RATE": ["GBP", "GBPUSD", "EURGBP", "GBPJPY"],
    "UK_CPI": ["GBP", "GBPUSD", "EURGBP"],
    
    # RBA (Reserve Bank of Australia)
    "RBA": ["AUD", "AUDUSD", "EURAUD", "AUDJPY", "GBPAUD"],
    "RBA_RATE": ["AUD", "AUDUSD", "EURAUD", "AUDJPY"],
    "AUSTRALIA_CPI": ["AUD", "AUDUSD"],
    
    # BOJ (Bank of Japan)
    "BOJ": ["JPY", "USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
    "BOJ_RATE": ["JPY", "USDJPY", "EURJPY", "GBPJPY"],
    "JAPAN_CPI": ["JPY", "USDJPY", "EURJPY"],
}


class EconomicIntegrationManager:
    """
    Manager for economic data integration in trading system.
    
    Responsibilities:
    - Initialize scheduler with fetch-persist job
    - Manage lifecycle (start/stop)
    - Expose metrics for monitoring
    - Provide trading status gate via get_trading_status()
    - Ensure zero impact on trading via agnosis preservation
    
    Non-blocking design:
    - Scheduler uses BackgroundScheduler (thread-based, non-blocking)
    - Trading loop runs independently in AsyncIO event loop
    - No contention or deadlocks possible
    - get_trading_status() uses in-memory cache (60s TTL, <50ms latency)
    """
    
    def __init__(self, gateway: EconomicDataProviderRegistry, sanitizer: NewsSanitizer, storage: StorageManager, scheduler_config: Optional[SchedulerConfig] = None) -> None:
        """
        Initialize integration manager.
        
        Args:
            gateway: Data provider gateway
            sanitizer: Economic data sanitizer
            storage: Database storage
            scheduler_config: Optional custom scheduler config
            
        Raises:
            TypeError: If dependencies not properly typed
            ValueError: If storage doesn't have required methods
        """
        # Validate agnosis: storage must be generic (no broker specifics)
        if not hasattr(storage, 'get_economic_events_by_window'):
            raise ValueError(
                "Storage must implement get_economic_events_by_window() method"
            )
        if not hasattr(storage, '_get_conn'):
            raise ValueError(
                "Storage must implement _get_conn() method for DB access"
            )
        
        self.gateway = gateway
        self.sanitizer = sanitizer
        self.storage = storage
        self.config = scheduler_config or SchedulerConfig()
        
        # Will be initialized in setup()
        self.fetch_persist: Optional[EconomicFetchPersist] = None
        self.scheduler: Optional[EconomicDataScheduler] = None
        
        # Cache for get_trading_status() (60s TTL)
        self._trading_status_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 60.0  # 60 seconds
        
        # Event-to-symbol mapping (extensible from DB)
        self._event_symbol_map = DEFAULT_EVENT_SYMBOL_MAPPING.copy()
        
        self.logger = logger
    
    async def setup(self) -> bool:
        """
        Initialize scheduler with fetch-persist job.
        
        Returns:
            True if setup successful, False otherwise
        """
        try:
            self.logger.info("[ECON-INTEGRATION] Setting up economic scheduler...")
            
            # Create fetch-persist executor
            self.fetch_persist = EconomicFetchPersist(
                gateway=self.gateway,
                sanitizer=self.sanitizer,
                storage=self.storage
            )
            
            # Create async job function that captures executor
            async def job_wrapper() -> 'FetchPersistMetrics':
                """Wrapper for scheduler job."""
                return await self.fetch_persist.execute_cycle(days_back=7)
            
            # Create scheduler with job function
            self.scheduler = EconomicDataScheduler(
                fetch_and_persist_func=job_wrapper,
                config=self.config
            )
            
            self.logger.info(
                f"[ECON-INTEGRATION] ✅ Scheduler initialized: "
                f"interval={self.config.job_interval_minutes}min, "
                f"max_cpu={self.config.max_critical_cpu_pct}%"
            )
            return True
        
        except Exception as e:
            self.logger.error(f"[ECON-INTEGRATION] ❌ Setup failed: {str(e)}")
            return False
    
    async def start(self) -> bool:
        """
        Start economic data scheduler.
        
        Returns:
            True if started successfully
        """
        if not self.scheduler:
            self.logger.error("[ECON-INTEGRATION] Scheduler not initialized")
            return False
        
        try:
            self.scheduler.start()
            self.logger.info("[ECON-INTEGRATION] ✅ Scheduler started")
            return True
        
        except Exception as e:
            self.logger.error(f"[ECON-INTEGRATION] ❌ Start failed: {str(e)}")
            return False
    
    async def stop(self) -> bool:
        """
        Stop economic data scheduler gracefully.
        
        Returns:
            True if stopped successfully
        """
        if not self.scheduler:
            return True
        
        try:
            self.scheduler.stop()
            self.logger.info("[ECON-INTEGRATION] ✅ Scheduler stopped")
            return True
        
        except Exception as e:
            self.logger.error(f"[ECON-INTEGRATION] ❌ Stop failed: {str(e)}")
            return False
    
    def get_scheduler_health(self) -> Dict[str, Any]:
        """
        Get scheduler health and EDGE intelligence.
        
        Returns:
            Dict with health status, metrics, and EDGE info
        """
        if not self.scheduler:
            return {'status': 'not_initialized'}
        
        health = self.scheduler.get_health()
        intelligence = self.scheduler.get_edge_intelligence()
        
        return {
            'health': health,
            'edge_intelligence': intelligence,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get economic data integration metrics.
        
        Returns:
            Dict with fetch/sanitize/persist metrics
        """
        if not self.scheduler:
            return {}
        
        metrics = self.scheduler.get_metrics_summary()
        return {
            'scheduler_metrics': metrics,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    # ========================================================================
    # ECONOMIC VETO INTERFACE (Contract 2: News-Based Trading Lockdown)
    # ========================================================================
    
    def _get_affected_symbols(self, event_name: str) -> List[str]:
        """
        Get currency pairs affected by an event (extensible from DB).
        
        Args:
            event_name: Event name (e.g., 'NFP', 'ECB', 'BOE')
        
        Returns:
            List of currency pairs affected
        """
        # Normalize event name for lookup
        normalized = event_name.upper().replace(" ", "_").replace("-", "_")
        
        # Check exact match
        if normalized in self._event_symbol_map:
            return self._event_symbol_map[normalized]
        
        # Check partial matches
        for key, symbols in self._event_symbol_map.items():
            if key in normalized or normalized in key:
                return symbols
        
        # Default: assume USD impact
        return ["USD", "EURUSD", "GBPUSD", "AUDUSD"]
    
    def _get_impact_buffers(self, impact_level: str) -> tuple[int, int]:
        """
        Get pre/post event buffers based on impact level.
        
        Args:
            impact_level: 'HIGH', 'MEDIUM', or 'LOW'
        
        Returns:
            Tuple of (pre_buffer_minutes, post_buffer_minutes)
        """
        buffers = {
            "HIGH": (15, 10),    # 15m pre, 10m post
            "MEDIUM": (5, 3),    # 5m pre, 3m post
            "LOW": (0, 0),       # No buffer
        }
        return buffers.get(impact_level, (0, 0))
    
    async def get_trading_status(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Check trading permission for a symbol based on economic calendar.
        
        This is the main VETO INTERFACE that MainOrchestrator queries.
        Preserves agnosis: caller never knows provider sources.
        
        Args:
            symbol: Currency pair (e.g., 'EUR/USD')
            current_time: Current time (defaults to UTC now)
        
        Returns:
            Dict containing:
            {
                "is_tradeable": bool,           # Can open new usr_positions?
                "restriction_level": str,      # "BLOCK" | "CAUTION" | "NORMAL"
                "reason": str,                  # Human-readable explanation
                "next_event": str,              # Name of next event
                "next_event_impact": str,      # Impact level of next event
                "time_to_event": float,         # Seconds until next event
                "buffer_pre_minutes": int,      # Pre-event buffer
                "buffer_post_minutes": int,      # Post-event buffer
                "cached": bool,                 # Whether result came from cache
                "timestamp": str                # Response timestamp (ISO 8601)
            }
        """
        start_time = time.time()
        current_time = current_time or datetime.now(timezone.utc)
        
        # Check cache first (60s TTL)
        cache_key = f"{symbol}_{current_time.date()}"
        if cache_key in self._trading_status_cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
            if cache_age < self._cache_ttl:
                result = self._trading_status_cache[cache_key]
                result["cached"] = True
                result["latency_ms"] = round((time.time() - start_time) * 1000, 2)
                return result
        
        try:
            # Query sys_economic_calendar for upcoming events
            events = self._query_economic_calendar(symbol, current_time)
            
            if not events:
                # No events: normal trading
                elapsed = time.time() - start_time
                result = {
                    "is_tradeable": True,
                    "restriction_level": "NORMAL",
                    "reason": "No economic events scheduled",
                    "next_event": None,
                    "next_event_impact": None,
                    "time_to_event": None,
                    "buffer_pre_minutes": 0,
                    "buffer_post_minutes": 0,
                    "cached": False,
                    "latency_ms": round(elapsed * 1000, 2),
                    "timestamp": current_time.isoformat()
                }
                
                # Cache result
                self._trading_status_cache[cache_key] = result
                self._cache_timestamps[cache_key] = time.time()
                
                return result
            
            # Get closest upcoming event
            next_event = events[0]
            event_name = next_event.get("event_name", "UNKNOWN")
            impact_level = next_event.get("impact_score", "LOW")
            event_time = next_event.get("event_time_utc")
            
            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            
            # Calculate time to event
            time_to_event = (event_time - current_time).total_seconds()
            
            # Get buffers for this impact level
            pre_buf, post_buf = self._get_impact_buffers(impact_level)
            pre_buf_secs = pre_buf * 60
            post_buf_secs = post_buf * 60
            
            # Determine trading status
            is_tradeable = True
            restriction_level = "NORMAL"
            
            if -post_buf_secs <= time_to_event <= pre_buf_secs:
                # Within buffer window
                if impact_level == "HIGH":
                    is_tradeable = False
                    restriction_level = "BLOCK"
                elif impact_level == "MEDIUM":
                    is_tradeable = True
                    restriction_level = "CAUTION"
            
            elapsed = time.time() - start_time
            result = {
                "is_tradeable": is_tradeable,
                "restriction_level": restriction_level,
                "reason": self._format_reason(impact_level, time_to_event, pre_buf_secs),
                "next_event": event_name,
                "next_event_impact": impact_level,
                "time_to_event": time_to_event,
                "buffer_pre_minutes": pre_buf,
                "buffer_post_minutes": post_buf,
                "cached": False,
                "latency_ms": round(elapsed * 1000, 2),
                "timestamp": current_time.isoformat()
            }
            
            # Cache result
            self._trading_status_cache[cache_key] = result.copy()
            self._cache_timestamps[cache_key] = time.time()
            
            # Log if latency exceeds threshold
            if elapsed * 1000 > 50:
                self.logger.warning(
                    f"[ECON-VETO] Latency exceeded 50ms: {result['latency_ms']}ms "
                    f"for {symbol} (event: {event_name})"
                )
            
            return result
        
        except Exception as e:
            # Graceful degradation: fail-open if DB is down
            self.logger.warning(
                f"[ECON-VETO] ⚠️ Error querying economic calendar: {str(e)}. "
                f"Failing open (is_tradeable=True) to preserve trading."
            )
            
            elapsed = time.time() - start_time
            return {
                "is_tradeable": True,  # FAIL-OPEN: allow trading if DB is down
                "restriction_level": "NORMAL",
                "reason": "Economic calendar unavailable (graceful degradation)",
                "next_event": None,
                "next_event_impact": None,
                "time_to_event": None,
                "buffer_pre_minutes": 0,
                "buffer_post_minutes": 0,
                "cached": False,
                "latency_ms": round(elapsed * 1000, 2),
                "timestamp": current_time.isoformat(),
                "degraded_mode": True
            }
    
    def _query_economic_calendar(self, symbol: str, current_time: datetime) -> List[Dict[str, Any]]:
        """
        Query sys_economic_calendar for upcoming events affecting this symbol.
        
        Args:
            symbol: Currency pair (e.g., 'EUR/USD')
            current_time: Current time (UTC)
        
        Returns:
            List of events sorted by time_to_event (ascending)
        """
        try:
            # Get affected currencies for this symbol
            currencies = self._extract_currencies(symbol)
            
            if not currencies:
                return []
            
            # Query affected events
            conn = self.storage._get_conn()
            cursor = conn.cursor()
            
            # Get events in the next 24 hours
            time_window = current_time + timedelta(hours=24)
            
            placeholders = ",".join(["?" for _ in currencies])
            query = f"""
                SELECT event_id, event_name, country, currency, impact_score, event_time_utc
                FROM sys_economic_calendar
                WHERE currency IN ({placeholders})
                  AND event_time_utc >= datetime(?)
                  AND event_time_utc <= datetime(?)
                ORDER BY event_time_utc ASC
                LIMIT 10
            """
            
            cursor.execute(
                query,
                currencies + [current_time.isoformat(), time_window.isoformat()]
            )
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return []
            
            # Convert to dicts
            events = []
            for row in rows:
                events.append({
                    "event_id": row[0],
                    "event_name": row[1],
                    "country": row[2],
                    "currency": row[3],
                    "impact_score": row[4],
                    "event_time_utc": row[5],
                })
            
            return events
        
        except Exception as e:
            self.logger.error(f"[ECON-VETO] Error querying calendar: {str(e)}")
            return []
    
    def _extract_currencies(self, symbol: str) -> List[str]:
        """
        Extract currency codes from symbol.
        
        Args:
            symbol: Symbol (e.g., 'EUR/USD' or 'EURUSD')
        
        Returns:
            List of currency codes (e.g., ['EUR', 'USD'])
        """
        # Normalize symbol
        symbol = symbol.upper().replace("/", "").replace(" ", "")
        
        # Handle major pairs (4-6 chars)
        if len(symbol) == 6:
            return [symbol[:3], symbol[3:]]
        elif len(symbol) == 7:
            return [symbol[:3], symbol[3:6]]
        
        # Fallback
        return []
    
    def _format_reason(self, impact_level: str, time_to_event: float, pre_buf_secs: float) -> str:
        """Format human-readable reason for trading restriction."""
        if time_to_event < 0:
            minutes_ago = int(abs(time_to_event) / 60)
            return f"{impact_level} impact event {minutes_ago}m ago (post-event buffer active)"
        else:
            minutes_ahead = int(time_to_event / 60)
            return f"{impact_level} impact event in {minutes_ahead}m (pre-event buffer active)"


# ============================================================================
# INTEGRATION WITH MAIMORCHESTRATOR
# ============================================================================

def create_economic_integration(gateway: EconomicDataProviderRegistry, sanitizer: NewsSanitizer, storage: StorageManager, scheduler_config: Optional[SchedulerConfig] = None) -> EconomicIntegrationManager:
    """
    Factory function for creating economic integration manager.
    
    Args:
        gateway: Data provider gateway
        sanitizer: Economic data sanitizer  
        storage: Database storage
        scheduler_config: Optional custom scheduler config
    
    Returns:
        Configured EconomicIntegrationManager instance
    """
    return EconomicIntegrationManager(
        gateway=gateway,
        sanitizer=sanitizer,
        storage=storage,
        scheduler_config=scheduler_config
    )
