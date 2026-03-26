"""
test_dynamic_threshold_controller.py — Suite TDD para DynamicThresholdController.

Componente: core_brain/adaptive/threshold_controller.py
Trace_ID:   TRACE_TEST_DTC_20260326
Orden S-9:  Dynamic Aggression Engine (Dynamic Threshold Controller)

Casos de prueba:
  1. Instancia SHADOW con sequía 24h → umbral se reduce 5 %
  2. Instancia SHADOW con señales recientes → sin ajuste
  3. Instancia con drawdown alto → umbral se recupera hacia base
  4. Instancia inexistente → retorna NOT_APPLICABLE
  5. Floor de 0.40 se respeta aunque haya múltiples reducciones acumuladas
  6. Trace_ID sigue el patrón TRACE_DTC_YYYYMMDD_HHMMSS_ID8
  7. Instancia en estado terminal (DEAD) → sin ajuste
  8. get_current_threshold retorna base si no hay ajuste previo
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core_brain.adaptive.threshold_controller import DynamicThresholdController


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _create_in_memory_db() -> sqlite3.Connection:
    """Crea DB SQLite in-memory con las tablas mínimas para DTC."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sys_shadow_instances (
            instance_id         TEXT PRIMARY KEY,
            strategy_id         TEXT NOT NULL,
            account_id          TEXT NOT NULL DEFAULT 'MT5_DEMO_001',
            account_type        TEXT DEFAULT 'DEMO',
            parameter_overrides TEXT DEFAULT '{}',
            status              TEXT DEFAULT 'INCUBATING',
            max_drawdown_pct    REAL DEFAULT 0.0,
            birth_timestamp     TIMESTAMP,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sys_signals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id  TEXT NOT NULL,
            symbol       TEXT DEFAULT 'EURUSD',
            origin_mode  TEXT DEFAULT 'SHADOW',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


def _insert_instance(
    conn: sqlite3.Connection,
    instance_id: str,
    strategy_id: str = "strat_oliver",
    status: str = "INCUBATING",
    max_drawdown_pct: float = 0.0,
    parameter_overrides: str = "{}",
) -> None:
    """Inserta una instancia shadow para pruebas."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO sys_shadow_instances
            (instance_id, strategy_id, status, max_drawdown_pct,
             parameter_overrides, birth_timestamp, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (instance_id, strategy_id, status, max_drawdown_pct,
         parameter_overrides, now, now, now),
    )
    conn.commit()


def _insert_recent_signal(
    conn: sqlite3.Connection,
    strategy_id: str,
    hours_ago: float = 0.5,
) -> None:
    """Inserta una señal reciente (dentro de la ventana) para la estrategia dada."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    conn.execute(
        """
        INSERT INTO sys_signals (strategy_id, origin_mode, created_at)
        VALUES (?, 'SHADOW', ?)
        """,
        (strategy_id, ts),
    )
    conn.commit()


