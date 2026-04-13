"""
Aethelgard Trading System - Unified Launcher
=============================================

Comando único que inicia:
1. Servidor API (FastAPI/Uvicorn) - Backend + React UI
2. Motor de trading (Scanner + Orchestrator) - Lógica de negocio
3. EDGE Tuner - Auto-calibración

USO: python start.py
"""
import sys
import os

# Añadir el directorio raíz al path para importar módulos
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from data_vault.runtime_db_guard import install_runtime_sqlite_guard

# Runtime persistence enforcement: block new direct sqlite3.connect call sites.
install_runtime_sqlite_guard()

import asyncio
import logging
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
import webbrowser

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from core_brain.monitor import ClosingMonitor
from core_brain.edge_tuner import EdgeTuner
from core_brain.edge_monitor import EdgeMonitor
from core_brain.services.strategy_engine_factory import StrategyEngineFactory
from data_vault.storage import StorageManager
from data_vault.backup_manager import DatabaseBackupManager
from models.signal import ConnectorType

# Core Brain Imports
from core_brain.data_provider_manager import DataProviderManager
from core_brain.notificator import get_notifier
from core_brain.multi_timeframe_limiter import MultiTimeframeLimiter
from core_brain.coherence_monitor import CoherenceMonitor
from core_brain.strategy_gatekeeper import StrategyGatekeeper
from core_brain.signal_expiration_manager import SignalExpirationManager
from core_brain.regime import RegimeClassifier
from core_brain.trade_closure_listener import TradeClosureListener
from core_brain.position_manager import PositionManager

# Configurar logging
from logging.handlers import TimedRotatingFileHandler

# Asegurar carpeta de logs
Path("logs").mkdir(exist_ok=True)


def _rotate_stale_log(log_path: str = "logs/main.log") -> None:
    """
    Startup checkpoint: rotate log file if it belongs to a previous day.

    TimedRotatingFileHandler only rotates at midnight while the system
    is running. If the system is restarted days later, the old log would
    be appended to instead of rotated. This function closes that gap.
    """
    log_file = Path(log_path)
    if not log_file.exists() or log_file.stat().st_size == 0:
        return
    last_modified = datetime.fromtimestamp(log_file.stat().st_mtime)
    if last_modified.date() < datetime.now().date():
        suffix = last_modified.strftime("%Y-%m-%d")
        rotated = log_file.with_name(f"{log_file.name}.{suffix}")
        if not rotated.exists():
            log_file.rename(rotated)


