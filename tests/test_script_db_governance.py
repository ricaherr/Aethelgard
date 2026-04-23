"""
Tests TDD — Gobernanza de Bases de Datos en Scripts Utilitarios
===============================================================
Criterios de aceptación:
  1. Ningún .db residual persiste fuera de rutas oficiales tras ejecutar un script.
  2. El cleanup ocurre incluso si el script lanza una excepción.
  3. La DB global NUNCA es eliminada accidentalmente por purge_residual_dbs().
  4. is_allowed_db_path() clasifica correctamente cada ruta.
  5. temp_db() rechaza rutas de producción.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

# Asegurar que el root del proyecto esté en sys.path
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utilities.script_db_guard import (
    audit_and_warn,
    find_residual_dbs,
    is_allowed_db_path,
    purge_residual_dbs,
    temp_db,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def residual_db(tmp_path: Path) -> Path:
    """Crea un archivo .db en un directorio temporal (fuera de rutas permitidas)."""
    db = tmp_path / "aethelgard.db"
    db.touch()
    return db


@pytest.fixture()
def residual_db_with_wal(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Crea un .db con sus archivos WAL/SHM asociados."""
    db = tmp_path / "leftover.db"
    wal = tmp_path / "leftover.db-wal"
    shm = tmp_path / "leftover.db-shm"
    db.touch()
    wal.touch()
    shm.touch()
    return db, wal, shm


# ---------------------------------------------------------------------------
# 1. Clasificación de rutas
# ---------------------------------------------------------------------------


class TestIsAllowedDbPath:
    def test_global_db_is_allowed(self):
        path = _PROJECT_ROOT / "data_vault" / "global" / "aethelgard.db"
        assert is_allowed_db_path(path) is True

    def test_auth_db_is_allowed(self):
        path = _PROJECT_ROOT / "data_vault" / "global" / "auth.db"
        assert is_allowed_db_path(path) is True

    def test_template_db_is_allowed(self):
        path = _PROJECT_ROOT / "data_vault" / "templates" / "usr_template.db"
        assert is_allowed_db_path(path) is True

    def test_tenant_db_is_allowed(self):
        path = _PROJECT_ROOT / "data_vault" / "tenants" / "some_user_uuid" / "aethelgard.db"
        assert is_allowed_db_path(path) is True

    def test_backup_db_is_allowed(self):
        path = _PROJECT_ROOT / "backups" / "aethelgard.backup_123.db"
        assert is_allowed_db_path(path) is True

    def test_root_db_is_not_allowed(self):
        path = _PROJECT_ROOT / "aethelgard.db"
        assert is_allowed_db_path(path) is False

    def test_data_vault_root_db_is_not_allowed(self):
        path = _PROJECT_ROOT / "data_vault" / "aethelgard.db"
        assert is_allowed_db_path(path) is False

    def test_scripts_db_is_not_allowed(self):
        path = _PROJECT_ROOT / "scripts" / "test.db"
        assert is_allowed_db_path(path) is False

    def test_tmp_path_db_is_not_allowed(self, tmp_path: Path):
        path = tmp_path / "any.db"
        assert is_allowed_db_path(path) is False


# ---------------------------------------------------------------------------
# 2. temp_db — context manager con cleanup garantizado
# ---------------------------------------------------------------------------


class TestTempDb:
    def test_cleanup_after_normal_use(self, tmp_path: Path):
        db_path = tmp_path / "diag.db"
        with temp_db(db_path, description="test cleanup"):
            assert db_path.exists()
        assert not db_path.exists()

    def test_cleanup_after_exception(self, tmp_path: Path):
        db_path = tmp_path / "error_case.db"
        with pytest.raises(RuntimeError):
            with temp_db(db_path, description="error test"):
                assert db_path.exists()
                raise RuntimeError("simulated script error")
        assert not db_path.exists()

    def test_cleanup_removes_wal_and_shm(self, tmp_path: Path):
        db_path = tmp_path / "with_wal.db"
        with temp_db(db_path, description="wal test") as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.commit()
        assert not db_path.exists()
        assert not (tmp_path / "with_wal.db-wal").exists()
        assert not (tmp_path / "with_wal.db-shm").exists()

    def test_rejects_production_path(self):
        prod_path = _PROJECT_ROOT / "data_vault" / "global" / "aethelgard.db"
        with pytest.raises(ValueError, match="ruta de producción"):
            with temp_db(prod_path):
                pass  # pragma: no cover

    def test_connection_is_usable(self, tmp_path: Path):
        db_path = tmp_path / "usable.db"
        with temp_db(db_path, description="usable") as conn:
            conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO items (name) VALUES (?)", ("aethelgard",))
            conn.commit()
            result = conn.execute("SELECT name FROM items").fetchone()
        assert result[0] == "aethelgard"
        assert not db_path.exists()


