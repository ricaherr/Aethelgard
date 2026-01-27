"""
Pytest configuration file.
Ensures the project root is in sys.path for imports.
"""
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
