"""
tenant_factory.py — TenantDBFactory: Multi-Tenant Storage Selector (HU 8.1)
Trace_ID: SAAS-BACKBONE-2026-001

Responsibility:
    Given a tenant_id, return the isolated StorageManager that points to
    data_vault/tenants/{tenant_id}/aethelgard.db

    If the DB doesn't exist yet, it is provisioned automatically (schema +
    migrations + seeds) before the StorageManager is instantiated.

Rules:
    - NO imports from connectors/, core_brain/, or models/.
    - The global StorageManager (no tenant context) is unaffected.
    - Thread-safe singleton cache per tenant_id.
"""
import logging
import os
import threading
from typing import Dict, Optional

from .storage import StorageManager
from .schema import provision_tenant_db

logger = logging.getLogger(__name__)

# Default base path — resolved relative to this file's directory (data_vault/).
_DEFAULT_BASE_PATH = os.path.dirname(os.path.abspath(__file__))


class TenantDBFactory:
    """
    Factory & Registry of per-tenant StorageManagers.

    Usage (production):
        storage = TenantDBFactory.get_storage(tenant_id)
        storage.save_signal(...)

    The calling code never knows other tenants exist.
    """

    # Thread-safe singleton cache: tenant_id → StorageManager
    _instances: Dict[str, StorageManager] = {}
    _lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def get_storage(
        cls,
        tenant_id: str,
        base_path: Optional[str] = None,
    ) -> StorageManager:
        """
        Return the private StorageManager for `tenant_id`.

        Auto-provisions a new isolated DB if it doesn't exist yet.
        Subsequent calls with the same tenant_id return the cached instance.

        Args:
            tenant_id:  Unique identifier for the tenant (user UUID or slug).
            base_path:  Root directory that hosts the `tenants/` folder.
                        Defaults to `data_vault/` (where this file lives).
                        Override only in tests.

        Returns:
            A fully initialised StorageManager bound to the tenant's private DB.
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")

        # Fast path — no lock needed if already cached
        if tenant_id in cls._instances:
            return cls._instances[tenant_id]

        with cls._lock:
            # Double-checked locking
            if tenant_id in cls._instances:
                return cls._instances[tenant_id]

            db_path = cls._resolve_db_path(tenant_id, base_path)
            cls._ensure_provisioned(tenant_id, db_path)

            storage = StorageManager(db_path=db_path)
            cls._instances[tenant_id] = storage

            logger.info("[TENANT] Storage ready for tenant='%s' → %s", tenant_id, db_path)
            return storage

    @classmethod
    def release(cls, tenant_id: str) -> None:
        """
        Evict `tenant_id` from the cache.

        The next call to get_storage() will create a fresh instance.
        Useful on logout, tenant deletion, or forced reload.

        Safe to call even if tenant_id is not cached (no-op).
        """
        with cls._lock:
            instance = cls._instances.pop(tenant_id, None)
            if instance is not None:
                # Close persistent connection if present (e.g. :memory: or tests)
                if hasattr(instance, '_persistent_conn') and instance._persistent_conn:
                    try:
                        instance._persistent_conn.close()
                    except Exception:
                        pass
                logger.info("[TENANT] Released cache for tenant='%s'", tenant_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _resolve_db_path(cls, tenant_id: str, base_path: Optional[str]) -> str:
        """Build the canonical path for a tenant's private DB file."""
        root = os.path.abspath(base_path) if base_path else _DEFAULT_BASE_PATH
        return os.path.join(root, "tenants", tenant_id, "aethelgard.db")

    @classmethod
    def _ensure_provisioned(cls, tenant_id: str, db_path: str) -> None:
        """Create and initialise the tenant DB if it doesn't already exist."""
        if not os.path.isfile(db_path):
            logger.info(
                "[TENANT] New tenant detected — provisioning DB for '%s'...", tenant_id
            )
            provision_tenant_db(db_path)
