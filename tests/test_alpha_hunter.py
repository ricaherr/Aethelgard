"""
test_alpha_hunter.py — TDD suite para AlphaHunter.

Componente: core_brain/alpha_hunter.py
Trace_ID: TRACE_TEST_ALPHAHUNTER_20260326

Casos de prueba:
  1. Motor de Mutación — clonar estrategia y variar parameter_overrides con dist. normal
  2. Mutación respeta bounds (valores numéricos no negativos donde aplica)
  3. Pipeline de Auto-Promoción — score > 0.85 inserta en sys_shadow_instances
  4. Pipeline de Auto-Promoción — score <= 0.85 NO inserta
  5. Límite de Población — máximo 20 instancias SHADOW activas (no inserta si pool lleno)
  6. Límite de Población — permite insertar si hay < 20 instancias activas
  7. generate_mutation_trace_id sigue patrón TRACE_ALPHAHUNTER_YYYYMMDD_HHMMSS_ID8
  8. count_active_shadow_instances retorna conteo correcto desde DB
"""

import sqlite3
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List

from core_brain.alpha_hunter import AlphaHunter
from core_brain.scenario_backtester import AptitudeMatrix, RegimeResult, StressCluster


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_aptitude_matrix(strategy_id: str, score: float) -> AptitudeMatrix:
    """Helper: construye un AptitudeMatrix de prueba con el score dado."""
    regime_result = RegimeResult(
        stress_cluster=StressCluster.INSTITUTIONAL_TREND,
        detected_regime="TREND",
        profit_factor=2.5,
        max_drawdown_pct=0.05,
        total_trades=30,
        win_rate=0.70,
        regime_score=score,
    )
    return AptitudeMatrix(
        strategy_id=strategy_id,
        parameter_overrides={"confidence_threshold": 0.75},
        overall_score=score,
        passes_threshold=score >= 0.75,
        results_by_regime=[regime_result],
        trace_id=f"TRACE_BKT_VALIDATION_20260326_120000_{strategy_id[:8].upper()}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _create_in_memory_db() -> sqlite3.Connection:
    """Crea una DB SQLite in-memory con las tablas mínimas necesarias."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sys_shadow_instances (
            instance_id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            account_type TEXT CHECK(account_type IN ('DEMO', 'REAL')),
            parameter_overrides TEXT,
            regime_filters TEXT,
            birth_timestamp TIMESTAMP,
            status TEXT CHECK(status IN (
                'INCUBATING','SHADOW_READY','PROMOTED_TO_REAL','DEAD','QUARANTINED'
            )),
            total_trades_executed INTEGER DEFAULT 0,
            profit_factor REAL DEFAULT 0.0,
            win_rate REAL DEFAULT 0.0,
            max_drawdown_pct REAL DEFAULT 0.0,
            consecutive_losses_max INTEGER DEFAULT 0,
            equity_curve_cv REAL DEFAULT 0.0,
            promotion_trace_id TEXT,
            backtest_trace_id TEXT,
            target_regime TEXT,
            backtest_score REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sys_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            resource TEXT,
            resource_id TEXT,
            old_value TEXT,
            new_value TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


def _insert_shadow_instances(conn: sqlite3.Connection, count: int) -> None:
    """Inserta `count` instancias SHADOW activas (INCUBATING) en la DB."""
    import uuid
    for i in range(count):
        conn.execute(
            """
            INSERT INTO sys_shadow_instances
                (instance_id, strategy_id, account_id, account_type, status,
                 parameter_overrides, birth_timestamp, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                f"STRATEGY_{i:04d}",
                "MT5_DEMO_001",
                "DEMO",
                "INCUBATING",
                "{}",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    conn.commit()


class TestAlphaHunterMutationEngine:
    """Tests para el motor de mutación de parámetros."""

    def _make_hunter(self, conn: sqlite3.Connection) -> AlphaHunter:
        return AlphaHunter(
            storage_conn=conn,
            demo_account_id="MT5_DEMO_001",
            max_shadow_population=20,
            promotion_score_threshold=0.85,
        )

    def test_alpha_hunter_mutacion_clona_strategy_id(self):
        """La mutación preserva el strategy_id original."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        original_params = {"confidence_threshold": 0.75, "risk_reward": 1.5}

        mutant = hunter.mutate_parameters("strategy_oliver_velez", original_params)

        assert mutant["strategy_id"] == "strategy_oliver_velez"

    def test_alpha_hunter_mutacion_retorna_parameter_overrides(self):
        """La mutación retorna un dict con las mismas claves que los parámetros originales."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        original_params = {"confidence_threshold": 0.75, "risk_reward": 1.5}

        mutant = hunter.mutate_parameters("strategy_oliver_velez", original_params)

        assert "parameter_overrides" in mutant
        assert set(mutant["parameter_overrides"].keys()) == set(original_params.keys())

    def test_alpha_hunter_mutacion_varia_valores_numericos(self):
        """La mutación genera valores diferentes a los originales (distribución normal)."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        original_params = {"confidence_threshold": 0.75, "risk_reward": 1.5}

        # Con suficientes mutaciones, al menos una debe diferir del original
        mutations = [
            hunter.mutate_parameters("strat_x", original_params)["parameter_overrides"]
            for _ in range(20)
        ]
        any_different = any(
            m["confidence_threshold"] != 0.75 or m["risk_reward"] != 1.5
            for m in mutations
        )
        assert any_different, "La distribución normal debe producir variación en los parámetros"

    def test_alpha_hunter_mutacion_preserva_bounds_no_negativos(self):
        """Los parámetros numéricos no deben quedar negativos tras la mutación."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        # Valor muy pequeño: la mutación no debe producir negativos
        original_params = {"confidence_threshold": 0.001, "risk_reward": 0.01}

        for _ in range(50):
            mutant = hunter.mutate_parameters("strat_x", original_params)
            for val in mutant["parameter_overrides"].values():
                assert val >= 0.0, f"Parámetro negativo detectado: {val}"

    def test_alpha_hunter_mutacion_ignora_params_no_numericos(self):
        """Parámetros no numéricos (str, bool) se copian sin modificar."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        original_params = {
            "confidence_threshold": 0.75,
            "mode": "AGGRESSIVE",
            "enabled": True,
        }

        mutant = hunter.mutate_parameters("strat_x", original_params)

        assert mutant["parameter_overrides"]["mode"] == "AGGRESSIVE"
        assert mutant["parameter_overrides"]["enabled"] is True

    def test_alpha_hunter_mutacion_genera_trace_id(self):
        """La mutación incluye un trace_id con el patrón correcto."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        original_params = {"confidence_threshold": 0.75}

        mutant = hunter.mutate_parameters("strat_abc123", original_params)

        assert "trace_id" in mutant
        assert mutant["trace_id"].startswith("TRACE_ALPHAHUNTER_")


class TestAlphaHunterAutoPromotion:
    """Tests para el pipeline de auto-promoción a sys_shadow_instances."""

    def _make_hunter(self, conn: sqlite3.Connection) -> AlphaHunter:
        return AlphaHunter(
            storage_conn=conn,
            demo_account_id="MT5_DEMO_001",
            max_shadow_population=20,
            promotion_score_threshold=0.85,
        )

    def test_alpha_hunter_promueve_si_score_supera_umbral(self):
        """Si overall_score > 0.85, se inserta una fila en sys_shadow_instances."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_oliver", score=0.90)
        mutated_params = {"confidence_threshold": 0.78, "risk_reward": 1.6}

        result = hunter.try_promote_mutant(matrix, mutated_params)

        assert result["promoted"] is True
        cursor = conn.execute("SELECT COUNT(*) FROM sys_shadow_instances")
        assert cursor.fetchone()[0] == 1

    def test_alpha_hunter_no_promueve_si_score_igual_al_umbral(self):
        """Score exactamente 0.85 no supera el umbral (requiere estrictamente mayor)."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_oliver", score=0.85)
        mutated_params = {"confidence_threshold": 0.80}

        result = hunter.try_promote_mutant(matrix, mutated_params)

        assert result["promoted"] is False
        cursor = conn.execute("SELECT COUNT(*) FROM sys_shadow_instances")
        assert cursor.fetchone()[0] == 0

    def test_alpha_hunter_no_promueve_si_score_bajo(self):
        """Score < 0.85 no inserta en sys_shadow_instances."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_momentum", score=0.70)
        mutated_params = {"confidence_threshold": 0.60}

        result = hunter.try_promote_mutant(matrix, mutated_params)

        assert result["promoted"] is False
        cursor = conn.execute("SELECT COUNT(*) FROM sys_shadow_instances")
        assert cursor.fetchone()[0] == 0

    def test_alpha_hunter_promueve_con_parameter_overrides_correctos(self):
        """La instancia insertada tiene los parameter_overrides de la mutación."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_vwap", score=0.91)
        mutated_params = {"confidence_threshold": 0.82, "risk_reward": 2.0}

        hunter.try_promote_mutant(matrix, mutated_params)

        cursor = conn.execute("SELECT parameter_overrides FROM sys_shadow_instances LIMIT 1")
        row = cursor.fetchone()
        stored = eval(row[0])  # parameter_overrides se almacena como repr de dict
        assert stored["confidence_threshold"] == 0.82
        assert stored["risk_reward"] == 2.0

    def test_alpha_hunter_promueve_con_account_demo(self):
        """La instancia insertada tiene account_type='DEMO' y el account_id correcto."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_vwap", score=0.91)

        hunter.try_promote_mutant(matrix, {"confidence_threshold": 0.80})

        cursor = conn.execute(
            "SELECT account_id, account_type FROM sys_shadow_instances LIMIT 1"
        )
        row = cursor.fetchone()
        assert row["account_id"] == "MT5_DEMO_001"
        assert row["account_type"] == "DEMO"

    def test_alpha_hunter_promueve_con_strategy_id_origen(self):
        """La instancia insertada referencia el strategy_id de la AptitudeMatrix."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_brk_open", score=0.92)

        hunter.try_promote_mutant(matrix, {"confidence_threshold": 0.77})

        cursor = conn.execute("SELECT strategy_id FROM sys_shadow_instances LIMIT 1")
        row = cursor.fetchone()
        assert row["strategy_id"] == "strategy_brk_open"

    def test_alpha_hunter_promueve_registra_backtest_score(self):
        """La instancia insertada almacena el backtest_score de la AptitudeMatrix."""
        conn = _create_in_memory_db()
        hunter = self._make_hunter(conn)
        matrix = _make_aptitude_matrix("strategy_x", score=0.93)

        hunter.try_promote_mutant(matrix, {"confidence_threshold": 0.80})

        cursor = conn.execute("SELECT backtest_score FROM sys_shadow_instances LIMIT 1")
        row = cursor.fetchone()
        assert abs(row["backtest_score"] - 0.93) < 1e-6


