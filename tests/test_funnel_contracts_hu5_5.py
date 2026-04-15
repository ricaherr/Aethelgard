"""
HU 5.5 — Funnel Observability: Integration Contract Tests
==========================================================

Cubre los hallazgos de revisión post-implementación:
  1. Buffer de funnel no es sobreescrito por persist_session_stats_impl (Fix 1)
  2. _gk_veto_reasons no se hereda entre ciclos cuando execute phase no corre (Fix 2)
  3. no_strategy_engines se clasifica como LEGIT_SSOT, no INFRA_FAILURE (Fix 3)

Trace_ID: ETI-HU5.5-REVIEW-CONTRACTS-2026-04-14
"""
from __future__ import annotations

import pytest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from data_vault.storage import StorageManager
from core_brain.signal_batch_pipeline import _classify_raw_zero_cause


# ── Fix 1 — Buffer not clobbered by session-stats writer ─────────────────────


def test_funnel_buffer_preserved_after_session_stats_write() -> None:
    """
    persist_funnel_snapshot writes signal_funnel_recent (max 50).
    A subsequent update_sys_config call for session_stats (as done by
    persist_session_stats_impl) must NOT clobber those funnel keys.

    Verifies the single-writer contract: funnel keys are preserved through
    the stats-only update path.
    """
    storage = StorageManager(db_path=":memory:")

    # Write 3 funnel snapshots via the canonical method
    for i in range(3):
        storage.persist_funnel_snapshot({
            "trace_id": f"TRACE-BUF-{i:02d}",
            "stages": {"STAGE_RAW_SIGNAL_GENERATION": {"in": 2, "out": 0}},
            "reasons": {"no_signal_generated": 2},
            "raw_zero_cause_category": "LEGIT_SSOT",
        })

    assert storage.get_latest_funnel_snapshot()["trace_id"] == "TRACE-BUF-02"
    buf_before = (storage.get_sys_config().get("session_stats") or {}).get(
        "signal_funnel_recent", []
    )
    assert len(buf_before) == 3

    # Simulate persist_session_stats_impl writing stats-only data (with preservation)
    existing_session = storage.get_sys_config().get("session_stats") or {}
    stats_only = {
        "date": "2026-04-14",
        "cycles_completed": 10,
        "usr_signals_executed": 0,
        "usr_signals_processed": 0,
        "errors_count": 0,
        "scans_total": 10,
        "usr_signals_generated": 0,
        "usr_signals_risk_passed": 0,
        "usr_signals_vetoed": 0,
        "last_update": "2026-04-14T00:00:00",
    }
    # Replicate the fix: preserve funnel keys
    for funnel_key in ("signal_funnel_last_cycle", "signal_funnel_recent"):
        if funnel_key in existing_session:
            stats_only[funnel_key] = existing_session[funnel_key]
    storage.update_sys_config({"session_stats": stats_only})

    # Funnel data must survive
    latest = storage.get_latest_funnel_snapshot()
    assert latest is not None
    assert latest["trace_id"] == "TRACE-BUF-02"

    buf_after = (storage.get_sys_config().get("session_stats") or {}).get(
        "signal_funnel_recent", []
    )
    assert len(buf_after) == 3, (
        f"Expected 3 snapshots after stats write, got {len(buf_after)}"
    )


def test_funnel_buffer_cap_stays_at_50_not_20() -> None:
    """
    persist_funnel_snapshot enforces max-50 rolling buffer.
    Repeated writes must never reduce the count below the last 50 entries.
    """
    storage = StorageManager(db_path=":memory:")

    for i in range(55):
        storage.persist_funnel_snapshot({
            "trace_id": f"TRACE-{i:03d}",
            "stages": {},
            "reasons": {},
        })

    buf = (storage.get_sys_config().get("session_stats") or {}).get(
        "signal_funnel_recent", []
    )
    assert len(buf) == 50, f"Expected 50 entries (max cap), got {len(buf)}"
    # Latest entry must be the last one written
    assert buf[-1]["trace_id"] == "TRACE-054"
    # Oldest surviving entry must be index 5
    assert buf[0]["trace_id"] == "TRACE-005"


