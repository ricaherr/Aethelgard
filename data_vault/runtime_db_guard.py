"""Runtime guard for direct sqlite3.connect usage.

Objective: block new direct runtime connections outside approved files.
"""

from __future__ import annotations

import inspect
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

RULE_CONNECT = "sqlite_connect_outside_manager_driver"

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = WORKSPACE_ROOT / "governance" / "baselines" / "runtime_persistence_baseline.json"

ALWAYS_ALLOWED_CALLERS = {
    "data_vault/database_manager.py",
    "data_vault/drivers/sqlite_driver.py",
}

_ORIGINAL_CONNECT = sqlite3.connect
_GUARD_INSTALLED = False


def _normalize_path(path: str) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _load_legacy_allowed_callers(baseline_file: Path) -> set[str]:
    if not baseline_file.exists():
        return set()
    try:
        payload = json.loads(baseline_file.read_text(encoding="utf-8"))
    except Exception:
        return set()

    allowed: set[str] = set()
    for item in payload.get("violations", []):
        if str(item.get("rule", "")) == RULE_CONNECT:
            candidate = str(item.get("file", ""))
            if candidate:
                allowed.add(candidate)
    return allowed


def _resolve_caller_file() -> str:
    this_file = Path(__file__).resolve()
    for frame in inspect.stack()[2:]:
        frame_path = Path(frame.filename).resolve()
        if frame_path == this_file:
            continue
        return _normalize_path(str(frame_path))
    return "<unknown>"


def _is_allowed_caller(caller_file: str, legacy_allowed: set[str]) -> bool:
    if caller_file in ALWAYS_ALLOWED_CALLERS:
        return True
    if caller_file in legacy_allowed:
        return True
    return False


def install_runtime_sqlite_guard(baseline_file: Path | None = None) -> None:
    """Install sqlite3.connect guard once per process.

    The guard allows:
    - manager/driver core files.
    - legacy direct-connect call sites captured in baseline.

    Any new direct runtime call site is blocked.
    """
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return

    # Pytest suites rely on in-memory sqlite3.connect in many tests.
    # Runtime enforcement must not mutate sqlite behavior for unit tests.
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return

    resolved_baseline = baseline_file or BASELINE_PATH
    if not resolved_baseline.is_absolute():
        resolved_baseline = (WORKSPACE_ROOT / resolved_baseline).resolve()

    legacy_allowed = _load_legacy_allowed_callers(resolved_baseline)

    def _guarded_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        caller_file = _resolve_caller_file()
        if not _is_allowed_caller(caller_file, legacy_allowed):
            raise RuntimeError(
                "Blocked direct sqlite3.connect call outside allowed runtime paths: "
                f"{caller_file}. Use DatabaseManager/driver contract."
            )
        return _ORIGINAL_CONNECT(*args, **kwargs)

    sqlite3.connect = _guarded_connect
    _GUARD_INSTALLED = True
