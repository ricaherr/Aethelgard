"""
Pytest configuration file.
Ensures the project root is in sys.path for imports.
Provides shared fixtures for all tests.
"""
import sys
from pathlib import Path
import pytest
from data_vault.storage import StorageManager

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def storage(tmp_path):
    """
    Create temporary in-memory database for testing.
    
    Ensures test isolation - each test gets fresh database.
    """
    db_path = tmp_path / "test_db.db"
    return StorageManager(db_path=str(db_path))
