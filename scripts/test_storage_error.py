import sys
import os
import logging

# Add root directory to sys.path BEFORE other imports
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root_path)

from data_vault.storage import StorageManager

logging.basicConfig(level=logging.INFO)

try:
    storage = StorageManager()
    print("Instance created")
    print(f"Testing get_statistics: {storage.get_statistics()}")
    print("Testing get_open_operations...")
    ops = storage.get_open_operations()
    print(f"Result: {len(ops)} operations found")
    print("Success")
except Exception as e:
    print(f"CRASH: {e}")
    import traceback
    traceback.print_exc()
