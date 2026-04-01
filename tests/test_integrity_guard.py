"""
Tests TDD para IntegrityGuard
==============================

Convención: test_<componente>_<comportamiento>

Cobertura:
  - Check_Database: OK / CRITICAL
  - Check_Data_Coherence: OK / WARNING (sin datos) / CRITICAL (tick viejo)
  - Check_Veto_Logic: OK / WARNING (1-2 ceros) / CRITICAL (3+ ceros consecutivos)
  - check_health: agregación + reset de streak
  - _emit_health_log: nivel de log correcto según overall status
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core_brain.services.integrity_guard import (
    HealthStatus,
    IntegrityGuard,
    _ADX_ZERO_COUNT_THRESHOLD,
    _TICK_STALENESS_SECONDS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_storage(sys_config: dict) -> MagicMock:
    """Crea un StorageManager mock con get_sys_config() configurado."""
    storage = MagicMock()
    storage.get_sys_config.return_value = sys_config
    return storage


def _fresh_tick_ts() -> str:
    """Timestamp de hace 30 segundos (tick fresco)."""
    return (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()


def _stale_tick_ts() -> str:
    """Timestamp de hace 10 minutos (tick congelado)."""
    return (datetime.now(timezone.utc) - timedelta(seconds=_TICK_STALENESS_SECONDS + 120)).isoformat()


# ── Check_Database ────────────────────────────────────────────────────────────

class TestCheckDatabase:

    def test_integrity_guard_check_database_ok_cuando_config_es_dict(self):
        storage = _make_storage({"some_key": "value"})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_database("trace-001")
        assert result.status == HealthStatus.OK
        assert "DB conectada" in result.message

    def test_integrity_guard_check_database_critical_cuando_storage_lanza_excepcion(self):
        storage = MagicMock()
        storage.get_sys_config.side_effect = Exception("connection refused")
        guard = IntegrityGuard(storage=storage)
        result = guard._check_database("trace-002")
        assert result.status == HealthStatus.CRITICAL
        assert "Fallo de conectividad" in result.message

    def test_integrity_guard_check_database_critical_cuando_retorna_no_dict(self):
        storage = _make_storage([])  # type: ignore[arg-type]
        storage.get_sys_config.return_value = None  # No es un dict
        guard = IntegrityGuard(storage=storage)
        result = guard._check_database("trace-003")
        assert result.status == HealthStatus.CRITICAL

    def test_integrity_guard_check_database_mide_elapsed_ms(self):
        storage = _make_storage({"k": "v"})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_database("trace-004")
        assert result.elapsed_ms >= 0


# ── Check_Data_Coherence ──────────────────────────────────────────────────────

class TestCheckDataCoherence:

    def test_integrity_guard_check_data_coherence_ok_con_tick_fresco(self):
        storage = _make_storage({"last_market_tick_ts": _fresh_tick_ts()})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_data_coherence("trace-010")
        assert result.status == HealthStatus.OK
        assert "fresco" in result.message

    def test_integrity_guard_check_data_coherence_warning_sin_clave_de_tick(self):
        storage = _make_storage({})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_data_coherence("trace-011")
        assert result.status == HealthStatus.WARNING
        assert "last_market_tick_ts" in result.message

    def test_integrity_guard_check_data_coherence_warning_con_tick_viejo(self):
        # Broker offline / arranque tras sesión anterior → estado operacional válido, no fallo
        storage = _make_storage({"last_market_tick_ts": _stale_tick_ts()})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_data_coherence("trace-012")
        assert result.status == HealthStatus.WARNING
        assert "desactualizado" in result.message.lower()

    def test_integrity_guard_check_data_coherence_critical_con_ts_invalido(self):
        storage = _make_storage({"last_market_tick_ts": "not-a-datetime"})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_data_coherence("trace-013")
        assert result.status == HealthStatus.CRITICAL

    def test_integrity_guard_check_data_coherence_acepta_ts_naive_como_utc(self):
        naive_ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)).isoformat()
        storage = _make_storage({"last_market_tick_ts": naive_ts})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_data_coherence("trace-014")
        assert result.status == HealthStatus.OK


# ── Check_Veto_Logic ──────────────────────────────────────────────────────────

class TestCheckVetoLogic:

    def _guard_with_adx(self, adx_value) -> IntegrityGuard:
        config = {"dynamic_params": {"adx": adx_value}}
        return IntegrityGuard(storage=_make_storage(config))

    def test_integrity_guard_check_veto_logic_ok_con_adx_valido(self):
        guard = self._guard_with_adx(25.5)
        result = guard._check_veto_logic("trace-020")
        assert result.status == HealthStatus.OK
        assert "25.5" in result.message

    def test_integrity_guard_check_veto_logic_warning_con_un_cero(self):
        guard = self._guard_with_adx(0)
        result = guard._check_veto_logic("trace-021")
        assert result.status == HealthStatus.WARNING
        assert guard._adx_zero_streak == 1

    def test_integrity_guard_check_veto_logic_warning_con_dos_ceros_consecutivos(self):
        guard = self._guard_with_adx(0)
        guard._check_veto_logic("trace-022a")
        result = guard._check_veto_logic("trace-022b")
        assert result.status == HealthStatus.WARNING
        assert guard._adx_zero_streak == 2

    def test_integrity_guard_check_veto_logic_critical_con_tres_ceros_consecutivos(self):
        guard = self._guard_with_adx(0)
        for _ in range(_ADX_ZERO_COUNT_THRESHOLD):
            result = guard._check_veto_logic("trace-023")
        assert result.status == HealthStatus.CRITICAL
        assert str(_ADX_ZERO_COUNT_THRESHOLD) in result.message

    def test_integrity_guard_check_veto_logic_reset_streak_cuando_adx_valido(self):
        guard = self._guard_with_adx(0)
        guard._check_veto_logic("trace-024a")
        guard._check_veto_logic("trace-024b")
        # ADX vuelve a ser válido
        guard._storage.get_sys_config.return_value = {"dynamic_params": {"adx": 18.0}}
        guard._check_veto_logic("trace-024c")
        assert guard._adx_zero_streak == 0

    def test_integrity_guard_check_veto_logic_critical_con_adx_none(self):
        guard = IntegrityGuard(storage=_make_storage({"dynamic_params": {}}))
        for _ in range(_ADX_ZERO_COUNT_THRESHOLD):
            result = guard._check_veto_logic("trace-025")
        assert result.status == HealthStatus.CRITICAL

    def test_integrity_guard_check_veto_logic_acepta_clave_ADX_mayuscula(self):
        storage = _make_storage({"dynamic_params": {"ADX": 30.0}})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_veto_logic("trace-026")
        assert result.status == HealthStatus.OK

    def test_integrity_guard_check_veto_logic_parsea_dynamic_params_como_json_string(self):
        params_str = json.dumps({"adx": 22.0})
        storage = _make_storage({"dynamic_params": params_str})
        guard = IntegrityGuard(storage=storage)
        result = guard._check_veto_logic("trace-027")
        assert result.status == HealthStatus.OK


# ── check_health (agregación) ─────────────────────────────────────────────────

class TestCheckHealth:

    def _all_ok_storage(self) -> MagicMock:
        return _make_storage({
            "last_market_tick_ts": _fresh_tick_ts(),
            "dynamic_params": {"adx": 20.0},
        })

    def test_integrity_guard_check_health_overall_ok_cuando_todos_ok(self):
        guard = IntegrityGuard(storage=self._all_ok_storage())
        report = guard.check_health()
        assert report.overall == HealthStatus.OK
        assert len(report.checks) == 3

    def test_integrity_guard_check_health_overall_critical_cuando_hay_un_check_critical(self):
        # Timestamp inválido = corrupción real de DB → CRITICAL (tick viejo = sólo WARNING)
        storage = _make_storage({
            "last_market_tick_ts": "not-a-datetime",   # CRITICAL: corrupción de datos
            "dynamic_params": {"adx": 20.0},
        })
        guard = IntegrityGuard(storage=storage)
        report = guard.check_health()
        assert report.overall == HealthStatus.CRITICAL

    def test_integrity_guard_check_health_overall_warning_sin_nivel_critical(self):
        storage = _make_storage({
            # sin last_market_tick_ts → WARNING en coherence
            "dynamic_params": {"adx": 20.0},
        })
        guard = IntegrityGuard(storage=storage)
        report = guard.check_health()
        assert report.overall == HealthStatus.WARNING

    def test_integrity_guard_check_health_tiene_trace_id_y_timestamp(self):
        guard = IntegrityGuard(storage=self._all_ok_storage())
        report = guard.check_health()
        assert report.trace_id
        assert report.timestamp

    def test_integrity_guard_check_health_log_nivel_critical_cuando_overall_critical(self):
        # Timestamp inválido = corrupción real → overall CRITICAL → log.critical() llamado
        storage = _make_storage({
            "last_market_tick_ts": "not-a-datetime",
            "dynamic_params": {"adx": 20.0},
        })
        guard = IntegrityGuard(storage=storage)
        with patch.object(
            __import__("core_brain.services.integrity_guard", fromlist=["logger"]).logger,
            "critical",
        ) as mock_critical:
            report = guard.check_health()
            assert report.overall == HealthStatus.CRITICAL
            mock_critical.assert_called_once()
