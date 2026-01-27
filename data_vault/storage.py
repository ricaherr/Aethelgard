import json
import os
from datetime import date, datetime
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
            "system_state": {}
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
            "metadata": getattr(signal, 'metadata', {})
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