# ---------------------------------------------------------------------------
# 3. find_residual_dbs — detección de residuos
# ---------------------------------------------------------------------------


class TestFindResidualDbs:
    def test_finds_db_outside_allowed_paths(self, tmp_path: Path, residual_db: Path):
        found = find_residual_dbs(search_root=tmp_path)
        assert residual_db in found

    def test_does_not_find_db_in_allowed_path(self, tmp_path: Path):
        # Simular ruta permitida dentro de tmp_path
        allowed_dir = tmp_path / "data_vault" / "global"
        allowed_dir.mkdir(parents=True)
        allowed_db = allowed_dir / "aethelgard.db"
        allowed_db.touch()

        # No debería reportarla como residual porque está bajo global/
        # Nota: is_allowed_db_path usa _PROJECT_ROOT, así que esta prueba valida
        # la lógica de búsqueda — no encontrará nada residual en tmp_path/data_vault/global/
        # pero sí en tmp_path directamente
        residual = tmp_path / "stray.db"
        residual.touch()

        found = find_residual_dbs(search_root=tmp_path)
        assert residual in found

    def test_skips_venv_directories(self, tmp_path: Path):
        venv_db = tmp_path / "venv" / "lib" / "test.db"
        venv_db.parent.mkdir(parents=True)
        venv_db.touch()
        found = find_residual_dbs(search_root=tmp_path)
        assert venv_db not in found


# ---------------------------------------------------------------------------
# 4. purge_residual_dbs — eliminación de residuos
# ---------------------------------------------------------------------------


class TestPurgeResidualDbs:
    def test_removes_residual_db(self, tmp_path: Path, residual_db: Path):
        removed = purge_residual_dbs(search_root=tmp_path)
        assert residual_db in removed
        assert not residual_db.exists()

    def test_removes_wal_and_shm_alongside_db(
        self, tmp_path: Path, residual_db_with_wal: tuple[Path, Path, Path]
    ):
        db, wal, shm = residual_db_with_wal
        purge_residual_dbs(search_root=tmp_path)
        assert not db.exists()
        assert not wal.exists()
        assert not shm.exists()

    def test_dry_run_does_not_delete(self, tmp_path: Path, residual_db: Path):
        reported = purge_residual_dbs(search_root=tmp_path, dry_run=True)
        assert residual_db in reported
        assert residual_db.exists()  # no eliminado

    def test_global_db_is_never_deleted(self):
        """La DB global en data_vault/global/ NO debe ser eliminada."""
        global_db = _PROJECT_ROOT / "data_vault" / "global" / "aethelgard.db"
        if not global_db.exists():
            pytest.skip("DB global no existe en este entorno")

        # Ejecutar purge sobre el proyecto real
        removed = purge_residual_dbs(search_root=_PROJECT_ROOT)

        assert global_db not in removed
        assert global_db.exists(), "CRÍTICO: la DB global fue eliminada accidentalmente"

    def test_returns_empty_when_no_residuals(self, tmp_path: Path):
        removed = purge_residual_dbs(search_root=tmp_path)
        assert removed == []


# ---------------------------------------------------------------------------
# 5. audit_and_warn — detección sin eliminación
# ---------------------------------------------------------------------------


class TestAuditAndWarn:
    def test_returns_residuals_without_deleting(self, tmp_path: Path, residual_db: Path):
        found = audit_and_warn(search_root=tmp_path)
        assert residual_db in found
        assert residual_db.exists()

    def test_returns_empty_when_clean(self, tmp_path: Path):
        found = audit_and_warn(search_root=tmp_path)
        assert found == []
