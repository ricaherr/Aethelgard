"""
Tests for user broker accounts (usr_broker_accounts) implementation.
Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5
"""
import pytest
from data_vault.storage import StorageManager


@pytest.fixture
def storage():
    """In-memory storage for testing"""
    mgr = StorageManager(db_path=":memory:")
    # sys_users needs an admin to fulfill the foreign key in usr_broker_accounts
    conn = mgr._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sys_users (id, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("admin-user-123", "admin@aethelgard.com", "hash", "admin")
    )
    cursor.execute(
        "INSERT INTO sys_users (id, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("trader-user-456", "trader@aethelgard.com", "hash", "trader")
    )
    conn.commit()
    return mgr


class TestUserBrokerAccounts:
    """TDD suite for usr_broker_accounts CRUD via BrokerAccountsMixin"""

    def test_save_new_user_broker_account(self, storage):
        """Test inserting a new REAL account for a user"""
        account_id = storage.save_user_broker_account(
            user_id="trader-user-456",
            broker_name="ctrader",
            broker_account_id="857412",
            account_type="REAL",
            balance=10000.0,
            equity=10000.0
        )
        assert account_id is not None
        assert isinstance(account_id, str)

        acc = storage.get_user_broker_account("trader-user-456", "ctrader")
        assert acc is not None
        assert acc["broker_account_id"] == "857412"
        assert acc["account_type"] == "REAL"
        assert acc["account_status"] == "ACTIVE"
        assert acc["balance"] == 10000.0

    def test_update_existing_account(self, storage):
        """Test updating an existing account idempotently"""
        # Insert
        storage.save_user_broker_account(
            user_id="trader-user-456",
            broker_name="mt5",
            broker_account_id="login123",
            balance=500.0
        )
        
        # Update balance
        account_id = storage.save_user_broker_account(
            user_id="trader-user-456",
            broker_name="mt5",
            broker_account_id="login123",
            balance=650.0  # New balance
        )
        assert account_id is not None

        acc = storage.get_user_broker_account("trader-user-456", "mt5")
        assert acc["balance"] == 650.0
        # Assert type remains the default (DEMO)
        assert acc["account_type"] == "DEMO"

    def test_get_user_broker_account_isolation(self, storage):
        """Test getting account enforces user_id isolation"""
        storage.save_user_broker_account(
            user_id="trader-user-456",
            broker_name="fix_prime",
            broker_account_id="FIX-A"
        )
        
        # Admin tries to access trader's account (should return None via this specific method)
        admin_acc = storage.get_user_broker_account("admin-user-123", "fix_prime")
        assert admin_acc is None

        # Trader accesses their own
        trader_acc = storage.get_user_broker_account("trader-user-456", "fix_prime")
        assert trader_acc is not None

    def test_list_user_broker_accounts(self, storage):
        """Test listing all accounts for a user"""
        storage.save_user_broker_account("trader-user-456", "mt5", "A")
        storage.save_user_broker_account("trader-user-456", "ctrader", "B")
        storage.save_user_broker_account("admin-user-123", "mt5", "C")

        trader_accounts = storage.list_user_broker_accounts("trader-user-456")
        assert len(trader_accounts) == 2
        names = {acc["broker_name"] for acc in trader_accounts}
        assert names == {"mt5", "ctrader"}

    def test_update_broker_account_status(self, storage):
        """Test status update and validation"""
        account_id = storage.save_user_broker_account(
            user_id="trader-user-456",
            broker_name="ctrader",
            broker_account_id="X1"
        )

        # Update to valid status
        success = storage.update_broker_account_status(account_id, "trader-user-456", "SUSPENDED")
        assert success is True

        acc = storage.get_user_broker_account("trader-user-456", "ctrader", account_status="SUSPENDED")
        assert acc is not None
        
        # ACTIVE filter should return None now
        acc_active = storage.get_user_broker_account("trader-user-456", "ctrader", account_status="ACTIVE")
        assert acc_active is None

        # Update to invalid status
        success_invalid = storage.update_broker_account_status(account_id, "trader-user-456", "INVALID_STATUS")
        assert success_invalid is False

    def test_update_status_ownership(self, storage):
        """Test status update respects user ownership"""
        account_id = storage.save_user_broker_account(
            user_id="trader-user-456",
            broker_name="ctrader",
            broker_account_id="X1"
        )

        # Admin tries to suspend trader's account using the regular user API
        success = storage.update_broker_account_status(account_id, "admin-user-123", "SUSPENDED")
        assert success is False  # Ownership check fails

        # Original account is still ACTIVE
        acc = storage.get_user_broker_account("trader-user-456", "ctrader", account_status="ACTIVE")
        assert acc is not None
