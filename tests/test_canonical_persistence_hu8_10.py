"""
HU 8.10 — Legacy Table Canonicalization & Prefix Compliance
HU 10.33 — Canonical Heartbeat Observability Alignment
Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
Trace_ID: ETI-SRE-OEM-CANONICAL-HEARTBEAT-2026-04-14

TDD focal suite. Cubre los criterios de aceptación de ambos ETI:
  HU 8.10:
    1. sys_session_tokens / sys_position_metadata son canónicas tras initialize_schema.
    2. monitor_snapshot clasifica explícitamente: canonical | legacy_compatible | violation.
    3. Tablas tenant sin prefijo (ej. 'notifications') quedan visibles como violation.
  HU 10.33:
    4. Snapshot no reporta sqlite_sequence (ni ninguna sqlite_*) como violation.
    5. PositionManager DELETE de metadata corrupta opera sobre sys_position_metadata.
    6. OEM heartbeat se evalúa exclusivamente desde sys_audit_logs / sys_config.

Orden de ejecución: pytest tests/test_canonical_persistence_hu8_10.py -v
"""
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from data_vault.schema import initialize_schema
from scripts.monitor_snapshot import classify_tables


# ─────────────────────────────────────────────────────────────────────────────
# AC-1: Tablas canónicas presentes tras initialize_schema
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_exposes_prefixed_session_and_position_tables_as_canonical() -> None:
    """
    Dado un arranque sobre DB nueva (en memoria), cuando se ejecuta initialize_schema,
    entonces sys_session_tokens y sys_position_metadata quedan presentes como tablas canónicas.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "sys_session_tokens" in tables, (
        "sys_session_tokens debe existir como tabla canónica (prefijo sys_)"
    )
    assert "sys_position_metadata" in tables, (
        "sys_position_metadata debe existir como tabla canónica (prefijo sys_)"
    )


def test_schema_canonical_tables_have_expected_columns() -> None:
    """
    Las tablas canónicas sys_session_tokens y sys_position_metadata deben tener
    los mismos campos clave que sus contraparte legacy (compatibilidad estructural).
    """
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(sys_session_tokens)")
    session_cols = {row[1] for row in cursor.fetchall()}

    cursor.execute("PRAGMA table_info(sys_position_metadata)")
    position_cols = {row[1] for row in cursor.fetchall()}
    conn.close()

    # session tokens
    for col in ("token_hash", "user_id", "token_type", "expires_at", "revoked"):
        assert col in session_cols, f"sys_session_tokens debe tener columna '{col}'"

    # position metadata
    for col in ("ticket", "symbol", "entry_price", "entry_time", "direction"):
        assert col in position_cols, f"sys_position_metadata debe tener columna '{col}'"


# ─────────────────────────────────────────────────────────────────────────────
# AC-2: monitor_snapshot clasifica tablas con tres estados explícitos
# ─────────────────────────────────────────────────────────────────────────────

def test_monitor_snapshot_classifies_canonical_tables() -> None:
    """
    Dado un conjunto de tablas con prefijo sys_/usr_,
    classify_tables las reporta en 'canonical'.
    """
    tables = ["sys_users", "sys_config", "sys_audit_logs", "usr_trades", "usr_assets_cfg"]
    result = classify_tables(tables)

    for t in tables:
        assert t in result["canonical"], f"'{t}' debe clasificarse como canonical"
    assert result["legacy_compatible"] == [], "No debe haber legacy_compatible en este conjunto"
    assert result["violations"] == [], "No debe haber violations en este conjunto"


def test_monitor_snapshot_reports_legacy_session_tokens_explicitly() -> None:
    """
    Dado un snapshot con session_tokens (sin prefijo, legacy conocida),
    classify_tables la reporta en 'legacy_compatible', NO en violations.
    """
    tables = ["sys_users", "sys_config", "session_tokens", "position_metadata"]
    result = classify_tables(tables)

    assert "session_tokens" in result["legacy_compatible"], (
        "session_tokens debe clasificarse como legacy_compatible (migración en curso a sys_session_tokens)"
    )
    assert "position_metadata" in result["legacy_compatible"], (
        "position_metadata debe clasificarse como legacy_compatible (migración en curso a sys_position_metadata)"
    )
    assert "session_tokens" not in result["violations"], (
        "session_tokens NO es una violación: es legacy conocida con plan de migración"
    )
    assert "position_metadata" not in result["violations"], (
        "position_metadata NO es una violación: es legacy conocida con plan de migración"
    )


def test_monitor_snapshot_reports_unknown_unprefixed_tables_as_violations() -> None:
    """
    Dado un snapshot con tablas sin prefijo y sin registro como legacy conocida,
    classify_tables las reporta en 'violations'.
    """
    tables = ["sys_config", "unknown_table", "raw_data", "session_tokens"]
    result = classify_tables(tables)

    assert "unknown_table" in result["violations"], (
        "unknown_table sin prefijo y sin registro como legacy conocida es una VIOLATION"
    )
    assert "raw_data" in result["violations"], (
        "raw_data sin prefijo y sin registro como legacy conocida es una VIOLATION"
    )
    # legacy conocida NO debe saltar como violation
    assert "session_tokens" not in result["violations"]
    assert "sys_config" not in result["violations"]


def test_monitor_snapshot_returns_structured_dict_with_three_keys() -> None:
    """
    classify_tables siempre devuelve un dict con exactamente las claves:
    'canonical', 'legacy_compatible', 'violations'.
    """
    result = classify_tables([])
    assert set(result.keys()) == {"canonical", "legacy_compatible", "violations"}
    assert isinstance(result["canonical"], list)
    assert isinstance(result["legacy_compatible"], list)
    assert isinstance(result["violations"], list)


# ─────────────────────────────────────────────────────────────────────────────
# AC-3: Tablas tenant residuales sin prefijo quedan visibles como violation
# ─────────────────────────────────────────────────────────────────────────────

def test_tenant_db_legacy_tables_are_flagged_not_silently_accepted() -> None:
    """
    Dado un DB tenant con residuos legacy (notifications sin prefijo),
    classify_tables las expone como violations para remediación controlada.
    """
    tenant_tables = [
        "usr_trades",
        "usr_assets_cfg",
        "usr_credentials",
        "notifications",       # tabla legacy sin prefijo — VIOLATION
    ]
    result = classify_tables(tenant_tables)

    assert "notifications" in result["violations"], (
        "'notifications' sin prefijo debe aparecer en violations (tabla legacy sin plan de migración explícito)"
    )
    assert "usr_trades" in result["canonical"]
    assert "usr_assets_cfg" in result["canonical"]
    assert "usr_credentials" in result["canonical"]


def test_monitor_snapshot_skips_sqlite_internal_tables() -> None:
    """
    Las tablas internas de SQLite (sqlite_sequence, etc.) no deben clasificarse
    como violations ni contaminar ninguna categoría SRE.
    """
    tables = ["sys_users", "sqlite_sequence", "session_tokens", "unknown_table"]
    result = classify_tables(tables)

    all_classified = result["canonical"] + result["legacy_compatible"] + result["violations"]
    assert "sqlite_sequence" not in all_classified, (
        "sqlite_sequence es una tabla interna de SQLite y no debe aparecer en ninguna categoría SRE"
    )
    assert "unknown_table" in result["violations"], "unknown_table sí debe ser violation"
    assert "sys_users" in result["canonical"]
    assert "session_tokens" in result["legacy_compatible"]


def test_tenant_db_usr_prefixed_legacy_is_canonical_not_violation() -> None:
    """
    Tablas con prefijo usr_ (aunque sean candidatas a retiro) se reportan como
    canonical — tienen el prefijo correcto. El retiro es decisión de roadmap, no una violation.
    """
    tenant_tables = [
        "usr_edge_learning",        # candidata a retiro, pero tiene prefijo usr_
        "usr_tuning_adjustments",   # idem
    ]
    result = classify_tables(tenant_tables)

    assert "usr_edge_learning" in result["canonical"]
    assert "usr_tuning_adjustments" in result["canonical"]
    assert result["violations"] == []
    assert result["legacy_compatible"] == []


# ─────────────────────────────────────────────────────────────────────────────
# HU 10.33 — AC-4: Snapshot ignora tablas internas SQLite (sin falsos positivos)
# ─────────────────────────────────────────────────────────────────────────────

def test_monitor_snapshot_ignores_sqlite_internal_tables() -> None:
    """
    Las tablas internas de SQLite (sqlite_sequence, sqlite_stat*) NO deben aparecer
    en ninguna categoría SRE — ni como violation, ni como canonical, ni como
    legacy_compatible. Son artefactos del motor, invisibles para governance.

    Trace_ID: ETI-SRE-OEM-CANONICAL-HEARTBEAT-2026-04-14 / AC-4
    """
    tables = [
        "sys_users",
        "sys_config",
        "sys_audit_logs",
        "sqlite_sequence",
        "sqlite_stat1",
        "sqlite_stat4",
        "session_tokens",
        "unknown_table",
    ]
    result = classify_tables(tables)

    all_classified = result["canonical"] + result["legacy_compatible"] + result["violations"]

    for internal in ("sqlite_sequence", "sqlite_stat1", "sqlite_stat4"):
        assert internal not in all_classified, (
            f"'{internal}' es tabla interna SQLite y no debe aparecer en ninguna "
            "categoría SRE (evita falsos positivos de violation)"
        )

    # El resto sí debe estar clasificado correctamente
    assert "sys_users" in result["canonical"]
    assert "sys_audit_logs" in result["canonical"]
    assert "session_tokens" in result["legacy_compatible"]
    assert "unknown_table" in result["violations"]


# ─────────────────────────────────────────────────────────────────────────────
# HU 10.33 — AC-5: PositionManager DELETE opera sobre tabla canónica
# ─────────────────────────────────────────────────────────────────────────────

def test_position_manager_deletes_metadata_in_canonical_table() -> None:
    """
    Cuando PositionManager detecta metadata corrupta (entry_price=0 o volume=0),
    el DELETE de remediación debe apuntar a sys_position_metadata (canónica).
    No debe operar contra la tabla legacy position_metadata sin prefijo.

    Trace_ID: ETI-SRE-OEM-CANONICAL-HEARTBEAT-2026-04-14 / AC-5
    """
    from core_brain.position_manager import PositionManager

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    storage = MagicMock()
    storage._get_conn.return_value = mock_conn
    storage.get_position_metadata.return_value = {}
    storage.update_position_metadata.return_value = True

    config = {
        "max_drawdown_multiplier": 2.0,
        "modification_cooldown_seconds": 300,
        "max_modifications_per_day": 10,
        "time_based_exit_enabled": False,
        "stale_position_thresholds": {"TREND": 72, "RANGE": 4},
        "breakeven": {
            "enabled": True,
            "min_profit_distance_pips": 5,
            "min_time_minutes": 15,
            "include_commission": True,
            "include_swap": True,
            "include_spread": True,
        },
    }
    pm = PositionManager(
        storage=storage,
        connector=MagicMock(),
        regime_classifier=MagicMock(),
        config=config,
    )

    # Metadata corrupta: entry_price=0 → dispara el path de DELETE
    position = {"ticket": 99999, "volume": 1.0, "symbol": "EURUSD"}
    metadata = {"entry_price": 0.0, "volume": 1.0}

    result = pm._calculate_breakeven_real(position, metadata)

    # El método devuelve None en el path de metadata corrupta
    assert result is None, "Debe retornar None con metadata corrupta"

    # Extraer todas las llamadas execute sobre el cursor
    executed_sqls = [
        call.args[0] if call.args else ""
        for call in mock_cursor.execute.call_args_list
    ]
    delete_sqls = [sql for sql in executed_sqls if "DELETE" in sql.upper()]

    assert len(delete_sqls) >= 1, (
        "Debe haberse ejecutado al menos un DELETE al detectar metadata corrupta"
    )
    for sql in delete_sqls:
        assert "sys_position_metadata" in sql, (
            f"DELETE debe referenciar sys_position_metadata (canónica). SQL encontrado: {sql!r}"
        )
        # Verificar que no apunta accidentalmente a la tabla legacy sin prefijo
        # (nota: 'sys_position_metadata' contiene 'position_metadata' como subcadena,
        #  por eso verificamos la presencia del prefijo sys_)
        assert sql.strip().upper().find("FROM POSITION_METADATA") == -1, (
            f"DELETE no debe apuntar a la tabla legacy 'position_metadata' sin prefijo. SQL: {sql!r}"
        )
