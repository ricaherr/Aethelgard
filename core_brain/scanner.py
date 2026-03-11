"""
Escáner Proactivo - Pure Executor (OPTION A - 11-Mar-2026)
Ejecuta escaneos BAJO DEMANDA desde MainOrchestrator.
MainOrchestrator es el ÚNICO orquestador de timing.

Antes: ScannerEngine tenía timing logic + autonomía
Ahora:  MainOrchestrator decide CUÁNDO, ScannerEngine ejecuta QUÉ

Agnóstico de plataforma: recibe un DataProvider inyectado (ej. MT5).
"""
from __future__ import annotations

import logging
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor, as_completed

from models.signal import MarketRegime
from core_brain.regime import RegimeClassifier
from core_brain.data_provider_manager import DataProvider

logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:
    psutil = None


class CPUMonitor:
    """
    Monitor de uso de CPU. Si el uso supera cpu_limit_pct (configurable),
    el escáner debe aumentar el sleep entre ciclos.
    """

    def __init__(self, cpu_limit_pct: float = 80.0, interval: float = 0.3):
        self.cpu_limit_pct = max(1.0, min(100.0, cpu_limit_pct))
        self.interval = max(0.1, interval)

    def get_cpu_percent(self) -> float:
        """Devuelve el uso de CPU actual (0–100)."""
        if not psutil:
            return 0.0
        try:
            return float(psutil.cpu_percent(interval=self.interval))
        except Exception as e:
            logger.debug("Error leyendo CPU: %s", e)
            return 0.0

    def over_limit(self) -> bool:
        """True si el uso de CPU supera el umbral configurado."""
        return self.get_cpu_percent() > self.cpu_limit_pct


