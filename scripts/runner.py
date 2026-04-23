#!/usr/bin/env python3
"""
RUNNER — Ejecutor Central de Scripts Utilitarios
=================================================
Ejecuta cualquier script utilitario de Aethelgard con las siguientes garantías:

  1. Post-ejecución: escanea el proyecto en busca de archivos .db fuera de
     las rutas permitidas y los elimina automáticamente.
  2. Registra en log cada acción de cleanup realizada.
  3. Emite advertencia si el script no implementó su propio cleanup.

POLÍTICA DE GOBERNANZA:
  - Rutas permitidas: data_vault/global/, data_vault/templates/,
                      data_vault/tenants/, backups/
  - Cualquier otro .db es RESIDUAL y se elimina.

Uso:
    python scripts/runner.py <ruta_del_script> [args...]

Ejemplos:
    python scripts/runner.py scripts/utilities/purge_database.py
    python scripts/runner.py scripts/diagnose_db_lock.py
"""

import logging
import subprocess
import sys
from pathlib import Path

# Asegurar que el proyecto esté en sys.path
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utilities.script_db_guard import audit_and_warn, purge_residual_dbs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("runner")

_SEPARATOR = "=" * 70


def _run_script(script_path: Path, extra_args: list[str]) -> int:
    """Ejecuta el script como subproceso y devuelve su exit code."""
    cmd = [sys.executable, str(script_path)] + extra_args
    logger.info("Ejecutando: %s", " ".join(cmd))
    print(_SEPARATOR)
    result = subprocess.run(cmd, cwd=str(_PROJECT_ROOT))
    print(_SEPARATOR)
    return result.returncode


def _post_run_audit() -> list[Path]:
    """
    Detecta y elimina DBs residuales tras la ejecución del script.
    Devuelve la lista de archivos eliminados.
    """
    residuals = audit_and_warn()
    if not residuals:
        logger.info("[AUDIT] Sin DBs residuales detectadas. OK.")
        return []

    logger.warning(
        "[AUDIT] Se detectaron %d DB(s) residual(es). Procediendo con cleanup...",
        len(residuals),
    )
    removed = purge_residual_dbs()
    for path in removed:
        logger.info("[CLEANUP] Eliminada: %s", path)

    if len(removed) < len(residuals):
        failed = set(residuals) - set(removed)
        for path in failed:
            logger.error("[CLEANUP] No se pudo eliminar: %s", path)

    return removed


def run(script_path: Path, extra_args: list[str] | None = None) -> int:
    """
    Punto de entrada principal del runner.

    Args:
        script_path: Ruta al script a ejecutar.
        extra_args: Argumentos adicionales para el script.

    Returns:
        Exit code del script ejecutado.
    """
    args = extra_args or []

    if not script_path.exists():
        logger.error("Script no encontrado: %s", script_path)
        return 1

    print(f"\n{_SEPARATOR}")
    print("  AETHELGARD RUNNER")
    print(f"  Script: {script_path.relative_to(_PROJECT_ROOT)}")
    print(_SEPARATOR)

    exit_code = _run_script(script_path, args)

    print(f"\n[>] Auditoría post-ejecución de DBs residuales...")
    removed = _post_run_audit()

    if removed:
        print(f"  [OK] {len(removed)} DB(s) residual(es) eliminada(s):")
        for path in removed:
            print(f"       - {path}")
    else:
        print("  [OK] Sin residuos de base de datos.")

    print(f"\n[EXIT CODE] {exit_code}")
    print(_SEPARATOR + "\n")

    return exit_code


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    script_path = Path(sys.argv[1])
    if not script_path.is_absolute():
        script_path = _PROJECT_ROOT / script_path

    extra_args = sys.argv[2:]
    sys.exit(run(script_path, extra_args))


if __name__ == "__main__":
    main()
