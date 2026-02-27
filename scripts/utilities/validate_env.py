"""
HU 10.2: Path Resilience — Environment Validation Script

Validates that the execution environment is stable and path-agnostic.
Returns exit code 0 on success, 1 on failure.
"""
import sys
import os
import subprocess
import tempfile
from pathlib import Path

# ANSI color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

CHECKS_PASSED = []
CHECKS_FAILED = []


def ok(msg: str) -> None:
    CHECKS_PASSED.append(msg)
    print(f"  {GREEN}✅{RESET} {msg}")


def fail(msg: str) -> None:
    CHECKS_FAILED.append(msg)
    print(f"  {RED}❌{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠️ {RESET} {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}── {title} ──{RESET}")


# ─── Check 1: Python Version ──────────────────────────────────────────────────

def check_python_version() -> None:
    section("Python Version")
    major, minor = sys.version_info.major, sys.version_info.minor
    if major >= 3 and minor >= 12:
        ok(f"Python {major}.{minor} — OK (>= 3.12 required)")
    else:
        fail(f"Python {major}.{minor} — FAIL (>= 3.12 required). Current: {sys.version}")


# ─── Check 2: Project Root Path Integrity ─────────────────────────────────────

def check_path_integrity() -> None:
    section("Path Integrity")
    # Use __file__ to find project root dynamically (agnostic to developer machine)
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[2]  # scripts/utilities/validate_env.py -> root

    path_str = str(project_root)

    # Check for spaces in path
    if " " in path_str:
        warn(f"Project path contains spaces: '{path_str}'")
        warn("This may cause issues with some tools. Recommend relocating to a path without spaces.")
    else:
        ok(f"Project path has no spaces: '{path_str}'")

    # Check for special characters (excluding normal separators and drive letters)
    import re
    special_chars_pattern = re.compile(r"[^\w\s/\\:.\-]")
    matches = special_chars_pattern.findall(path_str.replace(os.sep, "/"))
    if matches:
        fail(f"Special characters detected in path: {set(matches)}")
    else:
        ok("No special characters in project path")

    # Check directory exists and is readable
    if project_root.exists():
        ok(f"Project root exists: {project_root}")
    else:
        fail(f"Project root NOT found: {project_root}")

    return project_root


# ─── Check 3: Critical Directories ────────────────────────────────────────────

def check_critical_dirs(project_root: Path) -> None:
    section("Critical Directories")
    critical_dirs = [
        "core_brain",
        "data_vault",
        "tests",
        "models",
        "config",
        "connectors",
        "scripts",
        "governance",
    ]
    for d in critical_dirs:
        path = project_root / d
        if path.exists() and path.is_dir():
            ok(f"{d}/")
        else:
            fail(f"Missing critical directory: {d}/")


# ─── Check 4: Critical Files ──────────────────────────────────────────────────

def check_critical_files(project_root: Path) -> None:
    section("Critical Files")
    critical_files = [
        "start.py",
        "requirements.txt",
        "core_brain/risk_manager.py",
        "core_brain/risk_calculator.py",
        "data_vault/storage.py",
        "governance/ROADMAP.md",
        "governance/BACKLOG.md",
    ]
    for f in critical_files:
        path = project_root / f
        if path.exists():
            ok(f"{f}")
        else:
            fail(f"Missing critical file: {f}")


# ─── Check 5: Write Permissions ───────────────────────────────────────────────

def check_write_permissions(project_root: Path) -> None:
    section("Write Permissions")
    test_dirs = ["data_vault", "logs"]
    for d in test_dirs:
        target = project_root / d
        target.mkdir(parents=True, exist_ok=True)
        try:
            tmp = tempfile.NamedTemporaryFile(dir=target, delete=True, suffix=".tmp")
            tmp.close()
            ok(f"Write access: {d}/")
        except OSError as e:
            fail(f"Cannot write to {d}/: {e}")


# ─── Check 6: Critical Imports ────────────────────────────────────────────────

def check_imports() -> None:
    section("Python Dependencies")
    packages = {
        "fastapi": "FastAPI",
        "uvicorn": "Uvicorn",
        "pydantic": "Pydantic",
        "pytest": "Pytest",
        "jose": "python-jose (JWT)",
        "bcrypt": "bcrypt",
        "aiohttp": "aiohttp",
        "pandas": "pandas",
        "numpy": "numpy",
    }
    for module, label in packages.items():
        try:
            __import__(module)
            ok(f"{label}")
        except ImportError:
            fail(f"{label} — NOT INSTALLED. Run: pip install -r requirements.txt")


# ─── Check 7: Data Vault Tenant Structure ─────────────────────────────────────

def check_data_vault(project_root: Path) -> None:
    section("Data Vault Structure")
    data_vault = project_root / "data_vault"
    if not data_vault.exists():
        fail("data_vault/ directory missing")
        return

    tenants_dir = data_vault / "tenants"
    if tenants_dir.exists():
        tenants = [d for d in tenants_dir.iterdir() if d.is_dir()]
        ok(f"Tenant directories found: {len(tenants)}")
    else:
        warn("data_vault/tenants/ not yet created (normal for fresh install)")

    global_dir = data_vault / "global"
    if global_dir.exists():
        ok("data_vault/global/ exists")
    else:
        warn("data_vault/global/ not found — auth DB not yet created")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n{BOLD}{'=' * 55}{RESET}")
    print(f"{BOLD}  AETHELGARD — Environment Validation (HU 10.2){RESET}")
    print(f"{BOLD}{'=' * 55}{RESET}")

    check_python_version()
    project_root = check_path_integrity()

    if project_root:
        check_critical_dirs(project_root)
        check_critical_files(project_root)
        check_write_permissions(project_root)
        check_data_vault(project_root)

    check_imports()

    # ── Summary ──
    print(f"\n{BOLD}{'=' * 55}{RESET}")
    total = len(CHECKS_PASSED) + len(CHECKS_FAILED)
    if CHECKS_FAILED:
        print(f"{RED}{BOLD}  RESULT: FAIL — {len(CHECKS_FAILED)} check(s) failed out of {total}{RESET}")
        print(f"\n{RED}  Failed checks:{RESET}")
        for c in CHECKS_FAILED:
            print(f"    ✗ {c}")
        print(f"{BOLD}{'=' * 55}{RESET}\n")
        return 1
    else:
        print(f"{GREEN}{BOLD}  RESULT: OK — All {total} checks passed ✅{RESET}")
        print(f"{BOLD}{'=' * 55}{RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