class ScannerEngine:
    """
    Orquestador del Escáner Proactivo Multihilo.
    - Recibe lista de activos y un DataProvider.
    - Procesa RegimeClassifier por activo en hilos (concurrent.futures).
    - Control de recursos: si CPU > X%, aumenta sleep entre escaneos.
    - Priorización: TREND/CRASH cada 1s, RANGE/NEUTRAL cada 5–10s.
    """

    def __init__(
        self,
        assets: List[str],
        data_provider: Any,
        config_path: Optional[str] = None,
        config_data: Optional[Dict] = None,
        regime_config_path: Optional[str] = None,
        scan_mode: str = "STANDARD",
        storage: Optional[Any] = None,
    ):
        self.assets = list(assets) if assets else []
        self.provider = data_provider
        self.config_path = config_path
        self.storage = storage
        self.scan_mode = scan_mode.upper()
        
        # 1. Resolve configuration (SSOT)
        sc = self._load_engine_config(config_data, storage, config_path)
        
        # 2. Apply scan mode settings
        self._apply_scan_mode_settings(sc)
        
        # 3. Initialize state and classifiers
        self._init_engine_state()
        self._init_classifiers()

    def _load_engine_config(self, config_data: Optional[Dict], storage: Optional[Any], config_path: Optional[str]) -> Dict:
        """Resolves configuration from multiple sources with SSOT priority."""
        cfg = {}
        if config_data:
            cfg = config_data
        elif storage:
            state = storage.get_sys_config()
            cfg = state.get("global_config", {}) if isinstance(state, dict) else {}
        elif config_path:
            try:
                cfg_file = Path(config_path)
                if cfg_file.exists():
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f) or {}
            except Exception as e:
                logger.warning("Failed loading scanner config: %s", e)
        
        if config_path and not storage and not config_data:
            logger.warning("ScannerEngine config_path is legacy compatibility mode.")
            
        return cfg.get("scanner", cfg)

    def _apply_scan_mode_settings(self, sc: Dict) -> None:
        """Applies operational settings and scan mode multipliers."""
        mode_configs = {
            "ECO": {"cpu_limit_pct": 50.0, "max_workers_multiplier": 0.5, "base_sleep_multiplier": 2.0},
            "STANDARD": {"cpu_limit_pct": 80.0, "max_workers_multiplier": 1.0, "base_sleep_multiplier": 1.0},
            "AGRESSIVE": {"cpu_limit_pct": 95.0, "max_workers_multiplier": 2.0, "base_sleep_multiplier": 0.5},
        }
        
        selected_mode = mode_configs.get(self.scan_mode, mode_configs["STANDARD"])
        
        # CPU and Sleep settings
        self.cpu_limit_pct = float(sc.get("cpu_limit_pct", selected_mode["cpu_limit_pct"]))
        self.sleep_trend = float(sc.get("sleep_trend_seconds", 1.0))
        self.sleep_range = float(sc.get("sleep_range_seconds", 10.0))
        self.sleep_neutral = float(sc.get("sleep_neutral_seconds", 5.0))
        self.sleep_crash = float(sc.get("sleep_crash_seconds", 1.0))
        self.base_sleep = float(sc.get("base_sleep_seconds", 1.0)) * selected_mode["base_sleep_multiplier"]
        self.max_sleep_multiplier = float(sc.get("max_sleep_multiplier", 5.0))
        
        # Data settings
        self.mt5_timeframe = str(sc.get("mt5_timeframe", "M5"))
        self.mt5_bars_count = int(sc.get("mt5_bars_count", 500))
        
        # Workers count
        cpu_count = psutil.cpu_count(logical=True) if psutil else 1
        self._max_workers = max(1, int(cpu_count * selected_mode["max_workers_multiplier"]))
        
        # Provider type detection
        self.is_local_provider = isinstance(self.provider, DataProvider) and self.provider.is_local()
        if self.is_local_provider:
            self.base_sleep = 0.5
            self.sleep_trend = 0.5
        else:
            self.base_sleep = max(2.0, self.base_sleep)

        # Timeframes initialization
        timeframes_config = sc.get("timeframes", [])
        self.active_timeframes = [tf["timeframe"] for tf in timeframes_config if tf.get("enabled", True)]
        if not self.active_timeframes:
            self.active_timeframes = [self.mt5_timeframe]

    def _init_engine_state(self) -> None:
        """Initializes internal tracking dictionaries and monitors."""
        self.cpu_monitor = CPUMonitor(cpu_limit_pct=self.cpu_limit_pct)
        self.classifiers: Dict[str, RegimeClassifier] = {}
        self.last_regime: Dict[str, MarketRegime] = {}
        self.last_scan_time: Dict[str, float] = {}
        self.last_dataframes: Dict[str, Any] = {}
        self.last_providers: Dict[str, str] = {}
        self.consecutive_failures: Dict[str, int] = {}
        self.circuit_breaker_cooldowns: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False
        
        # OPTION A: Cache for LATEST scan results (accessed by MainOrchestrator)
        # MainOrchestrator orchestrates when to scan, ScannerEngine just caches results
        self.last_results: Dict[str, Dict[str, Any]] = {}

    def _init_classifiers(self) -> None:
        """Factory for RegimeClassifiers per asset/timeframe."""
        for symbol in self.assets:
            for tf in self.active_timeframes:
                key = f"{symbol}|{tf}"
                self.classifiers[key] = RegimeClassifier(storage=self.storage)
                self.last_regime[key] = MarketRegime.NORMAL
                self.last_scan_time[key] = 0.0

    def _scan_one(self, symbol: str, timeframe: str) -> Optional[Tuple[str, str, MarketRegime, Dict, Any]]:
        """Escanea un único activo en un hilo."""
        key = f"{symbol}|{timeframe}"
        
        # CIRCUIT BREAKER: Verificar si el activo está en cooldown
        if key in self.circuit_breaker_cooldowns and time.monotonic() < self.circuit_breaker_cooldowns[key]:
            logger.debug(f"[{key}] En cooldown por Circuit Breaker. Saltando escaneo.")
            return None

        try:
            # Obtener datos del proveedor (usando protocolo DataProvider: fetch_ohlc)
            df = self.provider.fetch_ohlc(
                symbol,
                timeframe=timeframe,
                count=self.mt5_bars_count
            )
            if df is None or df.empty:
                logger.warning("No se pudieron obtener datos para %s [%s]", symbol, timeframe)
                self._handle_scan_failure(key)
                return None

            # Clasificar régimen
            classifier = self.classifiers[key]
            provider_id = getattr(self.provider, "provider_name", "UNKNOWN")
            if hasattr(self.provider, "get_best_provider"):
                instance = self.provider.get_best_provider()
                if instance:
                    provider_id = getattr(instance, "name", provider_id)

            regime = classifier.classify()
            metrics = classifier.get_metrics()
            
            # Resetear fallos consecutivos si el escaneo fue exitoso
            self.consecutive_failures.pop(key, None)
            self.circuit_breaker_cooldowns.pop(key, None)

            return symbol, timeframe, regime, metrics, df, provider_id
        except Exception as e:
            logger.error("Error escaneando %s [%s]: %s", symbol, timeframe, e)
            self._handle_scan_failure(key)
            return None

    def _handle_scan_failure(self, key: str) -> None:
        """Maneja el fallo de escaneo actualizando el Circuit Breaker y registrando el evento."""
        current_failures = self.consecutive_failures.get(key, 0) + 1
        self.consecutive_failures[key] = current_failures
        
        symbol, timeframe = key.split("|")
        
        # Log del evento persistente (Data Drift)
        if self.storage:
            try:
                self.storage.save_coherence_event({
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'stage': 'SCANNER',
                    'status': 'FAIL',
                    'incoherence_type': 'DATA_DRIFT',
                    'reason': f'Consecutive failures: {current_failures}',
                    'details': f'Failed to fetch OHLC for {key}',
                    'connector_type': 'mt5' if self.is_local_provider else 'generic'
                })
            except Exception as e:
                logger.error(f"Error logging scan failure to DB: {e}")

        if current_failures >= 3:
            # 60 segundos de cooldown
            cooldown_time = time.monotonic() + 60 
            self.circuit_breaker_cooldowns[key] = cooldown_time
            logger.warning(f"[{key}] Circuit Breaker activado: {current_failures} fallos consecutivos. En cooldown por 60s.")

    def execute_scan(self, assets_to_scan: List[Tuple[str, str]]) -> Dict[str, Dict[str, Any]]:
        """
        OPTION A: Pure Executor - Scan ONLY the requested assets.
        
        MainOrchestrator decides WHEN and WHAT to scan.
        ScannerEngine just executes the request.
        
        Args:
            assets_to_scan: List of (symbol, timeframe) tuples to scan now
        
        Returns:
            Dict mapping "symbol|timeframe" -> {regime, metrics, df, provider, ...}
        """
        results = {}
        
        if not assets_to_scan:
            logger.debug("[EXECUTE_SCAN] No assets to scan")
            return results
        
        logger.info(f"[EXECUTE_SCAN] Scanning {len(assets_to_scan)} asset-timeframe pairs")
        
        # Execute scans in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
            futs = {ex.submit(self._scan_one, sym, tf): (sym, tf) for sym, tf in assets_to_scan}
            
            for fut in as_completed(futs):
                try:
                    res = fut.result()
                    if res:
                        # res = (symbol, timeframe, regime, metrics, df, provider_id)
                        symbol, timeframe, regime, metrics, df, provider_id = res
                        key = f"{symbol}|{timeframe}"
                        
                        # Store in result dict
                        results[key] = {
                            "regime": regime,
                            "metrics": metrics,
                            "df": df,
                            "provider_source": provider_id,
                            "symbol": symbol,
                            "timeframe": timeframe
                        }
                        
                        # Also persist using _process_scan_result() for compatibility
                        self._process_scan_result(res)
                except Exception as e:
                    sym, tf = futs[fut]
                    logger.warning(f"[EXECUTE_SCAN] Exception in scan thread for {sym}[{tf}]: {e}")
        
        # Update cache
        self.last_results.update(results)
        logger.info(f"[EXECUTE_SCAN] ✓ Completed: {len(results)} results cached")
        
        return results

    def _run_cycle(self) -> None:
        """
        ⚠️ DEPRECATED (OPTION A) - This method is never called anymore.
        
        OLD behavior was:
        - Decide which assets to scan (timing logic)
        - Call _scan_one for each
        - Process results
        
        NEW: execute_scan() is called by MainOrchestrator with explicit list
        """
        logger.debug("[_RUN_CYCLE] This method is deprecated in OPTION A. Use execute_scan() instead.")

    def _get_assets_to_scan(self) -> List[Tuple[str, str]]:
        """
        ⚠️ DEPRECATED (OPTION A - 11-Mar-2026)
        
        OLD: Timing logic lived here (caused triple-scanning)
        NEW: MainOrchestrator._get_scan_schedule() + _should_scan_now() handle timing
        
        This method is never called anymore but kept for backward compatibility.
        Returns empty list."""
        logger.debug("[_GET_ASSETS_TO_SCAN] This method is deprecated in OPTION A. MainOrchestrator handles timing.")
        return []

    def _process_scan_result(self, res: Tuple[str, str, MarketRegime, Dict, Any, str]) -> None:
        """Processes and persists the result of a single asset scan."""
        symbol, timeframe, regime, metrics, df, provider_id = res
        key = f"{symbol}|{timeframe}"
        now = time.monotonic()

        with self._lock:
            self.last_regime[key] = regime
            self.last_scan_time[key] = now
            self.last_dataframes[key] = df
            self.last_providers[key] = provider_id
        
        # Persistence for cross-process (Heatmap) - write to GLOBAL sys_market_pulse
        if self.storage:
            try:
                state_data = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "regime": regime.value,
                    "metrics": metrics,
                    "timestamp": datetime.now().isoformat()
                }
                self.storage.log_sys_market_pulse(state_data)
            except Exception as e:
                logger.error(f"Error persisting market state for {key}: {e}")

        logger.info(
            "Scanner %s [%s] -> %s (ADX=%.2f)",
            symbol, timeframe, regime.value, metrics.get("adx", 0) or 0,
        )

    def _adaptive_sleep(self) -> float:
        """
        ⚠️ DEPRECATED (OPTION A - 11-Mar-2026)
        
        OLD: Adjusted sleep based on CPU usage in autonomous loop
        NEW: MainOrchestrator controls timing, no sleep needed in ScannerEngine
        
        This method is never called anymore but kept for backward compatibility.
        Returns base sleep value.
        """
        logger.debug("[_ADAPTIVE_SLEEP] This method is deprecated in OPTION A. MainOrchestrator handles timing.")
        return self.base_sleep

    def run(self) -> None:
        """
        ⚠️ DEPRECATED (OPTION A - 11-Mar-2026)
        
        OLD: Autonomous scan loop (caused triple-scanning with MainOrchestrator)
        NEW: MainOrchestrator is sole orchestrator. ScannerEngine is pure executor.
        
        This method is kept for backward compatibility but does NOTHING.
        MainOrchestrator calls execute_scan() when it decides scans are due.
        """
        logger.warning(
            "[DEPRECATED] ScannerEngine.run() is no-op in OPTION A. "
            "MainOrchestrator is sole orchestrator. Remove scanner thread from start.py!"
        )
        # No autonomous loop - MainOrchestrator controls timing
        return

    def stop(self) -> None:
        """Stops the autonomous loop (deprecated in OPTION A, but kept for compatibility)."""
        self._running = False
    
    def _reload_timeframes_if_changed(self) -> None:
        """
        Hot-reload de timeframes desde StorageManager (SSOT).
        Detecta cambios y actualiza self.active_timeframes sin reiniciar el hilo.
        Coherente con sistema de module toggles (scanner enabled/disabled).
        Permite que TrifectaAnalyzer auto-habilite timeframes y Scanner los detecte.
        """
        try:
            config = {}
            # SSOT: Reload via StorageManager if available
            if self.storage:
                state = self.storage.get_sys_config()
                config = state.get("global_config", {}) or {}
            else:
                return

            scanner_config = config.get("scanner", {})
            timeframes_config = scanner_config.get("timeframes", [])
            
            if not timeframes_config:
                return
            
            # Extract currently enabled timeframes from config
            enabled_tfs = [tf["timeframe"] for tf in timeframes_config if tf.get("enabled", True)]
            
            # Compare with current active timeframes
            if set(enabled_tfs) != set(self.active_timeframes):
                with self._lock:
                    old_tfs = self.active_timeframes.copy()
                    self.active_timeframes = enabled_tfs
                    
                    # Create classifiers for new timeframes
                    for symbol in self.assets:
                        for tf in self.active_timeframes:
                            key = f"{symbol}|{tf}"
                            if key not in self.classifiers:
                                logger.info(f"[RELOAD] [SCANNER] Creating classifier for new timeframe: {key}")
                                self.classifiers[key] = RegimeClassifier(storage=self.storage)
                                self.last_regime[key] = MarketRegime.NORMAL
                                self.last_scan_time[key] = 0.0
                
                logger.warning(
                    f"[RELOAD] [SCANNER] Timeframes hot-reloaded: {old_tfs} -> {enabled_tfs}. "
                    f"Scanning will now include all enabled timeframes."
                )
        
        except Exception as e:
            logger.error(f"[SCANNER] Failed to reload timeframes: {e}", exc_info=True)

    def get_all_regimes(self) -> Dict[str, MarketRegime]:
        """
        Obtiene los últimos regímenes detectados para todos los símbolos.
        Método para compatibilidad con el orquestador.
        
        Returns:
            Dict con symbol -> MarketRegime
        """
        with self._lock:
            return dict(self.last_regime)
    
    def get_scan_results_with_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns latest cached scan results with DataFrames.
        
        OPTION A: Simply returns self.last_results (updated by execute_scan())
        
        Returns:
            Dict with "symbol|timeframe" -> {"regime": ..., "df": ..., "symbol": ..., "timeframe": ...}
        """
        with self._lock:
            return self.last_results.copy() if self.last_results else {}

    def get_status(self) -> Dict[str, Any]:
        """Current status: regimes, CPU, last results count (no dedup stats in OPTION A)."""
        with self._lock:
            regimes = dict(self.last_regime)
            last_scan = dict(self.last_scan_time)
        cpu = self.cpu_monitor.get_cpu_percent() if psutil else 0.0
        
        return {
            "assets": list(self.assets),
            "last_regime": {k: v.value for k, v in regimes.items()},
            "last_scan_time": last_scan,
            "cpu_percent": cpu,
            "cpu_limit_pct": self.cpu_limit_pct,
            "running": self._running,
            # OPTION A: Dedup removed (timing is in MainOrchestrator now)
            "cached_results": len(self.last_results),
        }
