"""Concurrency resilience tests for scanner/system_db/audit critical path."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from data_vault.storage import StorageManager


def test_concurrent_transaction_audit_and_state_update(tmp_path: Path) -> None:
    db_path = tmp_path / "lock_cascade_resilience.sqlite"
    storage = StorageManager(db_path=str(db_path))

    worker_count = 24

    def _worker(idx: int) -> str:
        key = f"stress_key_{idx}"
        trace = f"SRE_LOCK_{idx:03d}"
        with storage.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sys_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (key, str(idx)),
            )
            conn.execute(
                """
                INSERT INTO sys_audit_logs
                    (user_id, action, resource, resource_id, status, reason, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SYSTEM",
                    "CONCURRENCY_STRESS",
                    "lock_cascade",
                    str(idx),
                    "success",
                    "transaction+audit+state_update",
                    trace,
                ),
            )
        return trace

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        traces = list(pool.map(_worker, range(worker_count)))

    audit_rows = storage.execute_query(
        "SELECT trace_id FROM sys_audit_logs WHERE action = ?",
        ("CONCURRENCY_STRESS",),
    )
    trace_set = {row["trace_id"] for row in audit_rows}

    config_rows = storage.execute_query(
        "SELECT key, value FROM sys_config WHERE key LIKE 'stress_key_%'",
        (),
    )

    assert len(trace_set) == worker_count
    assert all(trace in trace_set for trace in traces)
    assert len(config_rows) == worker_count
