import json
import os

class StorageManager:
    """
    Manages persistence of system state to a local JSON file.
    A simple implementation for demonstration purposes.
    """
    def __init__(self, db_path='data_vault/system_state.json'):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            with open(self.db_path, 'w') as f:
                json.dump({}, f)

    def get_system_state(self) -> dict:
        """Retrieves the current system state from the database."""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def update_system_state(self, new_state: dict):
        """Updates and saves the system state."""
        current_state = self.get_system_state()
        current_state.update(new_state)
        with open(self.db_path, 'w') as f:
            json.dump(current_state, f, indent=4)