class TestAlphaHunterPopulationLimit:
    """Tests para el límite de 20 instancias SHADOW activas."""

    def _make_hunter(self, conn: sqlite3.Connection, max_pop: int = 20) -> AlphaHunter:
        return AlphaHunter(
            storage_conn=conn,
            demo_account_id="MT5_DEMO_001",
            max_shadow_population=max_pop,
            promotion_score_threshold=0.85,
        )

    def test_alpha_hunter_no_promueve_si_pool_lleno(self):
        """Con 20 instancias activas, try_promote_mutant rechaza la promoción."""
        conn = _create_in_memory_db()
        _insert_shadow_instances(conn, 20)
        hunter = self._make_hunter(conn, max_pop=20)
        matrix = _make_aptitude_matrix("strategy_new", score=0.95)

        result = hunter.try_promote_mutant(matrix, {"confidence_threshold": 0.80})

        assert result["promoted"] is False
        assert "population_limit" in result["reason"].lower()
        # La cuenta debe seguir en 20
        cursor = conn.execute(
            "SELECT COUNT(*) FROM sys_shadow_instances WHERE status NOT IN ('DEAD','PROMOTED_TO_REAL')"
        )
        assert cursor.fetchone()[0] == 20

    def test_alpha_hunter_promueve_si_pool_no_lleno(self):
        """Con 19 instancias activas, la promoción se permite."""
        conn = _create_in_memory_db()
        _insert_shadow_instances(conn, 19)
        hunter = self._make_hunter(conn, max_pop=20)
        matrix = _make_aptitude_matrix("strategy_new", score=0.95)

        result = hunter.try_promote_mutant(matrix, {"confidence_threshold": 0.80})

        assert result["promoted"] is True

    def test_alpha_hunter_count_active_instances_excluye_terminales(self):
        """count_active_shadow_instances excluye DEAD y PROMOTED_TO_REAL."""
        conn = _create_in_memory_db()
        _insert_shadow_instances(conn, 5)  # 5 INCUBATING
        # Insertar 2 terminales que NO deben contarse
        import uuid
        for status in ("DEAD", "PROMOTED_TO_REAL"):
            conn.execute(
                """
                INSERT INTO sys_shadow_instances
                    (instance_id, strategy_id, account_id, account_type, status,
                     parameter_overrides, birth_timestamp, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), "STRAT_TERMINAL", "MT5_DEMO_001", "DEMO", status,
                    "{}", datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()
        hunter = self._make_hunter(conn)

        count = hunter.count_active_shadow_instances()

        assert count == 5

    def test_alpha_hunter_limite_configurable(self):
        """El límite de población es configurable vía constructor."""
        conn = _create_in_memory_db()
        _insert_shadow_instances(conn, 5)
        # Con max_shadow_population=5, el pool ya está lleno
        hunter = self._make_hunter(conn, max_pop=5)
        matrix = _make_aptitude_matrix("strategy_new", score=0.95)

        result = hunter.try_promote_mutant(matrix, {"confidence_threshold": 0.80})

        assert result["promoted"] is False


class TestAlphaHunterTraceId:
    """Tests para la generación de Trace_IDs."""

    def test_generate_mutation_trace_id_formato_correcto(self):
        """El trace_id sigue el patrón TRACE_ALPHAHUNTER_YYYYMMDD_HHMMSS_ID8."""
        conn = _create_in_memory_db()
        hunter = AlphaHunter(
            storage_conn=conn,
            demo_account_id="MT5_DEMO_001",
            max_shadow_population=20,
            promotion_score_threshold=0.85,
        )
        # Usar strategy_id sin guiones en los primeros 8 chars para evitar splits extra
        trace_id = hunter.generate_mutation_trace_id("STRATXYZ9")

        assert trace_id.startswith("TRACE_ALPHAHUNTER_")
        parts = trace_id.split("_")
        # TRACE_ALPHAHUNTER_YYYYMMDD_HHMMSS_ID8 → partes: [TRACE, ALPHAHUNTER, date, time, id8]
        assert len(parts) == 5
        assert len(parts[2]) == 8   # YYYYMMDD
        assert len(parts[3]) == 6   # HHMMSS
        assert len(parts[4]) == 8   # ID8

    def test_generate_mutation_trace_id_usa_strategy_id_prefix(self):
        """El suffix del trace_id usa los primeros 8 chars del strategy_id en mayúsculas."""
        conn = _create_in_memory_db()
        hunter = AlphaHunter(
            storage_conn=conn,
            demo_account_id="MT5_DEMO_001",
            max_shadow_population=20,
            promotion_score_threshold=0.85,
        )

        trace_id = hunter.generate_mutation_trace_id("strategy_oliver_velez")
        suffix = trace_id.split("_")[-1]

        assert suffix == "STRATEGY"  # "strategy"[:8].upper() == "STRATEGY"
