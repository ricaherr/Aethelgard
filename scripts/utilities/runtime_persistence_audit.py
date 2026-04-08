#!/usr/bin/env python3
"""Runtime persistence enforcement audit.

Rules enforced:
1. sqlite3.connect outside manager/driver is forbidden in runtime paths.
2. Manual commit() calls in runtime write paths are forbidden.

The audit supports a baseline file to freeze current technical debt and fail only
on newly introduced violations.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

RULE_CONNECT = "sqlite_connect_outside_manager_driver"
RULE_COMMIT = "manual_commit_runtime_write"

RUNTIME_DIRS = (
    "core_brain",
    "data_vault",
    "connectors",
)

EXCLUDED_PARTS = {
    "tests",
    "scripts",
    "docs",
    "ui",
    "governance",
    "venv",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}

ALLOWED_CONNECT_FILES = {
    "data_vault/database_manager.py",
    "data_vault/drivers/sqlite_driver.py",
}

ALLOWED_COMMIT_FILES = {
    "data_vault/database_manager.py",
    "data_vault/drivers/sqlite_driver.py",
}

DEFAULT_BASELINE = Path("governance/baselines/runtime_persistence_baseline.json")


@dataclass(frozen=True)
class Violation:
    rule: str
    file: str
    line: int
    code: str

    @property
    def signature(self) -> str:
        return f"{self.rule}|{self.file}|{self.code.strip()}"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_runtime_python_file(workspace_root: Path, file_path: Path) -> bool:
    if file_path.suffix != ".py":
        return False
    rel = file_path.relative_to(workspace_root)
    rel_parts = set(rel.parts)
    if rel_parts.intersection(EXCLUDED_PARTS):
        return False
    return any(rel.parts and rel.parts[0] == runtime_dir for runtime_dir in RUNTIME_DIRS)


def _collect_python_files(workspace_root: Path) -> list[Path]:
    files: list[Path] = []
    for py_file in workspace_root.rglob("*.py"):
        if _is_runtime_python_file(workspace_root, py_file):
            files.append(py_file)
    return sorted(files)


def _sqlite_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    module_aliases: set[str] = set()
    direct_connect_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == "sqlite3":
                    module_aliases.add(imported.asname or imported.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                for imported in node.names:
                    if imported.name == "connect":
                        direct_connect_names.add(imported.asname or imported.name)
    return module_aliases, direct_connect_names


def _find_violations_in_file(workspace_root: Path, file_path: Path) -> list[Violation]:
    rel_file = file_path.relative_to(workspace_root).as_posix()
    source = file_path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=rel_file)
    except SyntaxError:
        return []

    sqlite_module_aliases, direct_connect_names = _sqlite_aliases(tree)
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        code = ast.get_source_segment(source, node) or ""

        # Rule 1: sqlite3.connect outside manager/driver.
        is_direct_connect_call = False
        if isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id in sqlite_module_aliases
                and node.func.attr == "connect"
            ):
                is_direct_connect_call = True
        elif isinstance(node.func, ast.Name) and node.func.id in direct_connect_names:
            is_direct_connect_call = True

        if is_direct_connect_call and rel_file not in ALLOWED_CONNECT_FILES:
            violations.append(
                Violation(
                    rule=RULE_CONNECT,
                    file=rel_file,
                    line=getattr(node, "lineno", 0),
                    code=code or "sqlite3.connect(...)",
                )
            )

        # Rule 2: manual commit() in runtime write paths.
        if isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
            if rel_file not in ALLOWED_COMMIT_FILES:
                violations.append(
                    Violation(
                        rule=RULE_COMMIT,
                        file=rel_file,
                        line=getattr(node, "lineno", 0),
                        code=code or "conn.commit()",
                    )
                )

    return violations


def scan_runtime_violations(workspace_root: Path | None = None) -> list[Violation]:
    root = workspace_root or _workspace_root()
    violations: list[Violation] = []
    for py_file in _collect_python_files(root):
        violations.extend(_find_violations_in_file(root, py_file))
    return sorted(violations, key=lambda v: (v.rule, v.file, v.line, v.code))


def save_baseline(baseline_file: Path, violations: Iterable[Violation]) -> None:
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "trace_id": "DB-POLICY-RUNTIME-ENFORCEMENT-2026-04-07",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "violations": [asdict(v) for v in violations],
    }
    baseline_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_baseline_signatures(baseline_file: Path) -> set[str]:
    if not baseline_file.exists():
        return set()
    payload = json.loads(baseline_file.read_text(encoding="utf-8"))
    signatures: set[str] = set()
    for item in payload.get("violations", []):
        rule = str(item.get("rule", ""))
        file = str(item.get("file", ""))
        code = str(item.get("code", "")).strip()
        if rule and file and code:
            signatures.add(f"{rule}|{file}|{code}")
    return signatures


def detect_new_violations(current: Iterable[Violation], baseline_signatures: set[str]) -> list[Violation]:
    return [v for v in current if v.signature not in baseline_signatures]


def _print_grouped(title: str, violations: list[Violation]) -> None:
    print(f"\n{title}: {len(violations)}")
    if not violations:
        print("  - none")
        return
    for violation in violations:
        print(
            f"  - [{violation.rule}] {violation.file}:{violation.line} -> {violation.code.strip()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime persistence audit")
    parser.add_argument(
        "--baseline-file",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to baseline JSON file",
    )
    parser.add_argument(
        "--init-baseline",
        action="store_true",
        help="Generate or overwrite baseline with current violations",
    )
    args = parser.parse_args()

    root = _workspace_root()
    baseline_file = args.baseline_file
    if not baseline_file.is_absolute():
        baseline_file = root / baseline_file

    current = scan_runtime_violations(root)
    _print_grouped("Current violations", current)

    if args.init_baseline:
        save_baseline(baseline_file, current)
        print(f"\nBaseline initialized at: {baseline_file}")
        return 0

    baseline_signatures = load_baseline_signatures(baseline_file)
    if not baseline_signatures:
        print(f"\nBaseline missing or empty: {baseline_file}")
        print("Run with --init-baseline to freeze current surface.")
        return 1

    new_violations = detect_new_violations(current, baseline_signatures)
    _print_grouped("New violations vs baseline", new_violations)

    if new_violations:
        print("\n[FAIL] Runtime persistence enforcement detected new violations.")
        return 1

    print("\n[OK] Runtime persistence enforcement: no new violations against baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
