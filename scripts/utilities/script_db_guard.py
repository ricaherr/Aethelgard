"""
POLÍTICA DE GOBERNANZA: Manejo Seguro de Bases de Datos Temporales
==================================================================
Este módulo provee herramientas para que los scripts utilitarios gestionen
bases de datos temporales de forma segura, garantizando cleanup aunque ocurra
un error.

Rutas PERMITIDAS en producción:
  - data_vault/global/aethelgard.db   (DB del sistema)
  - data_vault/global/auth.db         (DB de autenticación)
  - data_vault/templates/usr_template.db
  - data_vault/tenants/{id}/aethelgard.db
  - backups/  (archivos de backup)

Cualquier otro archivo .db fuera de estas rutas es RESIDUAL y debe eliminarse.
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Sequence

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Prefijos de paths PERMITIDOS relativos a PROJECT_ROOT
_ALLOWED_PREFIXES: tuple[Path, ...] = (
    PROJECT_ROOT / "data_vault" / "global",
    PROJECT_ROOT / "data_vault" / "templates",
    PROJECT_ROOT / "data_vault" / "tenants",
    PROJECT_ROOT / "backups",
)

# Nombres de archivo que NUNCA deben eliminarse
_PROTECTED_FILENAMES: frozenset[str] = frozenset({"aethelgard.db", "auth.db", "usr_template.db"})


def is_allowed_db_path(db_path: Path) -> bool:
    """Devuelve True si db_path está dentro de una ruta permitida."""
    resolved = db_path.resolve()
    return any(resolved.is_relative_to(prefix.resolve()) for prefix in _ALLOWED_PREFIXES)


def find_residual_dbs(search_root: Path | None = None) -> list[Path]:
    """
    Escanea el proyecto y devuelve los archivos .db que están FUERA
    de las rutas permitidas (i.e. son residuos).

    Excluye venv, .venv, node_modules y __pycache__.
    """
    root = search_root or PROJECT_ROOT
    residuals: list[Path] = []
    excluded_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git"}

    for db_file in root.rglob("*.db"):
        # Saltar directorios excluidos
        if any(part in excluded_dirs for part in db_file.parts):
            continue
        if not is_allowed_db_path(db_file):
            residuals.append(db_file)

    return sorted(residuals)


def purge_residual_dbs(
    search_root: Path | None = None,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """
    Elimina todos los archivos .db residuales fuera de rutas permitidas.

    Args:
        search_root: Directorio raíz de búsqueda (default: PROJECT_ROOT).
        dry_run: Si True, solo reporta sin eliminar.

    Returns:
        Lista de paths eliminados (o que se eliminarían en dry_run).
    """
    residuals = find_residual_dbs(search_root)
    removed: list[Path] = []

    for db_path in residuals:
        try:
            if dry_run:
                logger.warning("[DRY-RUN] DB residual detectada: %s", db_path)
            else:
                db_path.unlink(missing_ok=True)
                # Eliminar también WAL y SHM si existen
                for suffix in ("-wal", "-shm"):
                    side = db_path.with_name(db_path.name + suffix)
                    side.unlink(missing_ok=True)
                logger.info("[CLEANUP] DB residual eliminada: %s", db_path)
            removed.append(db_path)
        except OSError as exc:
            logger.error("[CLEANUP] No se pudo eliminar %s: %s", db_path, exc)

    return removed


@contextmanager
def temp_db(
    db_path: Path,
    *,
    description: str = "temporal",
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager que abre una conexión SQLite temporal y garantiza
    que el archivo sea eliminado al finalizar, incluso si ocurre un error.

    USO EXCLUSIVO en scripts de diagnóstico/test — NUNCA en rutas productivas.

    Example::

        with temp_db(Path("/tmp/my_test.db"), description="diagnóstico X") as conn:
            conn.execute("CREATE TABLE t (id INTEGER)")

    Args:
        db_path: Ruta del archivo temporal. Debe estar FUERA de las rutas
                 permitidas; si está dentro lanzará ValueError para proteger
                 datos reales.
        description: Nombre descriptivo para los logs.
    """
    if is_allowed_db_path(db_path):
        raise ValueError(
            f"temp_db() no puede usarse sobre una ruta de producción: {db_path}. "
            "Use StorageManager() en su lugar."
        )

    logger.debug("[TEMP-DB] Creando DB temporal '%s' en %s", description, db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        _remove_db_file(db_path)
        logger.debug("[TEMP-DB] DB temporal '%s' eliminada", description)


def _remove_db_file(db_path: Path) -> None:
    """Elimina db_path y sus archivos WAL/SHM asociados."""
    for target in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("[CLEANUP] No se pudo eliminar %s: %s", target, exc)


def audit_and_warn(search_root: Path | None = None) -> list[Path]:
    """
    Detecta DBs residuales y emite advertencias sin eliminar nada.
    Útil para scripts que quieren solo reportar, no actuar.

    Returns:
        Lista de paths residuales detectados.
    """
    residuals = find_residual_dbs(search_root)
    for path in residuals:
        logger.warning(
            "[AUDIT] DB fuera de ruta permitida: %s — "
            "Ejecutar purge_residual_dbs() o stop.py para limpiar.",
            path,
        )
    return residuals
