import sqlite3

from data_vault.schema import initialize_schema


def test_initialize_schema_creates_and_backfills_sys_session_tokens() -> None:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE session_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            token_type TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            revoked BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME,
            user_agent TEXT,
            ip_address TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO session_tokens (token_hash, user_id, token_type, expires_at, revoked)
        VALUES ('tok-001', 'usr-001', 'access', '2030-01-01T00:00:00', 0)
        """
    )
    conn.commit()

    initialize_schema(conn)

    row = conn.execute(
        "SELECT token_hash, user_id FROM sys_session_tokens WHERE token_hash = 'tok-001'"
    ).fetchone()
    assert row is not None
    assert row[0] == "tok-001"
    assert row[1] == "usr-001"


def test_initialize_schema_creates_and_backfills_sys_position_metadata() -> None:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE position_metadata (
            ticket INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_time TEXT NOT NULL,
            direction TEXT,
            sl REAL,
            tp REAL,
            volume REAL NOT NULL,
            initial_risk_usd REAL,
            entry_regime TEXT,
            timeframe TEXT,
            strategy TEXT,
            data TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO position_metadata (ticket, symbol, entry_price, entry_time, volume)
        VALUES (12345, 'EURUSD', 1.2345, '2026-04-05T00:00:00+00:00', 0.10)
        """
    )
    conn.commit()

    initialize_schema(conn)

    row = conn.execute(
        "SELECT ticket, symbol FROM sys_position_metadata WHERE ticket = 12345"
    ).fetchone()
    assert row is not None
    assert row[0] == 12345
    assert row[1] == "EURUSD"