_rotate_stale_log()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        TimedRotatingFileHandler(
            filename='logs/main.log',
            when='midnight',
            interval=1,
            backupCount=15,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# server_process global
server_process = None

_LOCK_PATH = Path("data_vault/aethelgard.lock")


def _acquire_singleton_lock(lock_path: Path = _LOCK_PATH) -> bool:
    """
    Create PID lockfile atomically. Returns False if another live instance is running.

    Uses open(path, 'x') — O_CREAT|O_EXCL at OS level — to eliminate the
    read→check→write race condition of the previous implementation.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Atomic exclusive creation: fails instantly if file already exists
        with open(lock_path, 'x') as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        # Lockfile exists — check whether the recorded PID is still alive
        try:
            existing_pid = int(lock_path.read_text().strip())
            import psutil
            if psutil.pid_exists(existing_pid) and existing_pid != os.getpid():
                logger.error(
                    "[SINGLETON] Otra instancia de Aethelgard ya está corriendo (PID %d). Abortando.",
                    existing_pid,
                )
                return False
            # Stale lock (PID dead) — remove and claim it
            lock_path.unlink(missing_ok=True)
            with open(lock_path, 'x') as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            # Another process won the race in the narrow window after unlink
            logger.error("[SINGLETON] Race condition: otra instancia ganó el lock. Abortando.")
            return False
        except (ValueError, ImportError, OSError):
            # Malformed lockfile or psutil unavailable — overwrite safely
            lock_path.write_text(str(os.getpid()))
            return True


def _release_singleton_lock(lock_path: Path = _LOCK_PATH) -> None:
    """Remove PID lockfile on clean shutdown."""
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _read_initial_capital(storage: "StorageManager") -> float:
    """Read account_balance from sys_config. Falls back to 10 000.0 with WARNING."""
    try:
        cfg = storage.get_sys_config()
        balance = cfg.get("account_balance", 0)
        if balance and float(balance) > 0:
            return float(balance)
    except Exception as exc:
        logger.warning("[CONFIG] No se pudo leer account_balance de sys_config: %s", exc)
    logger.warning("[CONFIG] account_balance no disponible — usando capital por defecto $10,000.00")
    return 10000.0


def _seed_risk_config(storage: "StorageManager") -> None:
    """Seed risk_settings and dynamic_params in sys_config if absent (idempotent).

    Only writes keys that do not yet exist, so user-modified values are never
    overwritten. Eliminates the [SSOT] Risk/dynamic config not in DB warning.
    HU 3.10 — Trace_ID: RISK-SEED-SSOT-2026-03-25
    """
    try:
        existing = storage.get_sys_config()
        updates: dict = {}
        if not existing.get("risk_settings"):
            updates["risk_settings"] = {
                "max_consecutive_losses": 3,
                "max_account_risk_pct": 5.0,
                "max_r_per_trade": 2.0,
            }
        if not existing.get("dynamic_params"):
            updates["dynamic_params"] = {
                "risk_per_trade": 0.005,
                "max_consecutive_losses": 3,
                "pilar3_min_trades": 5,
                "adx": None,
            }
        elif "pilar3_min_trades" not in existing.get("dynamic_params", {}):
            # Sub-key patch: dynamic_params exists but pre-dates HU 3.13
            updates["dynamic_params"] = {
                **existing["dynamic_params"],
                "pilar3_min_trades": 5,
            }
        if updates:
            storage.update_sys_config(updates)
            logger.info("[CONFIG] Risk config sembrada en sys_config: %s", list(updates.keys()))
    except Exception as exc:
        logger.warning("[CONFIG] No se pudo sembrar risk_config: %s", exc)


def _seed_backtest_config(storage: "StorageManager") -> None:
    """Seed backtest_config in sys_config if absent (idempotent).

    Sets cooldown_hours=1 so backtests run hourly instead of the hardcoded 24h
    default, unblocking the BACKTEST→SHADOW pipeline in development/staging.
    Only writes if the key is not already in the DB — user config is preserved.
    Trace_ID: FIX-BACKTEST-COOLDOWN-SEED-2026-03-25
    """
    try:
        existing = storage.get_sys_config()
        if not existing.get("backtest_config"):
            storage.update_sys_config({
                "backtest_config": {
                    "cooldown_hours": 1,
                    "min_trades_per_cluster": 15,
                    "bars_per_window": 120,
                    "bars_fetch_initial": 500,
                    "promotion_min_score": 0.75,
                }
            })
            logger.info("[CONFIG] backtest_config sembrado: cooldown_hours=1")
    except Exception as exc:
        logger.warning("[CONFIG] No se pudo sembrar backtest_config: %s", exc)


def _ensure_exec_capable_account(storage: "StorageManager") -> bool:
    """Ensure at least one enabled sys_broker_accounts row has supports_exec=1.

    Idempotent behavior:
    - If an execution-capable account already exists, no writes are performed.
    - Otherwise, creates/updates a deterministic system demo account seed.

    Returns:
        True if a seed account was created/updated, False otherwise.
    """
    try:
        accounts = storage.get_sys_broker_accounts(enabled_only=True)
        if any(bool(acc.get("supports_exec", 0)) for acc in accounts):
            return False

        seed_account_id = "SYS_EXEC_DEMO_AUTO"
        storage.save_broker_account(
            id=seed_account_id,
            broker_id="mt5",
            platform_id="mt5",
            account_name="System Demo Execution Seed",
            account_number="AUTO-DEMO-EXEC",
            account_type="demo",
            enabled=True,
        )

        storage.execute_update(
            """
            UPDATE sys_broker_accounts
            SET supports_exec = 1,
                supports_data = COALESCE(supports_data, 0),
                enabled = 1,
                updated_at = ?
            WHERE account_id = ?
            """,
            (datetime.now(), seed_account_id),
        )

        logger.warning(
            "[EXEC-SEED] No execution-capable account found. "
            "Created fallback demo account '%s' (supports_exec=1).",
            seed_account_id,
        )
        return True
    except Exception as exc:
        logger.error("[EXEC-SEED] Failed to ensure execution-capable account: %s", exc)
        return False


def _resolve_connector_type(provider_id: str) -> ConnectorType:
    """Map connector provider_id to known ConnectorType with generic fallback."""
    normalized = (provider_id or "").lower()
    if "mt5" in normalized or "metatrader" in normalized:
        return ConnectorType.METATRADER5
    if "paper" in normalized:
        return ConnectorType.PAPER
    if "fix" in normalized:
        return ConnectorType.FIX
    return ConnectorType.GENERIC


def _build_active_connectors(connectivity_orchestrator: object) -> dict[ConnectorType, object]:
    """Collect registered connectors from ConnectivityOrchestrator without broker hardcoding."""
    connectors = getattr(connectivity_orchestrator, "connectors", {})
    if not isinstance(connectors, dict):
        return {}

    resolved: dict[ConnectorType, object] = {}
    for connector in connectors.values():
        if not connector:
            continue
        provider_id = getattr(connector, "provider_id", connector.__class__.__name__)
        connector_type = _resolve_connector_type(str(provider_id))
        if connector_type not in resolved:
            resolved[connector_type] = connector

    return resolved


def _connect_registered_connectors(connectors: dict[ConnectorType, object]) -> dict[ConnectorType, bool]:
    """Attempt connector bootstrap without assuming specific broker implementations."""
    bootstrap_status: dict[ConnectorType, bool] = {}
    for connector_type, connector in connectors.items():
        if bool(getattr(connector, "is_connected", False)):
            bootstrap_status[connector_type] = True
            continue

        connect_fn = getattr(connector, "connect_blocking", None) or getattr(connector, "connect", None)
        if not callable(connect_fn):
            bootstrap_status[connector_type] = False
            continue

        try:
            bootstrap_status[connector_type] = bool(connect_fn())
        except Exception:
            bootstrap_status[connector_type] = False

    return bootstrap_status


def _bind_signal_factory_reconciliation_connector(
    signal_factory: object,
    active_provider: dict[str, object] | None,
) -> None:
    """Bind reconciliation connector using active provider descriptor without broker hardcoding."""
    connector = active_provider.get("instance") if isinstance(active_provider, dict) else None
    if not connector:
        return

    if hasattr(signal_factory, "set_reconciliation_connector"):
        signal_factory.set_reconciliation_connector(connector)

    balance_fn = getattr(connector, "get_account_balance", None)
    if callable(balance_fn):
        try:
            account_balance = balance_fn()
            provider_name = active_provider.get("name", "unknown")
            logger.info("   Balance obtenido: $%s (%s)", f"{account_balance:,.2f}", provider_name)
        except Exception as e:
            logger.warning("[WARN] No se pudo obtener balance del proveedor activo: %s", e)


# launch_dashboard eliminada - UI unificada en puerto 8000

def launch_server() -> None:
    """Lanza el servidor FastAPI (Uvicorn) en un proceso COMPLETAMENTE INDEPENDIENTE (detached)."""
    global server_process
    try:
        logger.info("[INFO] Iniciando Cerebro Aethelgard & UI Next-Gen (detached)...")
        # Verificar si la UI está compilada
        ui_dist = os.path.join(os.getcwd(), "ui", "dist")
        if not os.path.exists(ui_dist):
            logger.warning("[WARN] UI Next-Gen no compilada. Ejecutando build rápido...")
            try:
                subprocess.run(["npm", "run", "build"], cwd=os.path.join(os.getcwd(), "ui"), shell=True, check=True)
                logger.info("[OK] UI compilada correctamente.")
            except Exception as e:
                logger.error(f"[ERROR] Falló la compilación de la UI: {e}. Se servirá solo la API.")

        # Ejecutar uvicorn como módulo en subproceso detached
        _uvicorn_log = open("logs/uvicorn_debug.log", "w")
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "core_brain.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
            stdout=_uvicorn_log,
            stderr=_uvicorn_log,
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        logger.info("[OK] Cerebro lanzado en proceso independiente")
        logger.info("[LINK] Interfaz Principal: http://localhost:8000")
        logger.info("[LINK] Documentación API: http://localhost:8000/docs")
        logger.info("[LINK] Health SRE: http://localhost:8000/health")
        # NO esperar - continuar inmediatamente
        
    except Exception as e:
        logger.error(f"[ERROR] Error al iniciar servidor API: {e}")

async def main() -> None:
    """
    Lanzador unificado de Aethelgard.
    Inicializa motor de trading + dashboard.
    """
    logger.info("=" * 70)
    logger.info("[START] AETHELGARD TRADING SYSTEM - UNIFIED LAUNCHER")
    logger.info("=" * 70)

    # Crear directorios necesarios
    Path("logs").mkdir(exist_ok=True)
    Path("data_vault").mkdir(exist_ok=True)

    # P9 — Singleton guard: abortar si ya hay una instancia corriendo
    if not _acquire_singleton_lock():
        logger.error("[ABORT] Ya existe una instancia activa. Terminar la instancia anterior primero.")
        return

    try:
        # 1. Storage Manager (SSOT - Regla 14)
        logger.info("[INIT] Inicializando Storage Manager...")
        storage = StorageManager()

        # 1.1 DB Backup Manager (periodic, configurable via dynamic_params.database_backup)
        backup_manager = DatabaseBackupManager(storage=storage, poll_seconds=30)
        backup_manager.start()
        
        # 1.5. Configuración SSOT (Regla 14)
        # Cargar configuraciones directamente desde DB (sin auto-bootstrap JSON en runtime)
        system_state = storage.get_sys_config()
        global_config = system_state.get("global_config") or {}
        dynamic_params = storage.get_dynamic_params()

        # === FUNCIONES AUXILIARES EDGE ===
        async def run_edge_tuner_loop(edge_tuner: EdgeTuner, signal_factory: SignalFactory) -> None:
            """
            Tarea asíncrona que ejecuta el EDGE Tuner cada hora.
            Ajusta parámetros basándose en resultados de trades.
            """
            tuner_logger = logging.getLogger(__name__)
            
            while True:
                try:
                    # Esperar 1 hora
                    await asyncio.sleep(3600)  # 3600 segundos = 1 hora
                    
                    tuner_logger.info("[EDGE] Ejecutando ajuste EDGE de parámetros...")
                    adjustment = edge_tuner.adjust_parameters()
                    
                    if adjustment and not adjustment.get("skipped_reason"):
                        tuner_logger.info(f"[OK] Ajuste EDGE completado: {adjustment.get('trigger')}")
                        # En el nuevo SignalFactory (DI), los parámetros se cargan vía StorageManager
                        # pero si la estrategia es inyectada, puede que necesitemos avisar.
                        # El factory tiene su propio _load_parameters.
                        signal_factory._load_parameters()
                        tuner_logger.info("[INFO] Parámetros recargados en SignalFactory")
                    else:
                        reason = adjustment.get("skipped_reason") if adjustment else "unknown"
                        tuner_logger.info(f"[INFO] Sin ajustes: {reason}")
                        
                except Exception as e:
                    tuner_logger.error(f"[ERROR] Error en EDGE Tuner: {e}", exc_info=True)
                    # Continuar ejecutándose a pesar del error
                    await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar

        # 2. Notification Service (Internal persistency)
        logger.info("[INIT] Inicializando Notification Service...")
        from core_brain.notification_service import NotificationService
        notification_service = NotificationService(storage)

        # 3. Risk Manager (Regla 1 - DI)
        logger.info("[INIT]  Inicializando Risk Manager...")
        from core_brain.position_size_monitor import PositionSizeMonitor
        risk_monitor = PositionSizeMonitor(
            max_consecutive_failures=3,
            circuit_breaker_timeout=300
        )
        
        from core_brain.instrument_manager import InstrumentManager
        instrument_manager = InstrumentManager(storage=storage)
        
        # === SÍMBOLOS A MONITOREAR - LEER DE BD (SSOT) ===
        # Obtener TODOS los símbolos habilitados sin filtrado por mercado
        # (Agnóstico - respeta lo que esté activo en la BD, sin discriminar FOREX vs CRYPTO vs METALS)
        enabled_symbols = instrument_manager.get_enabled_symbols(market=None)
        if enabled_symbols:
            symbols = enabled_symbols
            enabled_by_market = {}
            for sym in symbols:
                cfg = instrument_manager.get_config(sym)
                if cfg:
                    market = cfg.category
                    if market not in enabled_by_market:
                        enabled_by_market[market] = []
                    enabled_by_market[market].append(sym)
            logger.info(f"   Símbolos configurados (desde DB): {len(symbols)} instrumentos habilitados")
            for market, syms in sorted(enabled_by_market.items()):
                logger.info(f"      - {market}: {len(syms)} ({', '.join(sorted(syms)[:5])}{'...' if len(syms) > 5 else ''})")
        else:
            # Si no hay NADA habilitado en la BD, abortar con mensaje claro
            logger.critical("[CRITICAL] No hay símbolos habilitados en la BD. Configura al menos un instrumento en Settings.")
            raise RuntimeError("No enabled symbols found in database. Cannot start trading.")
        
        _seed_risk_config(storage)
        _seed_backtest_config(storage)
        _ensure_exec_capable_account(storage)
        initial_capital = _read_initial_capital(storage)
        risk_manager = RiskManager(
            storage=storage,
            initial_capital=initial_capital,
            instrument_manager=instrument_manager,
            monitor=risk_monitor
        )
        logger.info(f"   Capital: ${risk_manager.capital:,.2f}")
        logger.info(f"   Riesgo por trade (SST): {risk_manager.risk_per_trade:.1%}")
        
        # 3. Connectors & Data Provider (Unificación de Conexión)
        # ----------------------------------------------------------------
        
        # A) Inicializar Data Provider Manager (SSOT providers from DB)
        logger.info("[INIT] Inicializando Data Provider Manager (DI)...")
        provider_manager = DataProviderManager(storage=storage)

        # B) Inicializar ConnectivityOrchestrator y Connectors Dinámicos (SSOT)
        logger.info("[INIT] Inicializando ConnectivityOrchestrator y conectores desde BD...")
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
        orchestrator = ConnectivityOrchestrator()
        orchestrator.set_storage(storage)

        # C) Inyección de Dependencia: Registrar conectores por proveedor activo de DB
        for provider_info in provider_manager.get_active_providers():
            provider_name = str(provider_info.get("name", "")).strip().lower()
            if not provider_name:
                continue
            connector = orchestrator.get_connector(provider_name)
            if connector:
                provider_manager.register_provider_instance(provider_name, connector)
        
        # Fallback: Registrar conectores preexistentes por provider_id (compatibilidad)
        for connector in orchestrator.connectors.values():
            if not connector:
                continue
            provider_id = str(getattr(connector, "provider_id", "")).lower()
            if not provider_id:
                continue
            provider_manager.register_provider_instance(provider_id, connector)
        logger.info("[DI] Conectores registrados en DataProviderManager desde DB")

        # D) Inicializar Scanner Engine (usando el provider_manager configurado)
        logger.info("[INIT] Inicializando Scanner Engine...")
        scanner = ScannerEngine(
            assets=symbols,
            data_provider=provider_manager,
            config_data=global_config, # Inyectar desde DB (SSOT)
            scan_mode="STANDARD",
            storage=storage
        )
        
        # 5. Signal Factory - FASE DI (Regla 1)
        logger.info("[INIT] Inicializando Signal Factory (DI)...")
        from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
        from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
        
        confluence_config = dynamic_params.get("confluence", {})
        confluence_analyzer = MultiTimeframeConfluenceAnalyzer(
            storage=storage,
            enabled=confluence_config.get("enabled", True)
        )
        
        trifecta_analyzer = TrifectaAnalyzer(
            storage=storage,
            config_data=global_config, # Inyectar desde DB (SSOT)
            auto_enable_tfs=True
        )
        
        # NOTE: SignalFactory will be created AFTER sensors are initialized in MainOrchestrator
        # See OPTION 4 implementation: Sensors first, then factory creation
        signal_factory = None  # Will be set later
        
        # 6. Order Executor - FASE DI (Regla 1)

        logger.info("[INIT] Inicializando Order Executor (DI)...")
        
        active_provider = provider_manager.get_connected_active_provider()
        multi_tf_limiter = MultiTimeframeLimiter(
            storage=storage,
            config=dynamic_params,
            connector=active_provider["instance"] if active_provider else None
        )
        
        # Construir diccionario de conectores activos sin suposición nominal de broker
        active_connectors = _build_active_connectors(orchestrator)
        connector_bootstrap = _connect_registered_connectors(active_connectors)
        connected_count = sum(1 for status in connector_bootstrap.values() if status)
        logger.info("[CONNECT] Bootstrap conectores: %d/%d conectados", connected_count, len(active_connectors))

        active_provider = provider_manager.get_connected_active_provider()
        if active_provider:
            logger.info("[PROVIDER] Proveedor de datos activo (DB): %s", active_provider["name"])
        else:
            logger.warning("[PROVIDER] No hay proveedor activo conectado desde DB")
            
        order_executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            multi_tf_limiter=multi_tf_limiter,
            notificator=get_notifier(),
            notification_service=notification_service,
            connectors=active_connectors
        )
        
        # 7. Coherence Monitor (DI)
        logger.info("[INIT] Inicializando Coherence Monitor...")
        coherence_monitor = CoherenceMonitor(storage=storage)
        
        # 7.1 Signal Expiration Manager (DI)
        logger.info("[INIT] Inicializando Signal Expiration Manager...")
        expiration_manager = SignalExpirationManager(storage=storage)
        
        # 7.2 Regime Classifier (DI)
        logger.info("[INIT] Inicializando Regime Classifier...")
        regime_classifier = RegimeClassifier(storage=storage)
        
        # 7.3 Edge Tuner (DI)
        logger.info("[INIT] Inicializando Edge Tuner...")
        edge_tuner = EdgeTuner(storage=storage) 
        
        # 7.4 Trade Closure Listener (DI)
        logger.info("[INIT] Inicializando Trade Closure Listener...")
        trade_closure_listener = TradeClosureListener(
            storage=storage,
            risk_manager=risk_manager,
            edge_tuner=edge_tuner
        )
        
        # 7.5 Position Manager (DI)
        logger.info("[INIT] Inicializando Position Manager...")
        best_exec_connector = provider_manager.get_best_provider()
        position_manager = PositionManager(
            storage=storage,
            connector=best_exec_connector,
            regime_classifier=regime_classifier,
            config=dynamic_params.get("position_management", {})
        )
        
        # 8. Main Orchestrator (Unified DI) - OPTION 4 Implementation
        # Explicit sensor initialization BEFORE SignalFactory creation
        logger.info("[INIT] Inicializando Main Orchestrator (DI/SSOT)...")
        from core_brain.server import broadcast_thought
        
        # STEP 1: Create MainOrchestrator WITHOUT signal_factory (signal_factory=None)
        # This ensures __init__ doesn't try to load strategies yet
        # Use agnóstico connectors dict instead of hardcoded mt5_connector
        strategy_gatekeeper = StrategyGatekeeper(storage=storage)
        orchestrator = MainOrchestrator(
            scanner=scanner,
            signal_factory=None,  # OPTION 4: Defer factory injection
            risk_manager=risk_manager,
            executor=order_executor,
            storage=storage,
            position_manager=position_manager,
            trade_closure_listener=trade_closure_listener,
            coherence_monitor=coherence_monitor,
            expiration_manager=expiration_manager,
            regime_classifier=regime_classifier,
            strategy_gatekeeper=strategy_gatekeeper,
            thought_callback=broadcast_thought
        )
        
        # STEP 2: Initialize sensors explicitly (BEFORE SignalFactory creation)
        logger.info("[INIT] Inicializando sensores (fase de DI explícita)...")
        available_sensors = orchestrator.initialize_sensors()
        logger.info(f"[INIT] ✓ Sensores inicializados: {list(available_sensors.keys())}")
        
        # STEP 3: Create SignalFactory WITH populated sensors
        logger.info("[INIT] Creando SignalFactory con sensores disponibles...")
        from core_brain.services.strategy_engine_factory import StrategyEngineFactory
        
        try:
            # Load strategies with sensors now available
            # Pasar user_id desde storage (SSOT) para multi-tenancy (Dominio 01, 08)
            strategy_factory = StrategyEngineFactory(
                storage=storage,
                config=dynamic_params,
                available_sensors=available_sensors,  # NOW POPULATED!
                user_id=storage.user_id  # Multi-user context for strategy initialization
            )
            active_engines = strategy_factory.instantiate_all_sys_strategies()
            # Mantener coherencia entre filtro pre-tick y snapshot analyze() con metadata SSOT.
            strategy_specs = storage.get_all_sys_strategies()
            strategy_gatekeeper.sync_from_strategy_specs(strategy_specs)
            logger.info(f"[INIT] ✓ {len(active_engines)} estrategias cargadas (con sensores listos)")
        except Exception as e:
            logger.warning(f"[INIT] Error cargando estrategias: {e}. SignalFactory operará con Dict vacío")
            active_engines = {}
        
        signal_factory = SignalFactory(
            storage_manager=storage,
            strategy_engines=active_engines,
            confluence_analyzer=confluence_analyzer,
            trifecta_analyzer=trifecta_analyzer,
            notification_service=notification_service,
            instrument_manager=instrument_manager,
        )
        
        # STEP 4: Inject SignalFactory into orchestrator (explicit DI)
        logger.info("[INIT] Inyectando SignalFactory en Orchestrator...")
        orchestrator.set_signal_factory(signal_factory)
        logger.info("[INIT] ✓ Orquestador listo con SignalFactory")
        
        # STEP 4.5: Bootstrap SHADOW pool (auto-create instances for Darwinian selection)
        logger.info("[INIT] Inicializando SHADOW pool (instancias automáticas)...")
        if active_engines:
            shadow_stats = await orchestrator.initialize_shadow_pool(
                strategy_engines=active_engines,
                account_id="DEMO_MT5_001",
                variations_per_strategy=2
            )
            logger.info(f"[INIT] ✓ SHADOW pool: {shadow_stats['created']} instancias, {shadow_stats['skipped']} skipped")
        else:
            logger.warning("[INIT] ⚠️  No strategies loaded, skipping SHADOW pool initialization")
        
        # 8.6 Operational Edge Monitor (auto-auditoría de invariantes de negocio)
        logger.info("[INIT] Inicializando Operational Edge Monitor (auto-auditoría)...")

        # Escribir heartbeat del orchestrator ANTES de iniciar OEM.
        # Sin esto, el primer ciclo del OEM ve el timestamp del arranque anterior
        # (potencialmente horas atrás si el sistema estuvo inactivo) y emite FAIL
        # aunque el orchestrator esté a punto de arrancar.
        storage.update_module_heartbeat("orchestrator")
        logger.info("[INIT] Heartbeat inicial del orchestrator escrito (previene falso FAIL en OEM)")

        from core_brain.operational_edge_monitor import OperationalEdgeMonitor
        from data_vault.shadow_db import create_shadow_manager

        _shadow_storage_for_oem = None
        try:
            _shadow_storage_for_oem = create_shadow_manager(storage)
            logger.info("[OEM] shadow_storage inyectado correctamente")
        except Exception as _exc:
            logger.warning("[OEM] Error creando shadow_storage: %s — check shadow_sync omitido", _exc)

        oem = OperationalEdgeMonitor(
            storage=storage,
            shadow_storage=_shadow_storage_for_oem,
            interval_seconds=300,
        )
        oem.start()

        from core_brain.server import set_oem_instance
        set_oem_instance(oem)
        logger.info("[OK] Operational Edge Monitor activo (10 invariantes de negocio, cada 5 min)")

        # 9. Autonomous Health Service (EDGE Autonomy)
        logger.info("[INIT] Inicializando Servicio de Salud Autónomo...")
        from core_brain.health_service import AutonomousHealthService
        health_service = AutonomousHealthService(storage=storage)
        health_task = asyncio.create_task(health_service.start())
        logger.info("[OK] Salud Autónoma activa")
        
        _bind_signal_factory_reconciliation_connector(signal_factory, active_provider)
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("[OK] SISTEMA COMPLETO INICIADO")
        logger.info("=" * 70)
        logger.info("")
        
        # Iniciar Servidor API en hilo separado
        server_thread = threading.Thread(target=launch_server,daemon=True)
        server_thread.start()
        
        # OPTION A (11-Mar-2026): Scanner is pure executor, no autonomous thread
        # MainOrchestrator calls scanner.execute_scan() when it decides timing
        # REMOVED: scanner_thread = threading.Thread(target=scanner.run, daemon=True)
        logger.info("[INFO] Scanner initialized as pure executor (OPTION A - MainOrchestrator orchestrates)")
        
        # Iniciar Closing Monitor en tarea asíncrona
        logger.info("[INFO] Inicializando Closing Monitor...")
        closing_monitor = ClosingMonitor(
            storage=storage,
            connectors=active_connectors,
            interval_seconds=60
        )
        monitor_task = asyncio.create_task(closing_monitor.start())
        logger.info("[OK] Closing Monitor activo (Feedback Loop)")
        
        # Iniciar EDGE Monitor (inject connectors dict — conector-agnóstico, HU 10.5)
        logger.info("[INFO] Iniciando EDGE Monitor...")
        edge_monitor = EdgeMonitor(
            storage=storage,
            connectors=active_connectors,
            trade_listener=trade_closure_listener
        )
        edge_monitor.start()
        logger.info("[OK] EDGE Monitor activo (Observabilidad + Reconciliación Automática)")
        
        logger.info("")
        logger.info("   -> [PRINCIPAL] Command Center Next-Gen: http://localhost:8000")
        logger.info("")
        logger.info("[STOP] Presiona Ctrl+C para detener todo el ecosistema")
        
        # Crear tarea asíncrona del EDGE Tuner
        tuner_task = asyncio.create_task(run_edge_tuner_loop(edge_tuner, signal_factory))
        logger.info("[AUTO] EDGE Tuner: ajustes automáticos cada 1 hora")
        
        # Ejecutar loop principal
        await orchestrator.run()
        
    except KeyboardInterrupt:
        logger.info("\n[STOP]  Deteniendo sistema...")
        scanner.stop()
        if 'closing_monitor' in locals():
            await closing_monitor.stop()
        if 'backup_manager' in locals():
            backup_manager.stop()
        # Cleanup
    except Exception as e:
        logger.error(f"[FATAL] Error crítico: {e}", exc_info=True)
        raise
    finally:
        if 'backup_manager' in locals():
            backup_manager.stop()
        if server_process and server_process.poll() is None:
            server_process.terminate()
        _release_singleton_lock()
        logger.info("[STOP] Sistema detenido completamente.")


if __name__ == "__main__":
    asyncio.run(main())
