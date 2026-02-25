"""
Aethelgard Workspace Cleanup
=============================
Purges temporary artifacts from the filesystem.

Scope:
  - __pycache__/ directories (recursive)
  - *.pyc bytecode files (recursive)
  - .tmp / .bak accidental files
  - Reports orphan JSON files in data_vault/

Does NOT handle:
  - DB backups  → managed by DatabaseBackupManager
  - Log rotation → managed by TimedRotatingFileHandler + _rotate_stale_log()

Usage:
  python scripts/workspace_cleanup.py           # Execute cleanup
  python scripts/workspace_cleanup.py --dry-run  # Preview only
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

# Project root = parent of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories to skip entirely
SKIP_DIRS = {"venv", ".venv", "node_modules", ".git"}

# Temp file extensions to purge
TEMP_EXTENSIONS = {".pyc", ".pyo", ".tmp", ".bak"}

# Directories considered temp artifacts
TEMP_DIRS = {"__pycache__"}


def _should_skip(path: Path) -> bool:
    """Check if path is inside a directory we should skip."""
    return any(part in SKIP_DIRS for part in path.parts)


def find_pycache_dirs(root: Path) -> list[Path]:
    """Find all __pycache__ directories recursively."""
    results = []
    for dirpath, dirnames, _ in os.walk(root):
        # Prune skipped dirs from walk
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        current = Path(dirpath)
        if current.name in TEMP_DIRS and not _should_skip(current):
            results.append(current)
    return results


def find_temp_files(root: Path) -> list[Path]:
    """Find temporary files by extension recursively."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        current = Path(dirpath)
        if _should_skip(current):
            continue
        for fname in filenames:
            fpath = current / fname
            if fpath.suffix.lower() in TEMP_EXTENSIONS:
                results.append(fpath)
    return results


def find_orphan_json(data_vault: Path) -> list[Path]:
    """Detect orphan JSON files in data_vault/ (report only)."""
    if not data_vault.exists():
        return []
    return [f for f in data_vault.glob("*.json") if f.is_file()]


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def get_total_size(path: Path) -> int:
    """Get total size of a file or directory."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def run_cleanup(dry_run: bool = False) -> dict:
    """Execute workspace cleanup and return summary."""
    label = "[DRY-RUN]" if dry_run else "[CLEANUP]"

    print(f"\n{'=' * 60}")
    print(f"  AETHELGARD WORKSPACE CLEANUP {'(Preview Mode)' if dry_run else ''}")
    print(f"{'=' * 60}")
    print(f"  Root: {PROJECT_ROOT}\n")

    stats = {
        "dirs_removed": 0,
        "files_removed": 0,
        "bytes_recovered": 0,
        "orphans_detected": 0,
    }

    # 1. Purge __pycache__/ directories
    pycache_dirs = find_pycache_dirs(PROJECT_ROOT)
    if pycache_dirs:
        print(f"📁 __pycache__/ directories: {len(pycache_dirs)}")
        for d in pycache_dirs:
            size = get_total_size(d)
            rel = d.relative_to(PROJECT_ROOT)
            print(f"   {label} {rel}/ ({format_size(size)})")
            stats["bytes_recovered"] += size
            stats["dirs_removed"] += 1
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
    else:
        print("📁 __pycache__/ directories: none found")

    # 2. Purge temp files
    temp_files = find_temp_files(PROJECT_ROOT)
    # Filter out files already inside pycache dirs (already deleted above)
    temp_files = [f for f in temp_files if not any(
        str(f).startswith(str(d)) for d in pycache_dirs
    )]
    if temp_files:
        print(f"\n📄 Temp files ({', '.join(TEMP_EXTENSIONS)}): {len(temp_files)}")
        for f in temp_files:
            size = f.stat().st_size if f.exists() else 0
            rel = f.relative_to(PROJECT_ROOT)
            print(f"   {label} {rel} ({format_size(size)})")
            stats["bytes_recovered"] += size
            stats["files_removed"] += 1
            if not dry_run:
                f.unlink(missing_ok=True)
    else:
        print(f"\n📄 Temp files ({', '.join(TEMP_EXTENSIONS)}): none found")

    # 3. Detect orphan JSON files in data_vault/
    data_vault = PROJECT_ROOT / "data_vault"
    orphans = find_orphan_json(data_vault)
    if orphans:
        print(f"\n⚠️  Orphan JSON files in data_vault/ (report only):")
        for f in orphans:
            size = f.stat().st_size
            print(f"   ⚠️  {f.name} ({format_size(size)})")
            stats["orphans_detected"] += 1
    else:
        print(f"\n✅ No orphan JSON files in data_vault/")

    # Summary
    print(f"\n{'─' * 60}")
    print(f"  SUMMARY {'(no changes made)' if dry_run else ''}")
    print(f"{'─' * 60}")
    print(f"  Directories removed: {stats['dirs_removed']}")
    print(f"  Files removed:       {stats['files_removed']}")
    print(f"  Space recovered:     {format_size(stats['bytes_recovered'])}")
    if stats["orphans_detected"]:
        print(f"  Orphans detected:    {stats['orphans_detected']} (manual review needed)")
    print()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aethelgard Workspace Cleanup - Purge temporary artifacts"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without executing them"
    )
    args = parser.parse_args()
    run_cleanup(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
