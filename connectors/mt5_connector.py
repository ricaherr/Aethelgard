"""
MT5 Connector - Production-Ready Integration
Simplified connector for OrderExecutor and ClosingMonitor
ARCHITECTURE: Single source of truth = DATABASE (no JSON files)
"""
import logging
import threading
import time
from enum import Enum
import pandas as pd
from typing import Optional, Dict, List, Any, Union, TYPE_CHECKING
from datetime import datetime, timedelta

if TYPE_CHECKING:
    import MetaTrader5 as mt5

try:
    import MetaTrader5 as _mt5
    mt5: Any = _mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5: Any = None
    logging.warning("MetaTrader5 library not installed. MT5 connector disabled.")

from models.signal import Signal, SignalType
from data_vault.storage import StorageManager
from models.broker_event import BrokerTradeClosedEvent, TradeResult, BrokerEvent
from utils.market_ops import normalize_price, normalize_volume

logger = logging.getLogger(__name__)

# MT5 Timeframe Map for Data Provider compatibility
if MT5_AVAILABLE and mt5:
    TIMEFRAME_MAP = {
        "M1": getattr(mt5, "TIMEFRAME_M1", 1),
        "M5": getattr(mt5, "TIMEFRAME_M5", 5),
        "M15": getattr(mt5, "TIMEFRAME_M15", 15),
        "M30": getattr(mt5, "TIMEFRAME_M30", 30),
        "H1": getattr(mt5, "TIMEFRAME_H1", 16385),
        "H4": getattr(mt5, "TIMEFRAME_H4", 16388),
        "D1": getattr(mt5, "TIMEFRAME_D1", 16408),
        "W1": getattr(mt5, "TIMEFRAME_W1", 32769),
        "MN1": getattr(mt5, "TIMEFRAME_MN1", 49153),
    }
else:
    TIMEFRAME_MAP = {}


