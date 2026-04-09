#!/usr/bin/env python3
"""
[AUDIT] DOCUMENTATION + GOVERNANCE STYLE AUDIT.

Checks:
1. Required governance/engineering files exist.
2. BACKLOG contains no completed HU entries ([DONE]) because it must track pending work only.
3. SPRINT task lines only use allowed states: [TODO], [DEV], [DONE].
4. ROADMAP does not keep archived epics (currently E17 is expected archived).
5. SYSTEM_LEDGER includes archived E17 entry after closure.
"""
import sys
from pathlib import Path
import io
import re

# Fix encoding for Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ALLOWED_SPRINT_STATES = {"TODO", "DEV", "DONE"}


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _check_file_presence(workspace_root: Path) -> list[str]:
    required_files = [
        "governance/BACKLOG.md",
        "governance/ROADMAP.md",
        "governance/SPRINT.md",
        "docs/AETHELGARD_MANIFESTO.md",
        "docs/DEVELOPMENT_GUIDELINES.md",
        "governance/SYSTEM_LEDGER.md",
    ]

    issues: list[str] = []
    for rel_path in required_files:
        full_path = workspace_root / rel_path
        if full_path.exists():
            print(f"OK FOUND: {rel_path}")
        else:
            issues.append(f"MISSING: {rel_path}")
    return issues


def _check_backlog_pending_only(backlog_path: Path) -> list[str]:
    issues: list[str] = []
    lines = _read_lines(backlog_path)
    for idx, line in enumerate(lines, start=1):
        # Real HU entries in BACKLOG use: * **HU X.Y ...** [STATE]
        if re.search(r"^\*\s+\*\*HU\s+\d+\.\d+.*\[DONE\]", line):
            issues.append(
                f"BACKLOG contains completed HU at line {idx}: completed HUs must be archived in SYSTEM_LEDGER"
            )
    return issues


def _check_sprint_states(sprint_path: Path) -> list[str]:
    issues: list[str] = []
    lines = _read_lines(sprint_path)
    for idx, line in enumerate(lines, start=1):
        match = re.search(r"^-\s+\[(?P<state>[^\]]+)\]\s+\*\*HU\s+\d+\.\d+", line)
        if not match:
            continue
        state = match.group("state").strip().upper()
        if state not in ALLOWED_SPRINT_STATES:
            issues.append(
                f"SPRINT invalid state at line {idx}: [{state}] (allowed: [TODO], [DEV], [DONE])"
            )
    return issues


def _check_epic_sync(roadmap_path: Path, ledger_path: Path) -> list[str]:
    issues: list[str] = []
    roadmap_text = roadmap_path.read_text(encoding="utf-8", errors="replace")
    ledger_text = ledger_path.read_text(encoding="utf-8", errors="replace")

    # Current governance decision: E17 was completed and archived.
    if "### E17:" in roadmap_text:
        issues.append("ROADMAP still contains E17 as active/pending after archival")

    if "ÉPICA E17 COMPLETADA" not in ledger_text:
        issues.append("SYSTEM_LEDGER missing archived entry for E17")

    return issues


def check_documentation() -> int:
    workspace_root = Path(__file__).parent.parent.parent
    issues: list[str] = []

    print("\n" + "="*80)
    print("AETHELGARD DOCUMENTATION + GOVERNANCE STYLE AUDIT")
    print("="*80)

    issues.extend(_check_file_presence(workspace_root))

    backlog = workspace_root / "governance/BACKLOG.md"
    sprint = workspace_root / "governance/SPRINT.md"
    roadmap = workspace_root / "governance/ROADMAP.md"
    ledger = workspace_root / "governance/SYSTEM_LEDGER.md"

    if backlog.exists():
        issues.extend(_check_backlog_pending_only(backlog))
    if sprint.exists():
        issues.extend(_check_sprint_states(sprint))
    if roadmap.exists() and ledger.exists():
        issues.extend(_check_epic_sync(roadmap, ledger))

    if not issues:
        print("\nSUCCESS: Governance documentation is present and synchronized with style rules.")
        return 0

    print(f"\nFAILED: {len(issues)} governance issue(s) detected.")
    for issue in issues:
        print(f"  - {issue}")
    return 1

if __name__ == "__main__":
    sys.exit(check_documentation())
