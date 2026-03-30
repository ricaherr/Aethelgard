"""
Test Suite — monitor_snapshot.py
FIX-MONITOR-SNAPSHOT-2026-03-30
Verifica: encoding UTF-8 robusto + query sys_config (no sys_state obsoleta).
"""
import json
import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_sys_config_db(db_path: str) -> None:
    """Crea una DB mínima con tabla sys_config para tests."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE sys_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO sys_config VALUES (?, ?, ?)",
        ("heartbeat_test", '"ok"', "2026-03-30T10:00:00+00:00"),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests: get_db_snapshot
# ---------------------------------------------------------------------------

class TestGetDbSnapshot:
    """Verifica que get_db_snapshot use sys_config y no sys_state."""

    def test_get_db_snapshot_retorna_error_cuando_db_no_existe(self, tmp_path):
        fake_db = str(tmp_path / "no_existe.db")
        with patch("scripts.monitor_snapshot.GLOBAL_DB", fake_db):
            from scripts.monitor_snapshot import get_db_snapshot
            result = get_db_snapshot()
        assert "error" in result
        assert "GLOBAL_DB_NOT_FOUND" in result["error"] or result.get("path") == fake_db

    def test_get_db_snapshot_consulta_sys_config(self, tmp_path):
        db_path = str(tmp_path / "aethelgard.db")
        _build_sys_config_db(db_path)
        with patch("scripts.monitor_snapshot.GLOBAL_DB", db_path):
            from scripts.monitor_snapshot import get_db_snapshot
            result = get_db_snapshot()
        assert "error" not in result
        assert "sys_config_tail" in result
        assert len(result["sys_config_tail"]) >= 1
        row = result["sys_config_tail"][0]
        assert "key" in row and "value" in row and "updated_at" in row

    def test_get_db_snapshot_no_crashea_sin_tabla_sys_state(self, tmp_path):
        """La DB sólo tiene sys_config — sys_state no existe.
        El script NO debe lanzar OperationalError."""
        db_path = str(tmp_path / "aethelgard.db")
        _build_sys_config_db(db_path)
        with patch("scripts.monitor_snapshot.GLOBAL_DB", db_path):
            from scripts.monitor_snapshot import get_db_snapshot
            result = get_db_snapshot()
        # No error, y sys_state no aparece en los resultados
        assert "error" not in result
        assert "sys_state" not in str(result)

    def test_get_db_snapshot_lista_tablas_activas(self, tmp_path):
        db_path = str(tmp_path / "aethelgard.db")
        _build_sys_config_db(db_path)
        with patch("scripts.monitor_snapshot.GLOBAL_DB", db_path):
            from scripts.monitor_snapshot import get_db_snapshot
            result = get_db_snapshot()
        assert "active_tables" in result
        assert "sys_config" in result["active_tables"]


# ---------------------------------------------------------------------------
# Tests: get_recent_logs (encoding UTF-8)
# ---------------------------------------------------------------------------

class TestGetRecentLogs:
    """Verifica que get_recent_logs maneje encoding robusto."""

    def test_get_recent_logs_lee_utf8_correctamente(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "engine.log").write_text(
            "INFO inicio\nERROR señal inválida\n", encoding="utf-8"
        )
        with patch("scripts.monitor_snapshot.LOG_DIR", str(log_dir) + "/"):
            from scripts.monitor_snapshot import get_recent_logs
            result = get_recent_logs(lines=10)
        assert "engine.log" in result
        assert any("señal" in line for line in result["engine.log"])

    def test_get_recent_logs_no_crashea_con_bytes_invalidos(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        # Escribe bytes que no son UTF-8 válido
        path = log_dir / "corrupt.log"
        path.write_bytes(b"OK line\n\xff\xfe bad bytes\n")
        with patch("scripts.monitor_snapshot.LOG_DIR", str(log_dir) + "/"):
            from scripts.monitor_snapshot import get_recent_logs
            result = get_recent_logs(lines=10)
        # No debe lanzar excepción; el archivo debe estar presente
        assert "corrupt.log" in result

    def test_get_recent_logs_retorna_error_sin_directorio(self, tmp_path):
        fake_dir = str(tmp_path / "no_existe") + "/"
        with patch("scripts.monitor_snapshot.LOG_DIR", fake_dir):
            from scripts.monitor_snapshot import get_recent_logs
            result = get_recent_logs()
        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: generate_full_snapshot — JSON válido
# ---------------------------------------------------------------------------

class TestGenerateFullSnapshot:
    """Verifica que la salida del script sea JSON puro y válido."""

    def test_generate_full_snapshot_produce_json_valido(self, tmp_path, capsys):
        db_path = str(tmp_path / "aethelgard.db")
        _build_sys_config_db(db_path)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "app.log").write_text("INFO ok\n", encoding="utf-8")

        with (
            patch("scripts.monitor_snapshot.GLOBAL_DB", db_path),
            patch("scripts.monitor_snapshot.LOG_DIR", str(log_dir) + "/"),
        ):
            from scripts.monitor_snapshot import generate_full_snapshot
            generate_full_snapshot()

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)  # lanza si no es JSON válido
        assert "db_state" in parsed
        assert "log_tails" in parsed
        assert "metadata" in parsed

    def test_generate_full_snapshot_contiene_timestamp(self, tmp_path, capsys):
        db_path = str(tmp_path / "aethelgard.db")
        _build_sys_config_db(db_path)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        with (
            patch("scripts.monitor_snapshot.GLOBAL_DB", db_path),
            patch("scripts.monitor_snapshot.LOG_DIR", str(log_dir) + "/"),
        ):
            from scripts.monitor_snapshot import generate_full_snapshot
            generate_full_snapshot()

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "timestamp" in parsed["metadata"]
        assert parsed["metadata"]["timestamp"]  # no vacío