class ConnectionState(Enum):
    """MT5 Connection states for non-blocking startup"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


from connectors.base_connector import BaseConnector

class MT5Connector(BaseConnector):
    """
    Production MT5 Connector for Aethelgard

    Features:
    - Auto-loads configuration from database (broker_accounts + broker_credentials)
    - Validates demo account before executing
    - Implements standard connector interface
    - Thread-safe operations
    - Non-blocking connection with timeout and retry
    """

    @staticmethod
    def shutdown_broker() -> bool:
        """
        Cierra conexiones MT5 de forma limpia.
        Solo actúa si el proceso de MetaTrader ya está en ejecución para evitar abrirlo.
        """
        if not MT5_AVAILABLE:
            return False
            
        try:
            # 1. Verificar si el proceso está activo para evitar abrir MT5 si está cerrado
            import psutil
            mt5_procs = ["terminal64.exe", "terminal.exe", "metatrader.exe"]
            is_running = False
            
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'].lower() in mt5_procs:
                        is_running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not is_running:
                # Si no está corriendo, no hay nada que cerrar
                return False

            # 2. Solo si está corriendo, intentar inicializar para enviar el comando shutdown
            import MetaTrader5 as mt5_internal
            # initialize() sin argumentos intenta conectarse a la terminal activa
            if mt5_internal.initialize():
                mt5_internal.shutdown()
                return True
            return False
        except Exception as e:
            # Fallback defensivo: si psutil falla, mejor no arriesgarse a abrir MT5
            return False

    def __init__(self, storage: Optional[StorageManager] = None, account_id: Optional[str] = None):
        """
        Initialize MT5 Connector

        Args:
            storage: Optional StorageManager instance
            account_id: Optional account ID to use. If None, uses first enabled MT5 account from DB
        """
        if not MT5_AVAILABLE:
            raise ImportError("MetaTrader5 library not installed. Run: pip install MetaTrader5")

        self.storage = storage or StorageManager()
        self.account_id = account_id
        self.config = self._load_config_from_db()
        self.is_connected = False
        self.is_demo = False
        self.magic_number = 234000  # Aethelgard magic number

        # Connection state management
        self.connection_state = ConnectionState.DISCONNECTED
        self.connection_thread = None
        self.retry_timer = None
        self.last_attempt = 0
        
        # Available symbols cache (auto-discovery)
        self.available_symbols = set()
        self.last_error = None

        logger.info(f"[INSTANCE {id(self)}] MT5Connector initialized from database. Config enabled: {self.config.get('enabled', False)}, Account: {self.config.get('login', 'N/A')}")
    
    def _load_config_from_db(self) -> Dict:
        """
        Load MT5 configuration from DATABASE (single source of truth)
        
        Returns:
            Dict with 'enabled', 'login', 'server', 'password', 'account_id'
        """
        try:
            # Get all MT5 accounts
            all_accounts = self.storage.get_broker_accounts()
            mt5_accounts = [acc for acc in all_accounts if acc.get('platform_id') == 'mt5' and acc.get('enabled', True)]
            
            if not mt5_accounts:
                logger.warning("No MT5 accounts found in database. MT5 connector disabled.")
                return {'enabled': False}
            
            # Sort accounts by updated_at DESC (prefer most recently modified = likely active)
            mt5_accounts.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
            
            # Select account (by ID or first enabled)
            account = None
            if self.account_id:
                account = next((acc for acc in mt5_accounts if acc['account_id'] == self.account_id), None)
                if not account:
                    logger.error(f"MT5 account {self.account_id} not found in database")
                    return {'enabled': False}
            else:
                account = mt5_accounts[0]  # Use first enabled account (now sorted)
                if len(mt5_accounts) > 1:
                    logger.info(f"Multiple enabled MT5 accounts found. Selected most recent: {account.get('account_name')} ({account.get('account_number')})")
                    logger.debug(f"Candidates: {[a.get('account_name') for a in mt5_accounts]}")
            
            # Store account ID for later use
            self.account_id = account['account_id']
            
            # Get credentials
            credentials = self.storage.get_credentials(self.account_id)
            
            if not credentials or not credentials.get('password'):
                logger.error(f"No credentials found for MT5 account {self.account_id}")
                return {'enabled': False}
            
            config = {
                'enabled': True,
                'login': account.get('login') or account.get('account_number'),
                'server': account.get('server'),
                'password': credentials['password'],
                'account_id': self.account_id,
                'account_name': account.get('account_name'),
                'account_type': account.get('account_type')
            }
            
            logger.info(f"Loaded MT5 config from DB: Account '{config['account_name']}' (Login: {config['login']})")
            return config
            
        except Exception as e:
            logger.error(f"Error loading MT5 config from database: {e}", exc_info=True)
            return {'enabled': False}
    
    def start(self) -> None:
        """
        Start MT5 connection in background thread.
        Call this after system initialization is complete.
        """
        logger.info(f"[INSTANCE {id(self)}] [START] MT5Connector.start() called. Config enabled: {self.config.get('enabled', False)}, Connection state: {self.connection_state}")
        
        if not self.config.get('enabled', False):
            logger.warning("❌ MT5 connector is DISABLED in config - not starting connection")
            logger.warning(f"   Config keys: {list(self.config.keys())}")
            return
            
        if self.connection_state != ConnectionState.DISCONNECTED:
            logger.info(f"[WARNING]  MT5 connection already started or in progress (state: {self.connection_state})")
            return
            
        if self.config.get('enabled', False):
            logger.info("[START] Creating background thread for MT5 connection...")
        
        # Start connection in background thread
        self.connection_thread = threading.Thread(
            target=self._connect_background,
            name="MT5-Background-Connector",
            daemon=True
        )
        self.connection_thread.start()
        logger.info("[OK] Background thread launched successfully")
    
    def _connect_background(self) -> None:
        """
        Background connection loop with retries.
        Runs indefinitely until connected or system shutdown.
        """
        logger.info("[THREAD] Background connection thread started (daemon mode)")
        
        while True:
            try:
                if self.connection_state == ConnectionState.CONNECTED:
                    # Already connected, just wait
                    time.sleep(30)
                    continue
                    
                self.connection_state = ConnectionState.CONNECTING
                self.last_attempt = time.time()
                self.connection_state = ConnectionState.CONNECTING
                self.last_attempt = time.time()
                
                logger.info("[CONNECT] [BACKGROUND] Attempting MT5 connection...")
                logger.info(f"   Current state: {self.connection_state}, Available symbols: {len(self.available_symbols)}")
                
                # Try to connect with timeout
                success = self._connect_sync_once()
                
                if success:
                    logger.info(f"[OK] [BACKGROUND] MT5 CONNECTED! Symbols loaded: {len(self.available_symbols)}")
                    return  # Exit loop when connected
                else:
                    logger.error("[ERROR] [BACKGROUND] MT5 connection FAILED (_connect_sync_once returned False)")
                    logger.warning("[WARNING]  [BACKGROUND] Retrying in 30 seconds...")
                    self.connection_state = ConnectionState.FAILED
                    time.sleep(30)
                
            except Exception as e:
                logger.error(f"[CRITICAL] [BACKGROUND] EXCEPTION in connection thread: {e}", exc_info=True)
                self.connection_state = ConnectionState.FAILED
                time.sleep(30)
    
    def _connect_sync_once(self) -> bool:
        """
        Single synchronous connection attempt.
        Returns True if successful, False otherwise.
        """
        try:
            if not self._initialize_mt5():
                return False
                
            if not self._validate_credentials():
                return False
                
            if not self._perform_mt5_login():
                return False
                
            if not self._verify_demo_account():
                return False
                
            # Auto-discovery: Load available symbols from broker (CRITICAL for auto-filter)
            self._load_available_symbols()
                
            self._log_connection_success()
            return True
            
        except Exception as e:
            logger.error(f"Error in MT5 connection attempt: {e}")
            return False

    def _initialize_mt5(self) -> bool:
        """Initialize MT5 terminal using dynamic path from config"""
        import json
        from pathlib import Path
        
        logger.info("[VERBOSE] _initialize_mt5() started")
        
        terminal_path = None
        auto_start = True
        
        # Intentar cargar desde config.json
        try:
            config_file = Path("config/config.json")
            if config_file.exists():
                with open(config_file, "r") as f:
                    global_config = json.load(f)
                    mt5_settings = global_config.get("connectors", {}).get("mt5", {})
                    terminal_path = mt5_settings.get("terminal_path")
                    auto_start = mt5_settings.get("auto_start", True)
                    logger.info(f"[VERBOSE] Terminal path from config: {terminal_path}")
        except Exception as e:
            logger.error(f"Error reading terminal_path from config.json: {e}")

        # Fallback hardcoded (mantenemos el anterior como último recurso)
        if not terminal_path:
            terminal_path = r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe"
            logger.warning(f"No terminal_path found in config. Using fallback: {terminal_path}")

        logger.info(f"[VERBOSE] Calling mt5.initialize(path='{terminal_path}')...")
        
        # Check if MT5 already initialized
        try:
            existing_version = mt5.version()
            if existing_version:
                logger.info(f"[VERBOSE] MT5 already initialized: version {existing_version}")
        except:
            logger.info("[VERBOSE] MT5 not yet initialized")
        
        if not mt5.initialize(path=terminal_path):
            error = mt5.last_error()
            logger.error(f"[VERBOSE] [ERROR] mt5.initialize() FAILED: {error}")
            logger.error(f"[VERBOSE] Terminal path attempted: {terminal_path}")
            return False
        
        logger.info(f"[VERBOSE] [OK] mt5.initialize() SUCCESS")
        return True

    def _validate_credentials(self) -> bool:
        """Validate that all required credentials are present"""
        logger.info("[VERBOSE] _validate_credentials() started")
        
        login = self.config.get('login')
        password = self.config.get('password')
        server = self.config.get('server')
        
        logger.info(f"[VERBOSE] Credentials check: login={bool(login)}, password={bool(password)} (len={len(str(password)) if password else 0}), server={bool(server)}")
        
        if not login or not password or not server:
            logger.error(f"[VERBOSE] [ERROR] Incomplete credentials: login={login}, server={server}")
            return False
        
        logger.info("[VERBOSE] [OK] Credentials validated")
        return True

    def _check_shared_session(self, target_login: Union[int, str], target_server: str) -> bool:
        """
        Check if current terminal session already matches target account.
        
        Args:
            target_login: Account number to check
            target_server: Broker server name
            
        Returns:
            True if already connected to target account
        """
        if not MT5_AVAILABLE or not mt5:
            return False
            
        try:
            account_info = mt5.account_info()
            if account_info:
                current_login = int(account_info.login)
                current_server = str(account_info.server).strip()
                
                if current_login == int(target_login) and current_server == str(target_server).strip():
                    logger.info(f"[SHARED] Reusing existing terminal session for account {current_login}")
                    return True
            return False
        except Exception as e:
            logger.debug(f"[SHARED] Could not verify existing session: {e}")
            return False

    def _perform_mt5_login(self) -> bool:
        """Perform MT5 login with credentials"""
        logger.info("[VERBOSE] _perform_mt5_login() started")
        
        login = self.config.get('login')
        password = self.config.get('password')
        server = self.config.get('server')
        
        if not login or not password or not server:
            logger.error(f"[ERROR] Missing credentials in config: login={login}, server={server}")
            return False

        # SHARED SESSION OPTIMIZATION
        # If terminal is already on the correct account, we skip login to avoid reset
        if self._check_shared_session(login, server):
            logger.info("[SHARED] [OK] Skipping explicit login as session is already active")
            return True

        logger.info(f"[VERBOSE] Login parameters: login={login} (type={type(login).__name__}), server='{server}'")
        logger.info(f"[VERBOSE] Calling mt5.login(login={int(login)}, password=[HIDDEN], server='{str(server).strip()}')...")
        
        authorized = mt5.login(
            login=int(login),
            password=str(password).strip(),
            server=str(server).strip()
        )
        
        logger.info(f"[VERBOSE] mt5.login() returned: {authorized}")
        
        if not authorized:
            error = mt5.last_error()
            self.last_error = f"Auth failed: {error}"
            logger.error(f"[VERBOSE] [ERROR] mt5.login() FAILED: {error}")
            logger.error(f"[VERBOSE] Attempted login={int(login)}, server='{str(server).strip()}'")
            return False
            
        self.last_error = None
        logger.info("[VERBOSE] [OK] mt5.login() SUCCESS")
        return True

    def _verify_demo_account(self) -> bool:
        """Verify connected account is demo and set flags"""
        logger.info("[VERBOSE] _verify_demo_account() started")
        
        account_info = mt5.account_info()
        if account_info is None:
            logger.error("[VERBOSE] ❌ mt5.account_info() returned None")
            return False
        
        logger.info(f"[VERBOSE] Account info retrieved: login={account_info.login}, server={account_info.server}, trade_mode={account_info.trade_mode}")
        
        self.is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        
        logger.info(f"[VERBOSE] Account type check: is_demo={self.is_demo} (trade_mode={account_info.trade_mode}, DEMO_MODE={mt5.ACCOUNT_TRADE_MODE_DEMO})")
        
        if not self.is_demo:
            logger.critical("[VERBOSE] [WARNING]  REAL ACCOUNT DETECTED! Shutting down for safety.")
            mt5.shutdown()
            return False
            
        self.is_connected = True
        self.connection_state = ConnectionState.CONNECTED
        
        logger.info(f"[INSTANCE {id(self)}] [VERBOSE] [OK] Demo account verified, is_connected={self.is_connected}, connection_state={self.connection_state}")
        return True

    def _log_connection_success(self) -> None:
        """Log successful connection details with symbol count"""
        account_info = mt5.account_info()
        forex_count = len([s for s in self.available_symbols if len(s) == 6 and not s.startswith('X')])
        
        logger.info("=" * 60)
        logger.info("[OK] MT5 Connected Successfully!")
        logger.info(f"   Account: {account_info.login}")
        logger.info(f"   Server: {account_info.server}")
        logger.info(f"   Balance: {account_info.balance:,.2f} {account_info.currency}")
        logger.info(f"   Type: {'DEMO' if self.is_demo else 'REAL'}")
        logger.info(f"   Symbols Available: {len(self.available_symbols)} (FOREX: {forex_count} pares)")
        logger.info("=" * 60)
        """
        Load MT5 configuration from DATABASE (single source of truth)
        
        Returns:
            Dict with 'enabled', 'login', 'server', 'password', 'account_id'
        """
        try:
            # Get all MT5 accounts
            all_accounts = self.storage.get_broker_accounts()
            mt5_accounts = [acc for acc in all_accounts if acc.get('platform_id') == 'mt5' and acc.get('enabled', True)]
            
            if not mt5_accounts:
                logger.warning("No MT5 accounts found in database. MT5 connector disabled.")
                return {'enabled': False}
            
            # Select account (by ID or first enabled)
            account = None
            if self.account_id:
                account = next((acc for acc in mt5_accounts if acc['account_id'] == self.account_id), None)
                if not account:
                    logger.error(f"MT5 account {self.account_id} not found in database")
                    return {'enabled': False}
            else:
                account = mt5_accounts[0]  # Use first enabled account
            
            # Store account ID for later use
            self.account_id = account['account_id']
            
            # Get credentials
            credentials = self.storage.get_credentials(self.account_id)
            
            if not credentials or not credentials.get('password'):
                logger.error(f"No credentials found for MT5 account {self.account_id}")
                return {'enabled': False}
            
            config = {
                'enabled': True,
                'login': account.get('login') or account.get('account_number'),
                'server': account.get('server'),
                'password': credentials['password'],
                'account_id': self.account_id,
                'account_name': account.get('account_name'),
                'account_type': account.get('account_type')
            }
            
            logger.info(f"Loaded MT5 config from DB: Account '{config['account_name']}' (Login: {config['login']})")
            return config
            
        except Exception as e:
            logger.error(f"Error loading MT5 config from database: {e}", exc_info=True)
            return {'enabled': False}

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Normalize provider symbols to MT5 format.

        Examples:
            USDJPY=X -> USDJPY
        """
        return symbol.replace("=X", "") if symbol else symbol
    
    def connect(self, timeout_seconds: int = 10) -> bool:
        """
        Start asynchronous connection to MT5 terminal with timeout
        
        Args:
            timeout_seconds: Maximum time to wait for connection
            
        Returns:
            True if connection successful within timeout
        """
        if not self.config.get('enabled', False):
            logger.warning("MT5 connector is disabled in configuration. skipping connection.")
            self.connection_state = ConnectionState.FAILED
            return False
            
        if self.connection_state == ConnectionState.CONNECTED:
            return True
            
        if self.connection_state == ConnectionState.CONNECTING:
            # Already attempting connection, wait for result
            return self._wait_for_connection(timeout_seconds)
        
        # Start connection in background thread
        self.connection_state = ConnectionState.CONNECTING
        self.connection_thread = threading.Thread(
            target=self._connect_sync,
            name="MT5-Connector",
            daemon=True
        )
        self.connection_thread.start()
        
        # Wait for connection with timeout
        return self._wait_for_connection(timeout_seconds)
    
    def connect_blocking(self) -> bool:
        """
        SYNCHRONOUS connection in caller's thread (MT5 library is thread-specific).
        Use this when you need MT5 initialized in the SAME thread that will execute trades.
        
        Returns:
            True if connection successful
        """
        if not self.config.get('enabled', False):
            logger.warning("MT5 connector is disabled in configuration.")
            self.connection_state = ConnectionState.FAILED
            return False
            
        if self.connection_state == ConnectionState.CONNECTED:
            logger.info("MT5 already connected.")
            return True
        
        logger.info("[CONNECT] Conectando a MT5 sincrónicamente en thread actual...")
        success = self._connect_sync_once()
        
        if success:
            logger.info(f"[OK] MT5 connected! Thread: {threading.current_thread().name}, Symbols: {len(self.available_symbols)}")
        else:
            logger.error("[ERROR] MT5 connection failed")
            
        return success
    
    def _connect_sync(self) -> None:
        """
        Synchronous connection attempt (runs in background thread)
        """
        try:
            self.last_attempt = time.time()
            
            # Initialize MT5
            if not mt5.initialize():
                error = mt5.last_error()
                logger.error(f"MT5 initialization failed: {error}")
                self.connection_state = ConnectionState.FAILED
                self._schedule_retry()
                return
            
            # Get credentials from config (already loaded from DB)
            login = self.config.get('login')
            password = self.config.get('password')
            server = self.config.get('server')
            
            if not login or not password or not server:
                logger.error(f"Incomplete MT5 credentials: login={bool(login)}, password={bool(password)}, server={bool(server)}")
                self.connection_state = ConnectionState.FAILED
                self._schedule_retry()
                return
            
            # Log what we're about to send (without password)
            logger.info(f"Attempting MT5 login with: login={login} (type: {type(login)}, len: {len(str(login))}), server='{server}'")
            logger.info(f"MT5 terminal status: initialized={mt5.initialize() is not None}, last_error={mt5.last_error()}")
            
            # Login - FORZAR login específico, no asumir cuenta abierta por defecto
            logger.info(f"Calling mt5.login(login={int(login)}, password=[HIDDEN], server='{str(server).strip()}')")
            authorized = mt5.login(
                login=int(login),
                password=str(password).strip(),
                server=str(server).strip()
            )
            
            logger.info(f"mt5.login() returned: {authorized}")
            if not authorized:
                error = mt5.last_error()
                logger.error(f"MT5 login failed: {error}")
                logger.error(f"MT5 terminal info: version={mt5.version()}, account_info={mt5.account_info()}")
                self.connection_state = ConnectionState.FAILED
                self._schedule_retry()
                return
            
            # VERIFICAR que la cuenta conectada sea la correcta (no asumir)
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Could not retrieve MT5 account information after login")
                self.connection_state = ConnectionState.FAILED
                self._schedule_retry()
                return
            
            # Verificar que el login de la cuenta conectada coincida con el solicitado
            if account_info.login != int(login):
                logger.error(f"Cuenta conectada ({account_info.login}) no coincide con la solicitada ({login})")
                logger.error(f"Servidor conectado: {account_info.server}, Servidor solicitado: {server}")
                mt5.shutdown()
                self.connection_state = ConnectionState.FAILED
                self._schedule_retry()
                return
            
            # Check if demo account
            self.is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
            
            if not self.is_demo:
                logger.critical("⚠️  CONNECTED TO REAL ACCOUNT! Trading disabled for safety.")
                logger.critical("   Aethelgard will NOT execute on real accounts.")
                mt5.shutdown()
                self.connection_state = ConnectionState.FAILED
                self._schedule_retry()
                return
            
            self.is_connected = True
            self.connection_state = ConnectionState.CONNECTED
            
            # Auto-discovery: Load available symbols from broker
            self._load_available_symbols()
            
            # Log connection success (unified logging)
            self._log_connection_success()
            
        except Exception as e:
            logger.error(f"Error connecting to MT5: {e}")
            self.connection_state = ConnectionState.FAILED
            self._schedule_retry()
    
    def _wait_for_connection(self, timeout_seconds: int) -> bool:
        """
        Wait for connection to complete with timeout
        
        Args:
            timeout_seconds: Maximum seconds to wait
            
        Returns:
            True if connected successfully
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self.connection_state == ConnectionState.CONNECTED:
                return True
            elif self.connection_state == ConnectionState.FAILED:
                return False
            time.sleep(0.1)  # Small sleep to avoid busy waiting
        
        # Timeout reached
        logger.warning(f"MT5 connection timeout after {timeout_seconds} seconds")
        return False
    
    def _schedule_retry(self) -> None:
        """
        Schedule automatic retry in background
        """
        if self.retry_timer is not None:
            self.retry_timer.cancel()
        
        def retry() -> None:
            logger.info("[RETRY] Retrying MT5 connection...")
            self.connect()
        
        self.retry_timer = threading.Timer(30.0, retry)  # Retry every 30 seconds
        self.retry_timer.start()
        logger.info("[WAIT] Next MT5 retry in 30 seconds")
    
    def _load_available_symbols(self) -> None:
        """
        Auto-discovery: Load all available symbols from broker.
        This eliminates manual configuration and prevents errors with unavailable pairs.
        """
        try:
            symbols = mt5.symbols_get()
            if symbols is None:
                logger.warning("Could not retrieve symbols from MT5")
                return
            
            # Filter visible symbols (available for trading)
            self.available_symbols = {s.name for s in symbols if s.visible}
            
            # Log summary by category
            forex_pairs = [s for s in self.available_symbols if len(s) == 6 and not s.startswith('X')]
            metals = [s for s in self.available_symbols if s.startswith('X')]
            
            logger.info(f"[LIST] Auto-discovered {len(self.available_symbols)} symbols:")
            if forex_pairs:
                logger.info(f"   FOREX: {len(forex_pairs)} pares ({', '.join(sorted(forex_pairs)[:10])}{'...' if len(forex_pairs) > 10 else ''})")
            if metals:
                logger.info(f"   METALS: {len(metals)} ({', '.join(sorted(metals)[:5])}{'...' if len(metals) > 5 else ''})")
                
        except Exception as e:
            logger.error(f"Error loading available symbols: {e}", exc_info=True)
            self.available_symbols = set()
    
    def disconnect(self) -> None:
        """Disconnect from MT5"""
        if self.is_connected:
            mt5.shutdown()
            self.is_connected = False
            logger.info("MT5 disconnected")
    
    # --- DATA PROVIDER INTERFACE IMPLEMENTATION ---
    
    def is_local(self) -> bool:
        """Indicates that this connector is running locally (fast access)"""
        return True

    def is_available(self) -> bool:
        """Check if connector is connected and ready"""
        return self.is_connected

    def fetch_ohlc(self, symbol: str, timeframe: str = "M5", count: int = 500) -> Optional[Any]:
        """
        Fetch OHLC data from MT5 (DataProvider Protocol)
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe string (M1, M5, H1, etc.)
            count: Number of bars
            
        Returns:
            pandas DataFrame with [time, open, high, low, close, volume]
        """
        if not self.is_connected:
            return None
            
        try:
            # Normalize symbol
            mt5_symbol = self.normalize_symbol(symbol)
            
            # Map timeframe
            mt5_tf = self._map_timeframe_to_mt5(timeframe)
            if mt5_tf is None:
                logger.error(f"Invalid timeframe mapping for: {timeframe}")
                return None
                
            # Copy rates
            rates = mt5.copy_rates_from_pos(mt5_symbol, mt5_tf, 0, count)
            
            if rates is None or len(rates) == 0:
                # Try explicit connection check if data fails
                if not mt5.symbol_select(mt5_symbol, True):
                    logger.warning(f"Symbol {mt5_symbol} not found in Market Watch")
                return None
                
            # Convert to DataFrame
            import pandas as pd
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            # Rename columns to standard format
            # MT5 returns: time, open, high, low, close, tick_volume, spread, real_volume
            # We need: time, open, high, low, close, volume
            df.rename(columns={
                'tick_volume': 'volume', 
                'real_volume': 'vol_real'
            }, inplace=True)
            
            return df[['time', 'open', 'high', 'low', 'close', 'volume']]
            
        except Exception as e:
            logger.error(f"Error fetching OHLC from MT5 for {symbol}: {e}")
            return None

    def _map_timeframe_to_mt5(self, timeframe: str) -> Optional[int]:
        """Map string timeframe to MT5 constant"""
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1
        }
        return mapping.get(timeframe.upper())

    def _build_trade_comment(self, signal: Signal) -> str:
        """
        Build MT5 comment with timeframe and strategy info.
        
        Format: AE_<TF>_<TYPE>_<STRAT>
        Example: AE_M5_BUY_RSI (13 chars)
        
        MT5 comment limit: 31 chars
        """
        tf = (signal.timeframe or 'M5').upper()
        signal_type = signal.signal_type.value[:4]  # BUY or SELL (4 chars max)
        strategy = (signal.strategy_id or 'RSI')[:8]  # Max 8 chars for strategy
        signal_id = signal.metadata.get('signal_id') if hasattr(signal, 'metadata') else None
        # Embebe signal_id en el comentario si existe
        if signal_id:
            comment = f"Aethelgard_signal_{signal_id}_{tf}_{signal_type}_{strategy}"
        else:
            comment = f"AE_{tf}_{signal_type}_{strategy}"
        # Trunca si excede el límite MT5
        if len(comment) > 31:
            comment = comment[:31]
        return comment
    
    def execute_order(self, signal: Any) -> Dict[str, Any]:
        """BaseConnector interface wrapper for execute_signal"""
        return self.execute_signal(signal)

    def execute_signal(self, signal: Signal) -> Dict:
        """Execute a trading signal using MT5."""
        # 1. Environment Validation
        env_result = self._validate_execution_environment()
        if not env_result['success']:
            return env_result

        try:
            # 2. Symbol Normalization and Availability
            symbol_info = self._get_execution_symbol_info(signal.symbol)
            if not symbol_info:
                return {'success': False, 'error': f'Symbol {signal.symbol} not available or invalid'}

            # 3. Prepare and Send Order
            order_type = mt5.ORDER_TYPE_BUY if signal.signal_type == SignalType.BUY else mt5.ORDER_TYPE_SELL
            request = self._prepare_order_request(signal, symbol_info, order_type)
            if not request:
                return {'success': False, 'error': 'Failed to prepare order request'}

            result = mt5.order_send(request)
            return self._handle_order_result(result, signal, request)
        
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return {'success': False, 'error': str(e)}

    def _validate_execution_environment(self) -> Dict:
        """Checks connection and account safety."""
        if not self.is_connected:
            return {'success': False, 'error': 'Not connected'}
        if not self.is_demo:
            return {'success': False, 'error': 'Not a demo account'}
        return {'success': True}

    def _get_execution_symbol_info(self, raw_symbol: str) -> Optional[Any]:
        """Normalizes symbol and ensures it's available and visible."""
        symbol = self.normalize_symbol(raw_symbol)
        
        # Check broker level availability
        if len(self.available_symbols) > 0 and symbol not in self.available_symbols:
            logger.debug(f"Symbol {symbol} not available in this broker")
            return None
            
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            return None
            
        # Ensure Market Watch visibility
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return None
            symbol_info = mt5.symbol_info(symbol)
            
        return symbol_info

    def _prepare_order_request(self, signal: Signal, symbol_info: Any, order_type: int) -> Optional[Dict]:
        """Prepare order request dictionary"""
        try:
            # Get current price
            tick = mt5.symbol_info_tick(symbol_info.name)
            if tick is None:
                logger.error(f"Could not get tick for {symbol_info.name}")
                return None
            
            price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
            
            # Normalize price
            from utils.market_ops import normalize_price as global_normalize
            from utils.market_ops import normalize_volume as global_normalize_volume
            
            price = global_normalize(price, symbol_info)
            
            # Get volume
            volume = getattr(signal, 'volume', 0.01)
            volume = global_normalize_volume(volume, symbol_info)
            
            # Normalize SL/TP
            sl = global_normalize(signal.stop_loss, symbol_info) if signal.stop_loss else 0.0
            tp = global_normalize(signal.take_profit, symbol_info) if signal.take_profit else 0.0
            
            return {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol_info.name,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": self._build_trade_comment(signal),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
        except Exception as e:
            logger.error(f"Error preparing order request: {e}")
            return None

    def _handle_order_result(self, result: Any, signal: Signal, request: Dict) -> Dict:
        """Handle MT5 order result"""
        if result is None:
            error = mt5.last_error()
            logger.error(f"Order send failed: {error}")
            return {'success': False, 'error': str(error)}
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order rejected: {result.retcode} - {result.comment}")
            return {'success': False, 'error': f'{result.retcode}: {result.comment}'}
        
        logger.info(
            f"✅ Order executed: {request['symbol']} {signal.signal_type.value} "
            f"@ {result.price} | Ticket: {result.order}"
        )
        
        return {
            'success': True,
            'ticket': result.order,
            'price': result.price,
            'volume': request['volume'],
            'symbol': request['symbol'],
            'type': signal.signal_type.value
        }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """BaseConnector interface wrapper for get_open_positions"""
        res = self.get_open_positions()
        return res if res is not None else []

    def get_open_positions(self) -> Optional[List[Dict]]:
        """
        Get all currently open positions from MT5
        
        Returns:
            List of position dicts or None if error
        """
        if not self.is_connected:
            logger.warning("MT5 not connected, cannot get positions")
            return None
        
        try:
            positions = mt5.positions_get()
            if positions is None:
                error = mt5.last_error()
                logger.error(f"Failed to get positions from MT5. Error: {error}")
                
                # If terminal is not connected, force state change
                if error[0] == mt5.RES_E_NOT_INITIALIZED:
                    logger.warning("MT5 session lost during positions_get. Resetting state.")
                    self.is_connected = False
                    self.connection_state = ConnectionState.DISCONNECTED
                
                return None
            
            # Convert to dict format
            position_list = []
            for pos in positions:
                position_list.append({
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'price': pos.price_open,  # Entry price (alias for compatibility)
                    'price_open': pos.price_open,
                    'price_current': pos.price_current,
                    'current_price': pos.price_current,  # Alias for PositionManager compatibility
                    'volume': pos.volume,
                    'profit': pos.profit,
                    'sl': pos.sl,  # Stop loss
                    'tp': pos.tp,  # Take profit
                    'time': pos.time,  # Open time (Unix timestamp)
                    'type': pos.type,  # Position type (0=BUY, 1=SELL)
                })
            
            return position_list
            
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return None
    
    def get_closed_positions(self, hours: int = 24) -> List[Dict]:
        """
        Get closed positions from MT5 history
        
        Args:
            hours: Look back this many hours
        
        Returns:
            List of closed position dicts
        """
        if not self.is_connected:
            logger.warning("MT5 not connected. Returning empty list.")
            return []
        
        try:
            from_date = datetime.now() - timedelta(hours=hours)
            to_date = datetime.now()
            
            # Get history deals
            deals = mt5.history_deals_get(from_date, to_date)
            
            if deals is None:
                logger.warning("No history deals found")
                return []
            
            closed_positions = []
            
            # Process deals - filter only our magic number and exits
            for deal in deals:
                # Only our trades
                if deal.magic != self.magic_number:
                    continue
                
                # Only exits
                if deal.entry != mt5.DEAL_ENTRY_OUT:
                    continue
                
                # Find entry deal
                entry_deal = self._find_entry_deal(deal.position_id, from_date, to_date)
                
                position_info = {
                    'ticket': deal.position_id,
                    'symbol': deal.symbol,
                    'entry_price': entry_deal.price if entry_deal else None,
                    'exit_price': deal.price,
                    'profit': deal.profit,
                    'volume': deal.volume,
                    'close_time': datetime.fromtimestamp(deal.time),
                    'exit_reason': self._detect_exit_reason(deal),
                    'signal_id': self._extract_signal_id(deal.comment)
                }
                
                closed_positions.append(position_info)
            
            if closed_positions:
                logger.info(f"Found {len(closed_positions)} closed positions in last {hours}h")
            
            return closed_positions
        
        except Exception as e:
            logger.error(f"Error getting closed positions: {e}")
            return []
    
    def get_account_balance(self) -> float:
        """
        Get current account balance from MT5.
        
        Returns:
            Account balance in account currency, or 10000.0 as default if error
        """
        if not self.is_connected:
            logger.warning("MT5 not connected, using default balance 10000")
            return 10000.0
        
        try:
            account_info = mt5.account_info()
            if account_info:
                return account_info.balance
            
            logger.warning("Could not get account info, using default balance 10000")
            return 10000.0
        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            return 10000.0
    
    def get_symbol_info(self, symbol: str) -> Optional[Any]:
        """
        Get symbol information from MT5.
        Ensures symbol is visible in Market Watch.
        
        Args:
            symbol: Symbol to query (e.g., 'EURUSD')
        
        Returns:
            MT5 SymbolInfo object or None if error
        """
        if not self.is_connected:
            logger.warning(f"MT5 not connected, cannot get symbol info for {symbol}")
            return None
        
        try:
            # Ensure symbol is visible in Market Watch
            if not mt5.symbol_select(symbol, True):
                logger.warning(f"Could not enable {symbol} in Market Watch")
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"Could not get symbol info for {symbol}")
            return symbol_info
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None
    
    def calculate_margin(self, signal: Signal, position_size: float) -> Optional[float]:
        """
        Calculate required margin for a position using MT5 built-in function.
        
        Args:
            signal: Trading signal with symbol, type, entry price
            position_size: Position size in lots
        
        Returns:
            Required margin in account currency, or None if calculation fails
        """
        if not self.is_connected:
            logger.warning(f"MT5 not connected, cannot calculate margin for {signal.symbol}")
            return None
        
        try:
            order_type = mt5.ORDER_TYPE_BUY if signal.signal_type.value == 'BUY' else mt5.ORDER_TYPE_SELL
            margin_required = mt5.order_calc_margin(
                order_type,
                signal.symbol,
                position_size,
                signal.entry_price
            )
            
            if margin_required is None:
                logger.warning(f"Could not calculate margin for {signal.symbol}")
            
            return margin_required
        except Exception as e:
            logger.error(f"Error calculating margin: {e}")
            return None
    
    def reconcile_closed_trades(self, listener: Any, hours_back: int = 24) -> None:
        """
        Reconcile closed trades from MT5 history with the listener.
        
        Called at startup to process any trades that closed while the bot was offline.
        Uses idempotency to avoid duplicating already processed trades.
        
        Args:
            listener: TradeClosureListener instance to emit events to
            hours_back: How many hours to look back in history
        """
        if not self.is_connected:
            logger.warning("MT5 not connected. Skipping reconciliation.")
            return
        
        try:
            from_date, to_date = self._get_reconciliation_date_range(hours_back)
            deals = self._get_historical_deals(from_date, to_date)
            
            if not deals:
                logger.info("No deals found in reconciliation period")
                return
            
            processed_count = self._process_reconciliation_deals(deals, listener, from_date, to_date, hours_back)
            logger.info(f"Reconciliation complete. Processed {processed_count} trades from last {hours_back}h")
            
        except Exception as e:
            logger.error(f"Error during reconciliation: {e}")

    def _get_reconciliation_date_range(self, hours_back: int) -> tuple:
        """Get date range for reconciliation"""
        from_date = datetime.now() - timedelta(hours=hours_back)
        to_date = datetime.now()
        return from_date, to_date

    def _get_historical_deals(self, from_date: datetime, to_date: datetime) -> Optional[List]:
        """Get historical deals from MT5"""
        deals = mt5.history_deals_get(from_date, to_date)
        return deals if deals is not None else []

    def _process_reconciliation_deals(self, deals: List, listener: Any, from_date: datetime, to_date: datetime, hours_back: int) -> int:
        """Process deals for reconciliation and return count of processed trades"""
        processed_count = 0
        
        # Process exit deals only
        for deal in deals:
            if not self._is_our_exit_deal(deal):
                continue
                
            position = self._find_position_for_deal(deal, from_date, to_date)
            if not position:
                logger.warning(f"Could not find position data for deal {deal.ticket}")
                continue
            
            if self._process_reconciled_trade(position, deal, listener):
                processed_count += 1
        
        return processed_count

    def _is_our_exit_deal(self, deal: Any) -> bool:
        """Check if deal is our exit deal"""
        return deal.magic == self.magic_number and deal.entry == mt5.DEAL_ENTRY_OUT

    def _process_reconciled_trade(self, position: Any, deal: Any, listener: Any) -> bool:
        """Process a single reconciled trade and return success"""
        try:
            event = self._create_trade_closed_event(position, deal)
            broker_event = BrokerEvent.from_trade_closed(event)
            
            # Call async method in sync context using event loop
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, schedule as task (don't wait)
                    asyncio.create_task(listener.handle_trade_closed_event(broker_event))
                    success = True  # Assume success, will be processed async
                else:
                    # If no loop running, run synchronously
                    success = loop.run_until_complete(listener.handle_trade_closed_event(broker_event))
            except RuntimeError:
                # No event loop, create one for this call
                success = asyncio.run(listener.handle_trade_closed_event(broker_event))
            
            if success:
                logger.info(f"Reconciled trade: {event.ticket} {event.symbol} {event.result.value}")
            else:
                logger.debug(f"Trade already processed: {event.ticket}")
            
            return success
        except Exception as e:
            logger.error(f"Error processing reconciled trade {deal.ticket}: {e}")
            return False
    
    def _find_position_for_deal(self, deal: Any, from_date: datetime, to_date: datetime) -> Optional[Any]:
        """
        Find the position data for a given exit deal.
        
        This reconstructs position info from deals since MT5 positions are only available when open.
        """
        try:
            # Get deals for this position
            position_deals = mt5.history_deals_get(from_date, to_date, position=deal.position_id)
            if not position_deals:
                return None
            
            # Find entry deal
            entry_deal = None
            for d in position_deals:
                if d.entry == mt5.DEAL_ENTRY_IN:
                    entry_deal = d
                    break
            
            if not entry_deal:
                return None
            
            # Create a position-like object from the entry deal
            class PositionData:
                def __init__(self, entry_deal):
                    self.ticket = entry_deal.position_id
                    self.symbol = entry_deal.symbol
                    self.price_open = entry_deal.price
                    self.time = entry_deal.time
                    self.comment = entry_deal.comment
            
            return PositionData(entry_deal)
            
        except Exception as e:
            logger.error(f"Error finding position for deal {deal.ticket}: {e}")
            return None
    
    def _find_entry_deal(self, position_id: int, from_date: datetime, to_date: datetime) -> None:
        """Find the entry deal for a position"""
        try:
            deals = mt5.history_deals_get(from_date, to_date, position=position_id)
            if deals:
                for deal in deals:
                    if deal.entry == mt5.DEAL_ENTRY_IN:
                        return deal
            return None
        except Exception as e:
            logger.error(f"Error finding entry deal: {e}")
            return None
    
    def _detect_exit_reason(self, deal: Any) -> str:
        """Detect why a position was closed"""
        comment = deal.comment.lower()
        
        if 'tp' in comment or 'take profit' in comment:
            return 'TAKE_PROFIT'
        elif 'sl' in comment or 'stop loss' in comment or 'stop out' in comment:
            return 'STOP_LOSS'
        elif 'close' in comment:
            return 'MANUAL'
        else:
            return 'CLOSED'
    
    def _extract_signal_id(self, comment: str) -> Optional[str]:
        """Extract signal ID from deal comment if present"""
        try:
            if 'Aethelgard_' in comment:
                parts = comment.split('Aethelgard_')
                if len(parts) > 1:
                    return parts[1]
            return None
        except Exception:
            return None
    
    def _create_trade_closed_event(self, position: Any, deal: Any) -> BrokerTradeClosedEvent:
        """
        Create BrokerTradeClosedEvent from MT5 position and deal data
        
        Args:
            position: MT5 position object (entry data)
            deal: MT5 deal object (exit data)
        
        Returns:
            BrokerTradeClosedEvent with mapped data
        """
        # Calculate pips dynamically based on symbol digits
        symbol_info = mt5.symbol_info(position.symbol)
        if symbol_info:
            pip_multiplier = 10 ** symbol_info.digits
            pips = (deal.price - position.price_open) * pip_multiplier
        else:
            # Fallback for EURUSD-like pairs if symbol info unavailable
            pips = (deal.price - position.price_open) * 10000
        
        # Determine result
        if deal.profit > 0:
            result = TradeResult.WIN
        elif deal.profit < 0:
            result = TradeResult.LOSS
        else:
            result = TradeResult.BREAKEVEN
        
        return BrokerTradeClosedEvent(
            ticket=str(deal.ticket),  # Use deal ticket as unique identifier
            symbol=self.normalize_symbol(position.symbol),
            entry_price=position.price_open,
            exit_price=deal.price,
            entry_time=datetime.fromtimestamp(position.time),
            exit_time=datetime.fromtimestamp(deal.time),
            pips=pips,
            profit_loss=deal.profit,
            result=result,
            exit_reason=self._detect_exit_reason(deal),
            broker_id="MT5",
            signal_id=self._extract_signal_id(position.comment)
        )
    
    def modify_position(self, ticket: int, new_sl: float, new_tp: Optional[float] = None, reason: str = "") -> Dict[str, Any]:
        """Modify SL/TP of an existing position."""
        if not self.is_connected:
            return {'success': False, 'error': 'MT5 not connected'}
        
        try:
            # 1. Fetch position
            position = self._get_mt5_position(ticket)
            if not position:
                return {'success': False, 'error': f'Position {ticket} not found'}
            
            # 2. Validate modification parameters
            validation = self._validate_modification_params(position, new_sl, new_tp)
            if not validation['success']:
                return validation
            
            # 3. Use validated/adjusted TP
            final_tp = validation['tp']
            
            # 4. Prepare and Send Request
            request = self._prepare_modify_request(ticket, position.symbol, new_sl, final_tp, reason)
            
            # Execute modification
            result = mt5.order_send(request)
            
            # DEBUG: Log full MT5 response
            logger.info(f"MT5 modify response for {ticket}: {result}")
            if result:
                logger.info(f"  retcode: {result.retcode}")
                logger.info(f"  comment: {result.comment}")
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Position {ticket} modified - SL: {new_sl:.5f}, TP: {final_tp:.5f} - {reason}")
                return {'success': True}
            else:
                error_msg = result.comment if result else 'Unknown error'
                if result and result.retcode in [10025, 10016]:
                    logger.debug(f"MT5 rejected modification for {ticket}: {error_msg} (retcode {result.retcode})")
                else:
                    logger.error(f"Failed to modify position {ticket}: {error_msg}")
                return {'success': False, 'error': error_msg}
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error modifying position {ticket}: {error_msg}")
            return {'success': False, 'error': error_msg}

    def _get_mt5_position(self, ticket: int) -> Optional[Any]:
        """Fetch a specific position from MT5 by ticket."""
        if not MT5_AVAILABLE: return None
        positions = mt5.positions_get(ticket=ticket)
        return positions[0] if positions and len(positions) > 0 else None

    def _validate_modification_params(self, position: Any, new_sl: float, new_tp: Optional[float]) -> Dict[str, Any]:
        """Verify if new SL/TP are valid and respect platform constraints."""
        if not MT5_AVAILABLE: return {'success': False, 'error': 'MT5 not available'}
        symbol_info = mt5.symbol_info(position.symbol)
        if not symbol_info:
            return {'success': False, 'error': f'Symbol {position.symbol} info not found'}
        
        tick = mt5.symbol_info_tick(position.symbol)
        if not tick:
            return {'success': False, 'error': f'Tick for {position.symbol} not found'}
        
        current_price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        if not self._validate_freeze_level(position.ticket, new_sl, current_price, symbol_info):
            return {'success': False, 'error': 'Stop Loss violates freeze level'}
            
        final_tp = self._validate_sltp_logic(position.ticket, position.type == mt5.ORDER_TYPE_BUY, new_sl, new_tp)
        return {'success': True, 'tp': final_tp}

    def _prepare_modify_request(self, ticket: int, symbol: str, sl: float, tp: float, reason: str = "") -> Dict[str, Any]:
        """Prepare the request dictionary for mt5.order_send."""
        return {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": normalize_price(sl, mt5.symbol_info(symbol)) if sl > 0 else 0.0,
            "tp": normalize_price(tp, mt5.symbol_info(symbol)) if tp > 0 else 0.0,
            "comment": f"AE_MOD_{reason}"[:31],
        }

    def _validate_freeze_level(self, ticket: int, new_sl: float, current_price: float, symbol_info: Any) -> bool:
        """
        Validate if SL modification respects freeze level.
        Returns True if valid, False if violating freeze level.
        """
        try:
            point = getattr(symbol_info, 'point', 0.00001)
            freeze_level = getattr(symbol_info, 'trade_stops_level', 0)
            
            # Calculate distance in points
            sl_distance_points = abs(new_sl - current_price) / point
            
            logger.info(f"Freeze validation: SL={new_sl:.5f}, Current={current_price:.5f}, "
                        f"Distance={sl_distance_points:.1f} points, Freeze={freeze_level}")
            
            if freeze_level > 0 and sl_distance_points < freeze_level:
                logger.warning(f"Position {ticket}: SL too close ({sl_distance_points:.1f} < {freeze_level})")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error validating freeze level: {e}")
            # Fail safe: allow attempt if validation fails internally
            return True

    def _validate_sltp_logic(self, ticket: int, is_buy: bool, new_sl: float, new_tp: Optional[float]) -> float:
        """
        Validate and correct SL/TP logic to avoid platform rejection.
        Returns corrected TP (or 0.0 if removed).
        """
        if not new_tp or new_tp <= 0:
            return 0.0
            
        # MT5 forbids TP crossing SL (instant loss)
        if is_buy and new_tp <= new_sl:
            logger.warning(f"Position {ticket} (BUY): TP {new_tp:.5f} <= SL {new_sl:.5f} - Removing TP")
            return 0.0
        elif not is_buy and new_tp >= new_sl:
            logger.warning(f"Position {ticket} (SELL): TP {new_tp:.5f} >= SL {new_sl:.5f} - Removing TP")
            return 0.0
            
        return new_tp
    
    def close_position(self, ticket: int, reason: str = "") -> Dict[str, Any]:
        """
        Close a specific position
        
        Args:
            ticket: Position ticket ID
            reason: Reason for closing (for logging)
            
        Returns:
            dict: {'success': bool, 'error': str}
        """
        if not self.is_connected:
            return {'success': False, 'error': 'MT5 not connected'}
        
        try:
            positions = mt5.positions_get(ticket=ticket)
            
            if not positions or len(positions) == 0:
                logger.warning(f"Position {ticket} not found")
                return {'success': False, 'error': 'Position not found'}
            
            position = positions[0]
            
            # Prepare close request
            # Buscar signal_id en metadata de posición
            signal_id = None
            if hasattr(position, 'comment') and position.comment:
                # Si el comentario original tiene signal_id, extraerlo
                import re
                match = re.search(r'signal_(\w+)', position.comment)
                if match:
                    signal_id = match.group(1)
            comment = f"Aethelgard_Close_signal_{signal_id}_{reason}" if signal_id else (f"Aethelgard_Close_{reason}" if reason else "Aethelgard_Close")
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "price": normalize_price(mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask, mt5.symbol_info(position.symbol)),
                "deviation": 20,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(close_request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Position {ticket} closed successfully - Reason: {reason}")
                return {'success': True}
            else:
                error_msg = result.comment if result else 'Unknown error'
                logger.error(f"Failed to close position {ticket}: {error_msg}")
                return {'success': False, 'error': error_msg}
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error closing position: {error_msg}")
            return {'success': False, 'error': error_msg}


    # --- Data Provider Interface (Unified Connection) ---

    def _resolve_timeframe(self, timeframe: str) -> int:
        """Helper to map string TFs to MT5 constants"""
        t = (timeframe or "M5").upper()
        if t not in TIMEFRAME_MAP:
            logger.warning(f"Unknown timeframe '{timeframe}', falling back to M5")
            t = "M5"
        return TIMEFRAME_MAP[t]

    def get_market_data(self, symbol: str, timeframe: str = "M5", count: int = 500) -> Optional[Any]:
        """BaseConnector interface wrapper for fetch_ohlc"""
        return self.fetch_ohlc(symbol, timeframe, count)


    def get_latency(self) -> float:
        """Measure and return current latency to the provider in milliseconds."""
        if not self.is_connected:
            return 0.0
            
        try:
            # En MT5, una forma de medir latencia es el ping del terminal si está disponible
            # o simplemente el tiempo de respuesta de una operación vacía.
            # Por ahora, usamos el tiempo de ida y vuelta de info_tick (operación ligera)
            start = time.perf_counter()
            mt5.symbol_info_tick("EURUSD")
            return (time.perf_counter() - start) * 1000.0
        except Exception:
            return 0.0

    @property
    def provider_id(self) -> str:
        """Unique identifier for the provider."""
        return "mt5"

# Singleton instance for easy import
_mt5_connector_instance = None


def get_mt5_connector() -> Optional[MT5Connector]:
    """Get or create MT5 connector singleton"""
    global _mt5_connector_instance
    
    if _mt5_connector_instance is None:
        try:
            _mt5_connector_instance = MT5Connector()
            if not _mt5_connector_instance.connect():
                logger.error("Failed to connect MT5 connector")
                _mt5_connector_instance = None
                return None
        except Exception as e:
            logger.error(f"Failed to initialize MT5 connector: {e}")
            return None
    
    return _mt5_connector_instance
