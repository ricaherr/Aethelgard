"""
MT5 Connector - Production-Ready Integration
Simplified connector for OrderExecutor and ClosingMonitor
ARCHITECTURE: Single source of truth = DATABASE (no JSON files)
"""
import logging
import json
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logging.warning("MetaTrader5 library not installed. MT5 connector disabled.")

from models.signal import Signal, SignalType
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class MT5Connector:
    """
    Production MT5 Connector for Aethelgard
    
    Features:
    - Auto-loads configuration from config/mt5_config.json
    - Validates demo account before executing
    - Implements standard connector interface
    - Thread-safe operations
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
    
    def connect(self) -> bool:
        """
        Connect to MT5 terminal
        
        Returns:
            True if connection successful
        """
        if not self.config.get('enabled', False):
            logger.warning("MT5 connector is disabled in configuration. skipping connection.")
            return False
            
        try:
            # Initialize MT5
            if not mt5.initialize():
                error = mt5.last_error()
                logger.error(f"MT5 initialization failed: {error}")
                return False
            
            # Get credentials from config (already loaded from DB)
            login = self.config.get('login')
            password = self.config.get('password')
            server = self.config.get('server')
            
            if not login or not password or not server:
                logger.error(f"Incomplete MT5 credentials: login={bool(login)}, password={bool(password)}, server={bool(server)}")
                return False
            
            # Log what we're about to send (without password)
            logger.info(f"Attempting MT5 login with: login={login} (type: {type(login)}, len: {len(str(login))}), server='{server}'")
            
            # Login
            authorized = mt5.login(
                login=int(login),
                password=str(password).strip(),
                server=str(server).strip()
            )
            
            if not authorized:
                error = mt5.last_error()
                logger.error(f"MT5 login failed: {error}")
                return False
            
            # Verify account info
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Could not retrieve MT5 account information")
                return False
            
            # Check if demo account
            self.is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
            
            if not self.is_demo:
                logger.critical("⚠️  CONNECTED TO REAL ACCOUNT! Trading disabled for safety.")
                logger.critical("   Aethelgard will NOT execute on real accounts.")
                mt5.shutdown()
                return False
            
            self.is_connected = True
            
            logger.info("=" * 60)
            logger.info(f"✅ MT5 Connected Successfully!")
            logger.info(f"   Account: {account_info.login}")
            logger.info(f"   Server: {account_info.server}")
            logger.info(f"   Balance: {account_info.balance:,.2f} {account_info.currency}")
            logger.info(f"   Type: DEMO")
            logger.info("=" * 60)
            
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to MT5: {e}")
            return False
    
    def disconnect(self):
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
            symbol = signal.symbol
            
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
                "comment": f"Aethelgard_{signal.id if hasattr(signal, 'id') else 'signal'}",
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
    
    def _find_entry_deal(self, position_id: int, from_date: datetime, to_date: datetime):
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
    
    def _detect_exit_reason(self, deal) -> str:
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
