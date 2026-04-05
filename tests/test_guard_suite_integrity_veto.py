"""
Regression tests for guard suite integrity veto persistence.

Ensures INTEGRITY_VETO uses a unique audit trace_id to avoid collisions
with RESILIENCE_EVENT records that share the same parent trace.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from core_brain.orchestrators._guard_suite import write_integrity_veto


class _CriticalStatus:
    value = "CRITICAL"


class _Check:
    def __init__(self, name: str, message: str) -> None:
        self.name = name
        self.message = message
        self.status = _CriticalStatus()


def test_write_integrity_veto_uses_unique_audit_trace_id() -> None:
    conn = MagicMock()
    storage = MagicMock()
    storage._get_conn.return_value = conn
    orch = SimpleNamespace(storage=storage)

    parent_trace = "EDGE-ABC123"
    checks = [_Check("Check_Veto_Logic", "ADX zero streak")]

    write_integrity_veto(orch, parent_trace, checks)

    assert conn.execute.called
    _, params = conn.execute.call_args[0]

    reason = params[5]
    audit_trace = params[6]

    assert "parent_trace_id=EDGE-ABC123" in reason
    assert audit_trace != parent_trace
    assert ":IV:" in audit_trace
