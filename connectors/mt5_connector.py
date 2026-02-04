"""
MT5 Connector - Production-Ready Integration
Simplified connector for OrderExecutor and ClosingMonitor
ARCHITECTURE: Single source of truth = DATABASE (no JSON files)
"""
import logging
import threading
import time
from enum import Enum
from typing import Optional, Dict, List, Any, TYPE_CHECKING
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

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """MT5 Connection states for non-blocking startup"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class MT5Connector:
    """
    Production MT5 Connector for Aethelgard

    Features:
    - Auto-loads configuration from database (broker_accounts + broker_credentials)
    - Validates demo account before executing
    - Implements standard connector interface
    - Thread-safe operations
    - Non-blocking connection with timeout and retry
    """

    def __init__(self, account_id: Optional[str] = None):
        """
        Initialize MT5 Connector

        Args:
            account_id: Optional account ID to use. If None, uses first enabled MT5 account from DB

        ARCHITECTURE NOTE: Configuration comes from DATABASE ONLY (single source of truth)
        """
        if not MT5_AVAILABLE:
            raise ImportError("MetaTrader5 library not installed. Run: pip install MetaTrader5")

        self.storage = StorageManager()
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

        logger.info(f"MT5Connector initialized from database")
    
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
    
    def start(self) -> None:
        """
        Start MT5 connection in background thread.
        Call this after system initialization is complete.
        """
        if not self.config.get('enabled', False):
            logger.warning("MT5 connector is disabled - not starting connection")
            return
            
        if self.connection_state != ConnectionState.DISCONNECTED:
            logger.info("MT5 connection already started or in progress")
            return
            
        logger.info("🚀 Starting MT5 connection in background thread...")
        
        # Start connection in background thread
        self.connection_thread = threading.Thread(
            target=self._connect_background,
            name="MT5-Background-Connector",
            daemon=True
        )
        self.connection_thread.start()
    
    def _connect_background(self) -> None:
        """
        Background connection loop with retries.
        Runs indefinitely until connected or system shutdown.
        """
        while True:
            try:
                if self.connection_state == ConnectionState.CONNECTED:
                    # Already connected, just wait
                    time.sleep(30)
                    continue
                    
                self.connection_state = ConnectionState.CONNECTING
                self.last_attempt = time.time()
                
                logger.info("🔌 Attempting MT5 connection...")
                
                # Try to connect with timeout
                if self._connect_sync_once():
                    logger.info("✅ MT5 connected successfully in background")
                    return  # Exit loop when connected
                    
                # Connection failed, schedule retry
                logger.warning("⚠️  MT5 connection failed, retrying in 30 seconds...")
                self.connection_state = ConnectionState.FAILED
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Error in MT5 background connection loop: {e}")
                self.connection_state = ConnectionState.FAILED
                time.sleep(30)
    
    def _connect_sync_once(self) -> bool:
        """
        Single synchronous connection attempt.
        Returns True if successful, False otherwise.
        """
        try:
            # Initialize MT5 with specific terminal path (IC Markets)
            terminal_path = r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe"
            if not mt5.initialize(terminal_path):
                error = mt5.last_error()
                logger.error(f"MT5 initialization failed: {error}")
                return False
            
            # Get credentials
            login = self.config.get('login')
            password = self.config.get('password')
            server = self.config.get('server')
            
            if not login or not password or not server:
                logger.error("Incomplete MT5 credentials")
                return False
            
            # Login attempt
            authorized = mt5.login(
                login=int(login),
                password=str(password).strip(),
                server=str(server).strip()
            )
            
            if not authorized:
                error = mt5.last_error()
                logger.error(f"MT5 login failed: {error}")
                return False
            
            # Verify account
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Could not retrieve MT5 account information")
                return False
            
            # Check demo account
            self.is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
            if not self.is_demo:
                logger.critical("⚠️  CONNECTED TO REAL ACCOUNT! Trading disabled.")
                mt5.shutdown()
                return False
            
            self.is_connected = True
            self.connection_state = ConnectionState.CONNECTED
            
            logger.info("=" * 60)
            logger.info("✅ MT5 Connected Successfully!")
            logger.info(f"   Account: {account_info.login}")
            logger.info(f"   Server: {account_info.server}")
            logger.info(f"   Balance: {account_info.balance:,.2f} {account_info.currency}")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in MT5 connection attempt: {e}")
            return False
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
            
            logger.info("=" * 60)
            logger.info(f"✅ MT5 Connected Successfully!")
            logger.info(f"   Account: {account_info.login}")
            logger.info(f"   Server: {account_info.server}")
            logger.info(f"   Balance: {account_info.balance:,.2f} {account_info.currency}")
            logger.info(f"   Type: DEMO")
            logger.info("=" * 60)
            
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
        
        def retry():
            logger.info("🔄 Retrying MT5 connection...")
            self.connect()
        
        self.retry_timer = threading.Timer(30.0, retry)  # Retry every 30 seconds
        self.retry_timer.start()
        logger.info("⏰ Next MT5 retry in 30 seconds")
    
    def disconnect(self) -> None:
        """Disconnect from MT5"""
        if self.is_connected:
            mt5.shutdown()
            self.is_connected = False
            logger.info("MT5 disconnected")
    
    def execute_signal(self, signal: Signal) -> Dict:
        """
        Execute a trading signal
        
        Args:
            signal: Signal object to execute
        
        Returns:
            Dict with execution result
        """
        if not self.is_connected:
            logger.error("MT5 not connected. Call connect() first.")
            return {'success': False, 'error': 'Not connected'}
        
        if not self.is_demo:
            logger.error("Safety check: will not execute on non-demo account")
            return {'success': False, 'error': 'Not a demo account'}
        
        try:
            symbol = self.normalize_symbol(signal.symbol)
            if symbol != signal.symbol:
                logger.info(f"Normalized symbol for MT5: {signal.symbol} -> {symbol}")
            
            # Prepare order request
            order_type = mt5.ORDER_TYPE_BUY if signal.signal_type == SignalType.BUY else mt5.ORDER_TYPE_SELL
            
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.error(f"Could not get tick for {symbol}")
                return {'success': False, 'error': f'Symbol {symbol} not available'}
            
            price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
            
            # Calculate volume (default 0.01 lot = micro lot)
            volume = 0.01
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": signal.stop_loss if signal.stop_loss else 0.0,
                "tp": signal.take_profit if signal.take_profit else 0.0,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": f"Aethelgard_{signal.symbol}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send order
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                logger.error(f"Order send failed: {error}")
                return {'success': False, 'error': str(error)}
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order rejected: {result.retcode} - {result.comment}")
                return {'success': False, 'error': f'{result.retcode}: {result.comment}'}
            
            logger.info(
                f"✅ Order executed: {symbol} {signal.signal_type.value} "
                f"@ {result.price} | Ticket: {result.order}"
            )
            
            return {
                'success': True,
                'ticket': result.order,
                'price': result.price,
                'volume': volume,
                'symbol': symbol,
                'type': signal.signal_type.value
            }
        
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return {'success': False, 'error': str(e)}
    
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
            from_date = datetime.now() - timedelta(hours=hours_back)
            to_date = datetime.now()
            
            # Get all deals in the period
            deals = mt5.history_deals_get(from_date, to_date)
            
            if deals is None or len(deals) == 0:
                logger.info("No deals found in reconciliation period")
                return
            
            processed_count = 0
            
            # Process exit deals only
            for deal in deals:
                # Only our trades
                if deal.magic != self.magic_number:
                    continue
                
                # Only exits
                if deal.entry != mt5.DEAL_ENTRY_OUT:
                    continue
                
                # Find the corresponding position (entry) data
                position = self._find_position_for_deal(deal, from_date, to_date)
                if not position:
                    logger.warning(f"Could not find position data for deal {deal.ticket}")
                    continue
                
                # Create the event
                event = self._create_trade_closed_event(position, deal)
                
                # Wrap in BrokerEvent
                broker_event = BrokerEvent.from_trade_closed(event)
                
                # Emit to listener (it handles idempotency)
                try:
                    success = listener.handle_trade_closed_event(broker_event)
                    if success:
                        processed_count += 1
                        logger.info(f"Reconciled trade: {event.ticket} {event.symbol} {event.result.value}")
                    else:
                        logger.debug(f"Trade already processed: {event.ticket}")
                except Exception as e:
                    logger.error(f"Error processing reconciled trade {event.ticket}: {e}")
            
            logger.info(f"Reconciliation complete. Processed {processed_count} trades from last {hours_back}h")
            
        except Exception as e:
            logger.error(f"Error during reconciliation: {e}")
    
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
    
    def get_open_positions(self) -> List[Dict]:
        """Get currently open positions"""
        if not self.is_connected:
            return []
        
        try:
            positions = mt5.positions_get()
            
            if positions is None or len(positions) == 0:
                return []
            
            open_positions = []
            
            for pos in positions:
                if pos.magic != self.magic_number:
                    continue
                
                open_positions.append({
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': 'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'price_current': pos.price_current,
                    'profit': pos.profit,
                    'sl': pos.sl,
                    'tp': pos.tp
                })
            
            return open_positions
        
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []
    
    def close_position(self, ticket: int) -> bool:
        """Close a specific position"""
        if not self.is_connected:
            return False
        
        try:
            positions = mt5.positions_get(ticket=ticket)
            
            if not positions or len(positions) == 0:
                logger.warning(f"Position {ticket} not found")
                return False
            
            position = positions[0]
            
            # Prepare close request
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "Aethelgard_Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(close_request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Position {ticket} closed successfully")
                return True
            else:
                logger.error(f"Failed to close position {ticket}: {result.comment if result else 'Unknown error'}")
                return False
        
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False


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
