"""
Escáner Proactivo Multihilo.
Orquestador que escanea una lista de activos, clasifica régimen por activo en hilos separados,
controla recursos (CPU) y prioriza TREND (1s) vs RANGE (10s).
Agnóstico de plataforma: recibe un DataProvider inyectado (ej. MT5).
"""
from __future__ import annotations

import json
import logging
import threading
import time
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


def _load_config(config_path: str = "config/config.json") -> dict:
    p = Path(config_path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("No se pudo cargar %s: %s. Usando defaults.", config_path, e)
        return {}


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
        data_provider: DataProvider,
        config_path: str = "config/config.json",
        regime_config_path: Optional[str] = None,
        scan_mode: str = "STANDARD",  # Nuevo parámetro para el modo de escaneo
    ):
        self.assets = list(assets) if assets else []
        self.provider = data_provider
        self.config_path = config_path
        cfg = _load_config(config_path)
        sc = cfg.get("scanner", {})

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
        if timeframes_config:
            self.active_timeframes = [tf["timeframe"] for tf in timeframes_config if tf.get("enabled", True)]
        else:
            # Fallback to legacy single timeframe
            self.active_timeframes = [self.mt5_timeframe]
        
        logger.info(f"Active timeframes for scanning: {self.active_timeframes}")
        rp = regime_config_path or sc.get("config_path", "config/dynamic_params.json")

        self.cpu_monitor = CPUMonitor(cpu_limit_pct=self.cpu_limit_pct)
        # Multi-timeframe support: key = "symbol|timeframe"
        self.classifiers: Dict[str, RegimeClassifier] = {}
        self.last_regime: Dict[str, MarketRegime] = {}
        self.last_scan_time: Dict[str, float] = {}
        self.last_dataframes: Dict[str, Any] = {}  # Almacenar últimos DataFrames
        self._lock = threading.Lock()
        self._running = False
        
        # Calcular max_workers basado en el modo de escaneo y el número de activos
        base_workers = min(32, (len(self.assets) or 1) + 4)
        self._max_workers = int(base_workers * selected_mode["max_workers_multiplier"])
        
        logger.info("ScannerEngine inicializado en modo %s con CPU límite %.1f%% y %d workers.", self.scan_mode, self.cpu_limit_pct, self._max_workers)

        # Initialize classifiers for each (symbol, timeframe) combination
        for s in self.assets:
            for tf in self.active_timeframes:
                key = f"{s}|{tf}"
                self.classifiers[key] = RegimeClassifier(config_path=rp)
                self.last_regime[key] = MarketRegime.NORMAL
                self.last_scan_time[key] = 0.0

    def _sleep_for_regime(self, regime: MarketRegime) -> float:
        if regime == MarketRegime.TREND:
            return self.sleep_trend
        if regime == MarketRegime.CRASH:
            return self.sleep_crash
        if regime == MarketRegime.RANGE:
            return self.sleep_range
        return self.sleep_neutral

    def _symbols_to_scan(self) -> List[Tuple[str, str]]:
        """Priorización: TREND/CRASH cada 1s, RANGE/NORMAL cada 5–10s.
        
        Returns:
            List of (symbol, timeframe) tuples ready to scan
        """
        now = time.monotonic()
        out = []
        with self._lock:
            for s in self.assets:
                for tf in self.active_timeframes:
                    key = f"{s}|{tf}"
                    last = self.last_scan_time.get(key, 0.0)
                    regime = self.last_regime.get(key, MarketRegime.NORMAL)
                    interval = self._sleep_for_regime(regime)
                    if now - last >= interval:
                        out.append((s, tf))
        return out

    def _scan_one(self, symbol: str, timeframe: str) -> Optional[Tuple[str, str, MarketRegime, Dict, Any]]:
        """Ejecuta RegimeClassifier para un símbolo y timeframe específico.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe to scan (e.g., "M5", "H1")
            
        Returns:
            Tuple of (symbol, timeframe, regime, metrics, dataframe) or None
        """
        try:
            df = self.provider.fetch_ohlc(
                symbol,
                timeframe=timeframe,
                count=self.mt5_bars_count,
                only_system=True
            )
            if df is None or (hasattr(df, "empty") and df.empty):
                logger.debug("Sin datos OHLC para %s en %s", symbol, timeframe)
                return None

            key = f"{symbol}|{timeframe}"
            cl = self.classifiers[key]
            cl.load_ohlc(df)
            regime = cl.classify()
            metrics = cl.get_metrics()
            return (symbol, timeframe, regime, metrics, df)
        except Exception as e:
            logger.warning("Error escaneando %s [%s]: %s", symbol, timeframe, e)
            return None

    def _run_cycle(self) -> None:
        to_scan = self._symbols_to_scan()
        if not to_scan:
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
