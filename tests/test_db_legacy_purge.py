"""
TDD — Legacy DB Purge & SSOT Enforcement
Trace_ID: DB-LEGACY-PURGE-2026-03-21

Verifies that no production code references or creates the legacy DB
at data_vault/aethelgard.db (without global/ or tenants/ subdirectory).
"""
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
LEGACY_DB_PATH = PROJECT_ROOT / "data_vault" / "aethelgard.db"
GLOBAL_DB_PATH = PROJECT_ROOT / "data_vault" / "global" / "aethelgard.db"


class TestLegacyDBAbsence:
    """Legacy DB file must not exist on disk."""

    def test_legacy_db_does_not_exist(self) -> None:
        """The file data_vault/aethelgard.db must not exist on disk."""
        assert not LEGACY_DB_PATH.exists(), (
            f"Legacy DB found at {LEGACY_DB_PATH}. "
            "Run the purge script or delete manually."
        )

    def test_global_db_exists(self) -> None:
        """data_vault/global/aethelgard.db must exist as the active global DB."""
        assert GLOBAL_DB_PATH.exists(), (
            f"Global DB not found at {GLOBAL_DB_PATH}. System is misconfigured."
        )


class TestBaseRepoFallbackPath:
    """BaseRepository fallback path must resolve to global DB, never legacy."""

    def test_base_repo_default_path_is_global(self) -> None:
        """Instantiating BaseRepository without db_path must resolve to global DB path."""
        sys.path.insert(0, str(PROJECT_ROOT))
        from data_vault.base_repo import BaseRepository

        repo = BaseRepository()
        resolved = Path(repo.db_path).resolve()
        assert "global" in resolved.parts, (
            f"BaseRepository default path {repo.db_path} does not include 'global/'. "
            "It would create/access the legacy DB."
        )
        assert resolved.name == "aethelgard.db"

    def test_base_repo_explicit_path_is_respected(self, tmp_path: Path) -> None:
        """Explicit db_path must be used as-is (DI contract)."""
        from data_vault.base_repo import BaseRepository

        explicit_path = str(tmp_path / "test.db")
        repo = BaseRepository(db_path=explicit_path)
        assert repo.db_path == explicit_path


class TestStrategyLoaderDefaultPath:
    """StrategyRegistry default db_path must point to global DB."""

    def test_strategy_loader_default_db_is_global(self) -> None:
        """StrategyRegistry without db_path must use data_vault/global/aethelgard.db."""
        from core_brain.strategy_loader import StrategyRegistry

        registry = StrategyRegistry()
        resolved = Path(registry.db_path).resolve()
        assert "global" in resolved.parts, (
            f"StrategyRegistry default db_path {registry.db_path} does not include 'global/'."
        )


class TestHealthManagerDBPath:
    """HealthManager must check the global DB path."""

    def test_health_manager_db_path_is_global(self) -> None:
        """HealthManager.db_path must point to data_vault/global/aethelgard.db."""
        from core_brain.health import HealthManager

        hm = HealthManager()
        assert "global" in str(hm.db_path), (
            f"HealthManager.db_path={hm.db_path} does not include 'global/'."
        )
        assert str(hm.db_path).endswith("aethelgard.db")


class TestStorageManagerFallbackPath:
    """StorageManager(user_id=None) must always resolve to global DB."""

    def test_storage_manager_no_args_resolves_to_global(self) -> None:
        """StorageManager() with no arguments must resolve to global/aethelgard.db."""
        from data_vault.storage import StorageManager

        sm = StorageManager()
        assert "global" in sm.db_path, (
            f"StorageManager() resolved to {sm.db_path}, not global DB."
        )
        assert sm.db_path.endswith("aethelgard.db")
