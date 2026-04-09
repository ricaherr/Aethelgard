"""
broker_accounts_db.py — BrokerAccountsMixin for usr_broker_accounts CRUD operations.

Architecture: Per-tenant execution accounts (trader's own REAL/DEMO accounts).
Separation from sys_broker_accounts (system DEMO accounts for data feeds/SHADOW mode).

Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5
Reference: docs/01_IDENTITY_SECURITY.md — Section "Broker Account Management"
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from .base_repo import BaseRepository

logger: logging.Logger = logging.getLogger(__name__)


class BrokerAccountsMixin(BaseRepository):
    """
    Mixin for usr_broker_accounts CRUD operations.
    All methods enforce user_id isolation — a trader can only access their own accounts.
    """

    def get_user_broker_account(
        self,
        user_id: str,
        broker_name: str,
        account_status: str = "ACTIVE",
    ) -> Optional[Dict[str, Any]]:
        """
        Returns the active broker account for a user + broker combination.
        Returns None if no matching account exists.

        Args:
            user_id: The authenticated trader's user_id
            broker_name: Broker identifier (e.g. 'mt5', 'ctrader', 'fix_prime')
            account_status: Filter by status (default: ACTIVE)
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM usr_broker_accounts
                WHERE user_id = ? AND broker_name = ? AND account_status = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, broker_name, account_status),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as exc:
            logger.error(
                "[BrokerAccountsMixin] get_user_broker_account error user=%s broker=%s: %s",
                user_id, broker_name, exc,
            )
            return None
        finally:
            self._close_conn(conn)

    def list_user_broker_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Returns all broker accounts for a user (regardless of status).
        Used for the trader's account management UI.

        Args:
            user_id: The authenticated trader's user_id
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM usr_broker_accounts WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            rows: List[Any] = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error(
                "[BrokerAccountsMixin] list_user_broker_accounts error user=%s: %s",
                user_id, exc,
            )
            return []
        finally:
            self._close_conn(conn)

    def save_user_broker_account(
        self,
        user_id: str,
        broker_name: str,
        broker_account_id: str,
        account_type: str = "DEMO",
        account_status: str = "ACTIVE",
        credentials_encrypted: Optional[str] = None,
        daily_loss_limit: Optional[float] = None,
        max_position_size: Optional[float] = None,
        max_open_positions: int = 3,
        balance: Optional[float] = None,
        equity: Optional[float] = None,
    ) -> Optional[str]:
        """
        Inserts or updates a broker account for a user.
        Returns the account id on success, None on failure.

        Uses INSERT OR REPLACE with UNIQUE(user_id, broker_name, broker_account_id)
        to ensure idempotent upserts.
        """
        def _write(conn: sqlite3.Connection) -> Optional[str]:
            cursor: sqlite3.Cursor = conn.cursor()
            now: str = datetime.now(timezone.utc).isoformat()

            # Check if exists (to reuse id on update)
            cursor.execute(
                """
                SELECT id FROM usr_broker_accounts
                WHERE user_id = ? AND broker_name = ? AND broker_account_id = ?
                """,
                (user_id, broker_name, broker_account_id),
            )
            existing = cursor.fetchone()
            account_id: Optional[str] = cast(Optional[str], existing[0]) if existing else None

            if account_id:
                # Update existing
                cursor.execute(
                    """
                    UPDATE usr_broker_accounts SET
                        account_type = ?,
                        account_status = ?,
                        credentials_encrypted = COALESCE(?, credentials_encrypted),
                        daily_loss_limit = COALESCE(?, daily_loss_limit),
                        max_position_size = COALESCE(?, max_position_size),
                        max_open_positions = ?,
                        balance = COALESCE(?, balance),
                        equity = COALESCE(?, equity),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        account_type, account_status, credentials_encrypted,
                        daily_loss_limit, max_position_size, max_open_positions,
                        balance, equity, now, account_id,
                    ),
                )
            else:
                # Insert new — let DB generate id via DEFAULT
                cursor.execute(
                    """
                    INSERT INTO usr_broker_accounts
                        (user_id, broker_name, broker_account_id, account_type, account_status,
                         credentials_encrypted, daily_loss_limit, max_position_size,
                         max_open_positions, balance, equity, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, broker_name, broker_account_id, account_type, account_status,
                        credentials_encrypted, daily_loss_limit, max_position_size,
                        max_open_positions, balance, equity, now, now,
                    ),
                )
                # Retrieve the generated id
                cursor.execute(
                    "SELECT id FROM usr_broker_accounts WHERE user_id=? AND broker_name=? AND broker_account_id=?",
                    (user_id, broker_name, broker_account_id),
                )
                row = cursor.fetchone()
                account_id = cast(Optional[str], row[0]) if row else None
            return account_id

        try:
            result: str | None = self._execute_serialized(_write)
            logger.debug(
                "[BrokerAccountsMixin] Saved account user=%s broker=%s account_id=%s",
                user_id, broker_name, broker_account_id,
            )
            return result
        except Exception as exc:
            logger.error(
                "[BrokerAccountsMixin] save_user_broker_account error user=%s broker=%s: %s",
                user_id, broker_name, exc,
            )
            return None

    def update_broker_account_status(
        self,
        account_id: str,
        user_id: str,
        status: str,
    ) -> bool:
        """
        Updates the status of a broker account.
        Enforces ownership: only updates if account belongs to user_id.

        Args:
            account_id: The account's UUID
            user_id: Must match account's user_id (ownership check)
            status: New status ('ACTIVE', 'SUSPENDED', 'CLOSED')
        """
        VALID_STATUSES: set[str] = {"ACTIVE", "SUSPENDED", "CLOSED"}
        if status not in VALID_STATUSES:
            logger.warning(
                "[BrokerAccountsMixin] Invalid status '%s'. Must be one of %s",
                status, VALID_STATUSES,
            )
            return False

        def _update(conn: sqlite3.Connection) -> bool:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE usr_broker_accounts
                SET account_status = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (status, datetime.now(timezone.utc).isoformat(), account_id, user_id),
            )
            return cursor.rowcount > 0

        try:
            updated: bool = self._execute_serialized(_update)
            if updated:
                logger.info(
                    "[BrokerAccountsMixin] Account %s status → %s (user=%s)",
                    account_id, status, user_id,
                )
            else:
                logger.warning(
                    "[BrokerAccountsMixin] update_broker_account_status: account %s not found for user %s",
                    account_id, user_id,
                )
            return bool(updated)
        except Exception as exc:
            logger.error(
                "[BrokerAccountsMixin] update_broker_account_status error: %s", exc
            )
            return False
