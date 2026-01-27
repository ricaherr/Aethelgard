import json
import os
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

class StorageManager:
    """
    Manages persistence of system state to a local JSON file.
    Enhanced with signal tracking capabilities for session recovery.
    """
    def __init__(self, db_path='data_vault/system_state.json'):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database with proper structure"""
        initial_state = {
            "signals": [],
            "trades": [],  # Resultados de trades cerrados para EDGE learning
            "system_state": {},
            "tuning_history": []  # Historial de ajustes del tuner
        }
        with open(self.db_path, 'w') as f:
            json.dump(initial_state, f, indent=4)

    def get_system_state(self) -> dict:
        """Retrieves the current system state from the database."""
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                return data.get("system_state", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def update_system_state(self, new_state: dict):
        """Updates and saves the system state."""
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"signals": [], "system_state": {}}
        
        # Garantizar que system_state existe
        if "system_state" not in data:
            data["system_state"] = {}
        data["system_state"].update(new_state)
        
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=4)

    def save_signal(self, signal) -> str:
        """
        Save a signal to persistent storage.
        
        Args:
            signal: Signal object to save
            
        Returns:
            Signal ID (UUID)
        """
        import uuid
        
        signal_id = str(uuid.uuid4())
        
        # Serialize metadata properly (convert non-JSON types)
        metadata = getattr(signal, 'metadata', {})
        serialized_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                serialized_metadata[key] = value
            elif isinstance(value, Enum):
                serialized_metadata[key] = value.value
            else:
                serialized_metadata[key] = str(value)
        
        signal_record = {
            "id": signal_id,
            "symbol": signal.symbol,
            "signal_type": signal.signal_type if isinstance(signal.signal_type, str) else signal.signal_type.value,
            "confidence": getattr(signal, 'confidence', 0.0),
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "status": "executed",
            "metadata": serialized_metadata
        }
        
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"signals": [], "system_state": {}}
        
        if "signals" not in data:
            data["signals"] = []
        
        data["signals"].append(signal_record)
        
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        return signal_id
    
    def count_executed_signals(self, target_date: Optional[date] = None) -> int:
        """
        Count signals executed on a specific date.
        
        This method enables SessionStats to reconstruct state from DB
        after system restarts.
        
        Args:
            target_date: Date to count signals for (defaults to today)
            
        Returns:
            Number of signals executed on the target date
        """
        if target_date is None:
            target_date = date.today()
        
        target_date_str = target_date.isoformat()
        
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0
        
        signals = data.get("signals", [])
        
        count = sum(
            1 for signal in signals 
            if signal.get("date") == target_date_str and signal.get("status") == "executed"
        )
        
        return count
    
    def get_signals_by_date(self, target_date: Optional[date] = None) -> List[Dict]:
        """
        Retrieve all signals for a specific date.
        
        Args:
            target_date: Date to retrieve signals for (defaults to today)
            
        Returns:
            List of signal records
        """
        if target_date is None:
            target_date = date.today()
        
        target_date_str = target_date.isoformat()
        
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        
        signals = data.get("signals", [])
        
        return [
            signal for signal in signals 
            if signal.get("date") == target_date_str
        ]
    
    def get_signals_today(self) -> List[Dict]:
        """
        Retrieve all signals for today.
        Alias for get_signals_by_date() with no arguments.
        
        Returns:
            List of today's signal records
        """
        return self.get_signals_by_date()
    
    def get_statistics(self) -> Dict:
        """
        Get comprehensive statistics about the system.
        Used by the dashboard to display current state.
        
        Returns:
            Dictionary with system statistics
        """
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "total_signals": 0,
                "signals_today": 0,
                "executed_today": 0,
                "system_state": {}
            }
        
        signals = data.get("signals", [])
        today_str = date.today().isoformat()
        
        signals_today = [s for s in signals if s.get("date") == today_str]
        executed_today = [s for s in signals_today if s.get("status") == "executed"]
        
        return {
            "total_signals": len(signals),
            "signals_today": len(signals_today),
            "executed_today": len(executed_today),
            "system_state": data.get("system_state", {}),
            "last_signal": signals[-1] if signals else None
        }
    
    def save_trade_result(self, trade_result: Dict) -> str:
        """
        Save trade result for EDGE learning.
        
        Args:
            trade_result: Dictionary with trade outcome data
                {
                    "signal_id": str,
                    "symbol": str,
                    "entry_price": float,
                    "exit_price": float,
                    "pips": float,
                    "profit_loss": float,  # En moneda base
                    "duration_minutes": int,
                    "is_win": bool,
                    "exit_reason": str,  # "take_profit", "stop_loss", "manual"
                    "market_regime": str,
                    "volatility_atr": float,
                    "parameters_used": dict  # Parámetros activos al generar la señal
                }
        
        Returns:
            Trade ID (UUID)
        """
        import uuid
        
        trade_id = str(uuid.uuid4())
        
        trade_record = {
            "id": trade_id,
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            **trade_result
        }
        
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"signals": [], "trades": [], "system_state": {}, "tuning_history": []}
        
        if "trades" not in data:
            data["trades"] = []
        
        data["trades"].append(trade_record)
        
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        return trade_id
    
    def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        """
        Get recent trade results for EDGE analysis.
        
        Args:
            limit: Maximum number of trades to return (most recent first)
        
        Returns:
            List of trade result dictionaries
        """
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        
        trades = data.get("trades", [])
        
        # Retornar más recientes primero
        return sorted(trades, key=lambda t: t.get("timestamp", ""), reverse=True)[:limit]
    
    def save_tuning_adjustment(self, adjustment: Dict):
        """
        Save parameter adjustment made by tuner for audit trail.
        
        Args:
            adjustment: Dictionary with tuning details
                {
                    "trigger": str,  # "win_rate_low", "consecutive_losses", etc.
                    "old_params": dict,
                    "new_params": dict,
                    "stats": dict  # Win rate, profit factor, etc.
                }
        """
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"signals": [], "trades": [], "system_state": {}, "tuning_history": []}
        
        if "tuning_history" not in data:
            data["tuning_history"] = []
        
        adjustment_record = {
            "timestamp": datetime.now().isoformat(),
            **adjustment
        }
        
        data["tuning_history"].append(adjustment_record)
        
        # Keep only last 500 adjustments
        if len(data["tuning_history"]) > 500:
            data["tuning_history"] = data["tuning_history"][-500:]
        
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=4)