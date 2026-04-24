"""
Architecture guard — HU 2.1 (Épica E2)

Verifies that core_brain/ and scripts/ never import MT5-specific symbols directly.
Only connectors/ and tests/ are permitted to reference MT5 implementations.

This test acts as a regression gate: if any future commit re-introduces a
forbidden import, the test fails immediately in CI before the code ships.
"""
import ast
import os
import textwrap
from pathlib import Path
from typing import Sequence

import pytest

PROJECT_ROOT = Path(__file__).parent.parent

# Modules that must NEVER appear as top-level or deferred imports in these dirs
FORBIDDEN_IMPORTS = {
    "MetaTrader5",
    "mt5",          # bare 'import mt5' form
}
FORBIDDEN_FROM_MODULES = {
    "connectors.mt5_connector",
    "connectors.mt5_wrapper",   # raw wrapper (only scripts/ may use it)
    "connectors.mt5_data_provider",
    "connectors.mt5_event_adapter",
    "connectors.mt5_discovery",
}

# Directories subject to the prohibition
GUARDED_DIRS = [
    PROJECT_ROOT / "core_brain",
]

# Specific script files that had direct MetaTrader5 imports — now cleaned
GUARDED_SCRIPT_FILES = [
    PROJECT_ROOT / "scripts" / "utilities" / "verify_risk_calculation.py",
    PROJECT_ROOT / "scripts" / "utilities" / "backfill_trade_metadata.py",
    PROJECT_ROOT / "scripts" / "utilities" / "backfill_position_metadata.py",
]

# Allowlist: files inside guarded dirs that are explicitly permitted
# (e.g. generated stubs, vendor code). Keep empty unless there is a DOCUMENTED reason.
ALLOWLISTED_FILES: set[Path] = set()


def _collect_python_files(directories: Sequence[Path]) -> list[Path]:
    files = []
    for directory in directories:
        if directory.is_dir():
            files.extend(
                p for p in directory.rglob("*.py")
                if "__pycache__" not in p.parts
            )
    return files


def _parse_imports(source: str) -> list[tuple[str, str]]:
    """
    Return list of (kind, name) tuples for every import in *source*.

    kind is 'import' or 'from', name is the module/symbol string.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append(("import", alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            results.append(("from", module))
    return results


def _check_file(path: Path) -> list[str]:
    """Return list of violation descriptions found in *path*."""
    if path in ALLOWLISTED_FILES:
        return []

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    violations = []
    imports = _parse_imports(source)

    for kind, name in imports:
        if kind == "import" and name.split(".")[0] in FORBIDDEN_IMPORTS:
            violations.append(f"  Direct import '{name}'")
        if kind == "from" and name in FORBIDDEN_FROM_MODULES:
            violations.append(f"  'from {name} import ...'")

    return violations


def _build_report(file_violations: dict[Path, list[str]]) -> str:
    lines = ["", "ARCHITECTURE VIOLATION — MT5 imports detected outside connectors/:", ""]
    for path, viols in file_violations.items():
        rel = path.relative_to(PROJECT_ROOT)
        lines.append(f"  {rel}:")
        lines.extend(viols)
    lines += [
        "",
        "RULE: Only connectors/ may import MT5-specific modules.",
        "      Use connectors.connector_factory.build_connector_from_account()",
        "      or models.symbol_utils.normalize_symbol() in business logic.",
    ]
    return "\n".join(lines)


class TestArchitectureNoMT5InCore:
    """Ensure core_brain/ is free of direct MT5 connector imports."""

    def test_core_brain_has_no_forbidden_mt5_imports(self):
        files = _collect_python_files([PROJECT_ROOT / "core_brain"])
        violations: dict[Path, list[str]] = {}

        for path in files:
            viols = _check_file(path)
            if viols:
                violations[path] = viols

        if violations:
            pytest.fail(textwrap.dedent(_build_report(violations)))

    def test_guarded_scripts_have_no_raw_metatrader5_import(self):
        """Specific utility scripts must not import MetaTrader5 directly."""
        violations: dict[Path, list[str]] = {}

        for path in GUARDED_SCRIPT_FILES:
            if not path.exists():
                continue
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            imports = _parse_imports(source)
            viols = []
            for kind, name in imports:
                if kind == "import" and name == "MetaTrader5":
                    viols.append(f"  Direct 'import MetaTrader5' — use connectors.mt5_wrapper instead")
            if viols:
                violations[path] = viols

        if violations:
            pytest.fail(textwrap.dedent(_build_report(violations)))

    def test_symbol_utils_is_importable(self):
        """Sanity-check that the normalize_symbol utility exists and works."""
        from models.symbol_utils import normalize_symbol

        assert normalize_symbol("USDJPY=X") == "USDJPY"
        assert normalize_symbol("GBPUSD=X") == "GBPUSD"
        assert normalize_symbol("EURUSD") == "EURUSD"
        assert normalize_symbol("") == ""

    def test_connector_factory_is_importable(self):
        """Sanity-check that ConnectorFactory module exists."""
        from connectors.connector_factory import build_connector_from_account  # noqa: F401