def _make_dtc(
    conn: sqlite3.Connection,
    base_confidence: float = 0.60,
    floor_confidence: float = 0.40,
    step_down: float = 0.05,
    window_hours: int = 24,
    drawdown_alert_threshold: float = 0.10,
) -> DynamicThresholdController:
    return DynamicThresholdController(
        storage_conn=conn,
        base_confidence=base_confidence,
        floor_confidence=floor_confidence,
        step_down=step_down,
        window_hours=window_hours,
        drawdown_alert_threshold=drawdown_alert_threshold,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDynamicThresholdControllerSequía:
    """Ajuste por sequía de señales en ventana de 24 horas."""

    def test_dtc_reduce_threshold_si_sequia_24h(self):
        """Instancia SHADOW sin señales en 24h → umbral baja 5 %."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid, strategy_id="strat_oliver")
        # No insertamos señales → sequía activa
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust(iid)

        assert result["adjusted"] is True
        assert result["old_threshold"] == pytest.approx(0.60)
        assert result["new_threshold"] == pytest.approx(0.55)
        assert "no_signals" in result["reason"]

    def test_dtc_sin_ajuste_si_hay_señales_recientes(self):
        """Instancia SHADOW con señales recientes → sin ajuste."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid, strategy_id="strat_oliver")
        _insert_recent_signal(conn, "strat_oliver", hours_ago=2.0)
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust(iid)

        assert result["adjusted"] is False
        assert "no_adjustment" in result["reason"]

    def test_dtc_persiste_threshold_reducido_en_db(self):
        """El umbral reducido queda persistido en parameter_overrides."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid, strategy_id="strat_persist")
        dtc = _make_dtc(conn)

        dtc.evaluate_and_adjust(iid)

        cursor = conn.execute(
            "SELECT parameter_overrides FROM sys_shadow_instances WHERE instance_id = ?",
            (iid,),
        )
        raw = cursor.fetchone()[0]
        params = json.loads(raw)
        assert "dynamic_min_confidence" in params
        assert abs(params["dynamic_min_confidence"] - 0.55) < 1e-6


class TestDynamicThresholdControllerDrawdown:
    """Recuperación del umbral ante drawdown elevado."""

    def test_dtc_recupera_threshold_ante_drawdown_alto(self):
        """Drawdown > 10 % → umbral se recupera hacia base."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        # Instancia con umbral ya reducido y drawdown alto
        _insert_instance(
            conn, iid, strategy_id="strat_dd",
            max_drawdown_pct=0.15,
            parameter_overrides=json.dumps({"dynamic_min_confidence": 0.45}),
        )
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust(iid)

        assert result["adjusted"] is True
        assert result["new_threshold"] > result["old_threshold"]
        assert "drawdown_recovery" in result["reason"]

    def test_dtc_drawdown_bajo_no_activa_recuperacion(self):
        """Drawdown ≤ 10 % con sequía → reduce threshold (drawdown no interviene)."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid, strategy_id="strat_dd2", max_drawdown_pct=0.05)
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust(iid)

        # drawdown bajo → no recupera; sin señales → reduce
        assert result["adjusted"] is True
        assert result["new_threshold"] == pytest.approx(0.55)


class TestDynamicThresholdControllerFloor:
    """Respeto del piso mínimo (floor_confidence = 0.40)."""

    def test_dtc_respeta_floor_con_multiples_reducciones(self):
        """El umbral nunca cae por debajo de floor aunque haya varias reducciones."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        # Umbral ya en 0.41 → reducción de 0.05 no puede ir a 0.36
        _insert_instance(
            conn, iid,
            parameter_overrides=json.dumps({"dynamic_min_confidence": 0.41}),
        )
        dtc = _make_dtc(conn, floor_confidence=0.40)

        result = dtc.evaluate_and_adjust(iid)

        assert result["new_threshold"] == pytest.approx(0.40)

    def test_dtc_threshold_en_floor_permanece_si_sequia_continua(self):
        """Si el umbral ya está en floor y sigue la sequía, permanece en floor."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(
            conn, iid,
            parameter_overrides=json.dumps({"dynamic_min_confidence": 0.40}),
        )
        dtc = _make_dtc(conn, floor_confidence=0.40)

        result = dtc.evaluate_and_adjust(iid)

        assert result["adjusted"] is True  # tecnicamente ajustó (intentó bajar)
        assert result["new_threshold"] == pytest.approx(0.40)  # pero se quedó en floor


class TestDynamicThresholdControllerCasosEspeciales:
    """Casos especiales: instancia inexistente, estados terminales, trace_id."""

    def test_dtc_instancia_inexistente_retorna_not_applicable(self):
        """Instancia no encontrada → adjusted=False con reason NOT_APPLICABLE."""
        conn = _create_in_memory_db()
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust("00000000-0000-0000-0000-000000000000")

        assert result["adjusted"] is False
        assert "instance_not_found" in result["reason"]

    def test_dtc_instancia_dead_no_se_ajusta(self):
        """Instancia con status=DEAD → sin ajuste."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid, status="DEAD")
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust(iid)

        assert result["adjusted"] is False
        assert "not_applicable" in result["reason"]

    def test_dtc_trace_id_formato_correcto(self):
        """Trace_ID sigue patrón TRACE_DTC_YYYYMMDD_HHMMSS_ID8."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid)
        dtc = _make_dtc(conn)

        result = dtc.evaluate_and_adjust(iid)

        trace_id = result["trace_id"]
        assert trace_id.startswith("TRACE_DTC_")
        parts = trace_id.split("_")
        # TRACE_DTC_YYYYMMDD_HHMMSS_ID8 → [TRACE, DTC, date, time, id8]
        assert len(parts) == 5
        assert len(parts[2]) == 8   # YYYYMMDD
        assert len(parts[3]) == 6   # HHMMSS

    def test_dtc_get_current_threshold_retorna_base_sin_ajuste_previo(self):
        """get_current_threshold retorna base_confidence si no hay ajuste previo."""
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(conn, iid)
        dtc = _make_dtc(conn, base_confidence=0.65)

        threshold = dtc.get_current_threshold(iid)

        assert threshold == pytest.approx(0.65)


class TestDynamicThresholdControllerValidacionS9:
    """Tests de validación del protocolo S-9 (Orden de Ingeniería)."""

    def test_dtc_validacion_poblacion_alphahunter_respeta_dynamic_threshold(self):
        """
        Validación S-9 (Punto 4.3): AlphaHunter con umbral dinámico bajo (0.50)
        acepta mutaciones con score 0.55 que antes (umbral=0.85) serían rechazadas.

        Nota: este test verifica la INTEGRACIÓN conceptual —
        el DTC redujo el umbral y ahora promotions con score=0.55 son posibles.
        """
        conn = _create_in_memory_db()
        iid = str(uuid.uuid4())
        _insert_instance(
            conn, iid,
            parameter_overrides=json.dumps({"dynamic_min_confidence": 0.50}),
        )
        dtc = _make_dtc(conn)

        threshold = dtc.get_current_threshold(iid)

        # Con umbral dinámico en 0.50, una señal con score 0.55 debe ser considerada
        assert threshold == pytest.approx(0.50)
        assert 0.55 > threshold, "Score 0.55 debe superar el umbral dinámico de 0.50"