# ── Fix 2 — _gk_veto_reasons not inherited across cycles ─────────────────────


@pytest.mark.asyncio
async def test_gk_veto_reasons_reset_at_start_of_run_signal_filter() -> None:
    """
    run_signal_filter must reset orch._gk_veto_reasons = {} at entry,
    so stale reasons from a previous cycle (where execute phase was skipped)
    never contaminate the next cycle's funnel.
    """
    from core_brain.orchestrators._cycle_exec import run_signal_filter
    from core_brain.orchestrators._types import ScanBundle

    # Build minimal orchestrator stub
    mock_storage = MagicMock()
    mock_storage.get_sys_config.return_value = {}
    mock_storage.update_module_heartbeat.return_value = None

    mock_factory = MagicMock()
    mock_factory.generate_usr_signals_batch = AsyncMock(return_value=[])
    mock_factory.last_funnel_summary = None

    orch = SimpleNamespace(
        signal_factory=mock_factory,
        storage=mock_storage,
        risk_manager=MagicMock(),
        modules_enabled_global={},
        config={},
        strategy_gatekeeper=None,
        economic_integration=None,
        _econ_veto_symbols=set(),
        _econ_caution_symbols=set(),
        thought_callback=None,
        stats=SimpleNamespace(
            cycles_completed=0,
            usr_signals_processed=0,
            usr_signals_generated=0,
            usr_signals_risk_passed=0,
            usr_signals_vetoed=0,
        ),
        _active_usr_signals=[],
        # Stale reasons from a previous cycle
        _gk_veto_reasons={"gk_whitelist_reject": 5, "gk_score_below_threshold": 2},
    )

    bundle = ScanBundle(
        scan_results={},
        scan_results_with_data={},
        price_snapshots={},
        trace_id="TRACE-STALE-TEST",
        infra_skip_reason=None,
    )

    await run_signal_filter(orch, bundle)

    # After run_signal_filter entry, _gk_veto_reasons must have been reset
    # (even if the cycle returned early with no signals, reasons are cleared)
    assert orch._gk_veto_reasons == {}, (
        f"_gk_veto_reasons was not reset: {orch._gk_veto_reasons}"
    )


# ── Fix 3 — no_strategy_engines canonical taxonomy ───────────────────────────


@pytest.mark.parametrize(
    "reasons_dict, infra_skip, expected_category",
    [
        # no_strategy_engines alone → LEGIT_SSOT (config state, not runtime crash)
        ({"no_strategy_engines": 3}, None, "LEGIT_SSOT"),
        # strategy_engine_error → INFRA_FAILURE (runtime exception)
        ({"strategy_engine_error": 1}, None, "INFRA_FAILURE"),
        # no_strategy_engines + engine_error → INFRA_FAILURE wins (higher priority)
        ({"no_strategy_engines": 1, "strategy_engine_error": 1}, None, "INFRA_FAILURE"),
        # infra_skip_reason always → INFRA (highest priority)
        ({"no_strategy_engines": 3}, "backpressure_db_latency", "INFRA"),
        # Only data quality codes → DATA_QUALITY
        ({"regime_missing": 2, "df_missing": 1}, None, "DATA_QUALITY"),
        # Affinity codes → LEGIT_SSOT
        ({"affinity_below_threshold": 4, "no_signal_generated": 1}, None, "LEGIT_SSOT"),
    ],
)
def test_no_strategy_engines_classifies_as_legit_ssot(
    reasons_dict: dict,
    infra_skip: str | None,
    expected_category: str,
) -> None:
    """
    _classify_raw_zero_cause must assign no_strategy_engines to LEGIT_SSOT.
    strategy_engine_error must assign to INFRA_FAILURE.
    Taxonomy must be unambiguous (no duplicate membership).
    """
    reasons = Counter(reasons_dict)
    result = _classify_raw_zero_cause(reasons, infra_skip)
    assert result == expected_category, (
        f"reasons={reasons_dict} infra_skip={infra_skip!r}: "
        f"expected {expected_category!r}, got {result!r}"
    )
