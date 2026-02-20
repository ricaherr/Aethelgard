"""
Escáner Proactivo Multihilo.
Orquestador que escanea una lista de activos, clasifica régimen por activo en hilos separados,
controla recursos (CPU) y prioriza TREND (1s) vs RANGE (10s).
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
        
        # SSOT: Prefer injected config_data, then storage, then legacy config file path.
        if config_data:
            cfg = config_data
        elif storage:
            # SSOT: Get from StorageManager (bootstrapped from config.json)
            state = storage.get_system_state()
            cfg = state.get("global_config", {}) if isinstance(state, dict) else {}
        elif config_path:
            cfg = {}
            try:
                cfg_file = Path(config_path)
                if cfg_file.exists():
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        cfg = loaded
            except Exception as e:
                logger.warning("Failed loading scanner config from config_path: %s", e)
        else:
            # No config source
            cfg = {}

        if config_path and not storage and not config_data:
            logger.warning("ScannerEngine config_path is legacy compatibility mode.")
            
        sc = cfg.get("scanner", cfg) # Support both full config or just scanner segment

        self.scan_mode = scan_mode.upper()
        
        # Configuraciones predefinidas para los modos de escaneo
        mode_configs = {
            "ECO": {"cpu_limit_pct": 50.0, "max_workers_multiplier": 0.5, "base_sleep_multiplier": 2.0},
            "STANDARD": {"cpu_limit_pct": 80.0, "max_workers_multiplier": 1.0, "base_sleep_multiplier": 1.0},
            "AGRESSIVE": {"cpu_limit_pct": 95.0, "max_workers_multiplier": 2.0, "base_sleep_multiplier": 0.5}, # Ajustado a 95% para AGRESSIVE
        }
        
        selected_mode = mode_configs.get(self.scan_mode, mode_configs["STANDARD"])
        
        self.cpu_limit_pct = float(sc.get("cpu_limit_pct", selected_mode["cpu_limit_pct"]))
        self.sleep_trend = float(sc.get("sleep_trend_seconds", 1.0))
        self.sleep_range = float(sc.get("sleep_range_seconds", 10.0))
        self.sleep_neutral = float(sc.get("sleep_neutral_seconds", 5.0))
        self.sleep_crash = float(sc.get("sleep_crash_seconds", 1.0))
        self.base_sleep = float(sc.get("base_sleep_seconds", 1.0)) * selected_mode["base_sleep_multiplier"]
        self.max_sleep_multiplier = float(sc.get("max_sleep_multiplier", 5.0))
        self.mt5_timeframe = str(sc.get("mt5_timeframe", "M5"))  # Deprecated, use timeframes array
        self.mt5_bars_count = int(sc.get("mt5_bars_count", 500))
        
        # Load active timeframes from configuration
        timeframes_config = sc.get("timeframes", [])

        # Determine max_workers based on CPU count and multiplier
        cpu_count = psutil.cpu_count(logical=True) if psutil else 1
        self._max_workers = max(1, int(cpu_count * selected_mode["max_workers_multiplier"]))
        
        # Check if data provider is local (MT5) or remote
        self.is_local_provider = isinstance(self.provider, DataProvider) and self.provider.is_local()
        if self.is_local_provider:
            logger.info("[SCANNER] Proveedor LOCAL detectado (MT5). Modo ultra-rápido activado.")
            self.base_sleep = 0.5  # 500ms para local
            self.sleep_trend = 0.5
        else:
            logger.info("[SCANNER] Proveedor REMOTO detectado. Aplicando latencia de seguridad.")
            self.base_sleep = max(2.0, self.base_sleep) # Mínimo 2s para remoto
            
        # Initialize active_timeframes from config
        self.active_timeframes = [tf["timeframe"] for tf in timeframes_config if tf.get("enabled", True)]
        if not self.active_timeframes:
            # Fallback to legacy mt5_timeframe if no timeframes are configured
            self.active_timeframes = [self.mt5_timeframe]
            logger.warning(f"No active timeframes configured. Falling back to legacy mt5_timeframe: {self.mt5_timeframe}")
            
        logger.info(f"Active timeframes for scanning: {self.active_timeframes}")
        rp = regime_config_path or sc.get("config_path", None)

        self.cpu_monitor = CPUMonitor(cpu_limit_pct=self.cpu_limit_pct)
        # Multi-timeframe support: key = "symbol|timeframe"
        self.classifiers: Dict[str, RegimeClassifier] = {}
        self.last_regime: Dict[str, MarketRegime] = {}
        self.last_scan_time: Dict[str, float] = {}
        self.last_dataframes: Dict[str, Any] = {}  # Almacenar últimos DataFrames
        
        # CIRCUIT BREAKER: Rastrear fallos consecutivos por símbolo
        self.consecutive_failures: Dict[str, int] = {}
        self.circuit_breaker_cooldowns: Dict[str, float] = {} # Timestamp until when it's paused
        
        self._lock = threading.Lock()
        self._running = False
        
        # Inicializar clasificadores para todos los activos y timeframes
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
            classifier.load_ohlc(df)
            regime = classifier.classify()
            metrics = classifier.get_metrics()
            
            # Resetear fallos consecutivos si el escaneo fue exitoso
            self.consecutive_failures.pop(key, None)
            self.circuit_breaker_cooldowns.pop(key, None)

            return symbol, timeframe, regime, metrics, df
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

    def _run_cycle(self) -> None:
        """Ejecuta un ciclo completo de escaneo para todos los activos."""
        to_scan = []
        now = time.monotonic()

        with self._lock:
            for symbol in self.assets:
                for tf in self.active_timeframes:
                    key = f"{symbol}|{tf}"
                    last_scan_time = self.last_scan_time.get(key, 0.0)
                    regime = self.last_regime.get(key, MarketRegime.NORMAL)

                    # Priorización de escaneo
                    if regime in [MarketRegime.TREND, MarketRegime.CRASH]:
                        if now - last_scan_time >= self.sleep_trend:
                            to_scan.append((symbol, tf))
                    elif regime in [MarketRegime.RANGE, MarketRegime.NORMAL]:
                        if now - last_scan_time >= self.sleep_range:
                            to_scan.append((symbol, tf))
                    else: # Default o inicial
                        if now - last_scan_time >= self.base_sleep:
                            to_scan.append((symbol, tf))

        if not to_scan:
            # logger.debug("No hay activos para escanear en este ciclo.")
            return

        with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
            futs = {ex.submit(self._scan_one, sym, tf): (sym, tf) for sym, tf in to_scan}
            for fut in as_completed(futs):
                try:
                    res = fut.result()
                except Exception as e:
                    sym, tf = futs[fut]
                    logger.warning("Excepción en hilo para %s [%s]: %s", sym, tf, e)
                    continue
                if res is None:
                    continue
                symbol, timeframe, regime, metrics, df = res
                key = f"{symbol}|{timeframe}"
                now = time.monotonic()
                with self._lock:
                    self.last_regime[key] = regime
                    self.last_scan_time[key] = now
                    self.last_dataframes[key] = df
                
                # PERSISTENCIA PARA CROSS-PROCESS (Heatmap Resilience)
                if self.storage:
                    try:
                        state_data = {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "regime": regime.value,
                            "metrics": metrics,
                            "timestamp": datetime.now().isoformat()
                        }
                        self.storage.log_market_state(state_data)
                    except Exception as e:
                        logger.error(f"Error persistiendo estado de mercado para {key}: {e}")

                logger.info(
                    "Escáner %s [%s] -> %s (ADX=%.2f)",
                    symbol,
                    timeframe,
                    regime.value,
                    metrics.get("adx", 0) or 0,
                )

    def _adaptive_sleep(self) -> float:
        """Calcula sleep según CPU. Si CPU > límite, aumenta el tiempo entre escaneos."""
        base = self.base_sleep
        if not psutil:
            return base
        try:
            cpu = self.cpu_monitor.get_cpu_percent()
            if cpu <= self.cpu_limit_pct:
                return base
            excess = cpu - self.cpu_limit_pct
            # Aumentar sleep proporcional al exceso, cap por max_sleep_multiplier
            factor = 1.0 + min(excess / 20.0, self.max_sleep_multiplier - 1.0)
            t = base * factor
            logger.debug("CPU %.1f%% > %.1f%%, sleep aumentado a %.2fs", cpu, self.cpu_limit_pct, t)
            return t
        except Exception as e:
            logger.debug("Error en adaptive_sleep: %s", e)
            return base

    def run(self) -> None:
        """Bucle principal del escáner. Ejecutar en proceso o hilo dedicado."""
        self._running = True
        logger.info(
            "Escáner proactivo iniciado. Activos: %s. CPU límite: %.1f%%.",
            self.assets,
            self.cpu_limit_pct,
        )
        while self._running:
            # HOT-RELOAD: Verificar si scanner está habilitado en DB
            if self.storage:
                try:
                    modules_enabled = self.storage.get_global_modules_enabled()
                    if not modules_enabled.get("scanner", True):
                        logger.debug("[SCANNER] Módulo deshabilitado - esperando reactivación...")
                        time.sleep(10)  # Esperar 10s y verificar de nuevo
                        continue
                except Exception as e:
                    logger.warning(f"[SCANNER] Error verificando toggle: {e}")
            
            # HOT-RELOAD: Verificar cambios en timeframes configurados
            try:
                self._reload_timeframes_if_changed()
            except Exception as e:
                logger.warning(f"[SCANNER] Error reloading timeframes: {e}")
            
            # Módulo habilitado - ejecutar ciclo normal
            try:
                self._run_cycle()
            except Exception as e:
                logger.exception("Error en ciclo del escáner: %s", e)
            sleep_s = self._adaptive_sleep()
            deadline = time.monotonic() + sleep_s
            while self._running and time.monotonic() < deadline:
                time.sleep(0.2)

    def stop(self) -> None:
        """Detiene el bucle del escáner."""
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
                state = self.storage.get_system_state()
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
        Obtiene los últimos resultados del scanner con DataFrames incluidos.
        
        Returns:
            Dict con "symbol|timeframe" -> {"regime": MarketRegime, "df": DataFrame, "symbol": str, "timeframe": str}
        """
        with self._lock:
            results = {}
            for key in self.last_regime:
                # Parse key: "symbol|timeframe"
                if "|" in key:
                    symbol, timeframe = key.split("|", 1)
                else:
                    # Legacy support
                    symbol = key
                    timeframe = self.mt5_timeframe
                    
                results[key] = {
                    "regime": self.last_regime[key],
                    "df": self.last_dataframes.get(key),
                    "symbol": symbol,
                    "timeframe": timeframe
                }
            return results

    def get_status(self) -> Dict[str, Any]:
        """Estado actual: último régimen por símbolo, CPU, etc."""
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
        }
