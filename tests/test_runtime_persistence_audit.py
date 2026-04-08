from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "utilities"))

from runtime_persistence_audit import (  # type: ignore
    RULE_COMMIT,
    RULE_CONNECT,
    scan_runtime_violations,
)


def test_detects_sqlite_connect_outside_manager_driver(tmp_path: Path) -> None:
    (tmp_path / "core_brain").mkdir(parents=True)
    (tmp_path / "data_vault").mkdir(parents=True)

    (tmp_path / "core_brain" / "bad_runtime.py").write_text(
        "import sqlite3\nconn = sqlite3.connect('x.db')\n",
        encoding="utf-8",
    )
    (tmp_path / "data_vault" / "database_manager.py").write_text(
        "import sqlite3\nconn = sqlite3.connect('ok.db')\n",
        encoding="utf-8",
    )

    violations = scan_runtime_violations(tmp_path)
    connect_violations = [v for v in violations if v.rule == RULE_CONNECT]

    assert len(connect_violations) == 1
    assert connect_violations[0].file == "core_brain/bad_runtime.py"


def test_detects_manual_commit_in_runtime_write_paths(tmp_path: Path) -> None:
    (tmp_path / "data_vault").mkdir(parents=True)

    (tmp_path / "data_vault" / "market_db.py").write_text(
        "def save(conn):\n    conn.commit()\n",
        encoding="utf-8",
    )
    (tmp_path / "data_vault" / "database_manager.py").write_text(
        "def tx(conn):\n    conn.commit()\n",
        encoding="utf-8",
    )

    violations = scan_runtime_violations(tmp_path)
    commit_violations = [v for v in violations if v.rule == RULE_COMMIT]

    assert len(commit_violations) == 1
    assert commit_violations[0].file == "data_vault/market_db.py"
