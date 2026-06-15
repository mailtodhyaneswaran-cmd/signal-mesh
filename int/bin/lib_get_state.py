"""
lib_get_state.py
─────────────────────────────────────────────────────────────────────────────
SQLite state persistence for /get monitoring sessions.

Uses WAL mode for concurrent access safety.

Tables:
  get_sessions — one row per monitoring session
  get_runs     — one row per analysis run within a session

Public API:
  init_db()
  create_session(ticker, agent, total_runs, interval_min) -> str
  save_run(session_id, run_n, parsed_json, price)
  get_baseline(session_id) -> dict|None
  get_previous_run(session_id, current_run_n) -> dict|None
  mark_session_complete(session_id)
  cancel_session(session_id)
  list_active_sessions() -> list[dict]
  get_session(session_id) -> dict|None
  get_session_runs(session_id) -> list[dict]
  get_run_count(session_id) -> int
  get_active_session_for_ticker(ticker) -> dict|None
"""

import json
import sqlite3
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "get_state.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not yet exist. Called automatically at import."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS get_sessions (
                session_id   TEXT PRIMARY KEY,
                ticker       TEXT NOT NULL,
                agent        TEXT NOT NULL,
                total_runs   INTEGER NOT NULL,
                interval_min INTEGER NOT NULL,
                started_at   TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'active'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS get_runs (
                session_id   TEXT NOT NULL,
                run_n        INTEGER NOT NULL,
                timestamp    TEXT NOT NULL,
                signal       TEXT NOT NULL,
                factor_score INTEGER NOT NULL,
                confidence   INTEGER NOT NULL,
                price        REAL NOT NULL,
                raw_json     TEXT NOT NULL,
                PRIMARY KEY (session_id, run_n),
                FOREIGN KEY (session_id) REFERENCES get_sessions(session_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS get2_meta (
                session_id         TEXT PRIMARY KEY,
                budget             REAL NOT NULL,
                currency           TEXT NOT NULL DEFAULT 'USD',
                position_status    TEXT NOT NULL DEFAULT 'none',
                position_qty       REAL NOT NULL DEFAULT 0,
                position_buy_price REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES get_sessions(session_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS get2_trades (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id     TEXT NOT NULL,
                run_n          INTEGER NOT NULL,
                action         TEXT NOT NULL,
                ticker         TEXT NOT NULL,
                quantity       REAL NOT NULL DEFAULT 0,
                dollar_amount  REAL NOT NULL DEFAULT 0,
                fill_price     REAL NOT NULL DEFAULT 0,
                ibkr_order_id  INTEGER,
                ibkr_status    TEXT,
                pnl            REAL DEFAULT 0,
                timestamp      TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES get_sessions(session_id)
            )
        """)
        conn.commit()


# Initialise on import
init_db()


def create_session(ticker: str, agent: str, total_runs: int, interval_min: int) -> str:
    """Create a new monitoring session and return its 8-character session_id."""
    from datetime import datetime, timezone
    session_id = uuid.uuid4().hex[:8]
    started_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO get_sessions (session_id, ticker, agent, total_runs, interval_min, started_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active')",
            (session_id, ticker.upper(), agent, total_runs, interval_min, started_at),
        )
        conn.commit()
    return session_id


def save_run(session_id: str, run_n: int, parsed_json: dict, price: float) -> None:
    """Persist a single run result to get_runs."""
    from datetime import datetime, timezone
    timestamp    = parsed_json.get("timestamp") or datetime.now(timezone.utc).isoformat()
    signal       = str(parsed_json.get("signal", "HOLD"))
    factor_score = int(parsed_json.get("factor_score", 50) or 50)
    confidence   = int(parsed_json.get("confidence", 0) or 0)
    raw_json     = json.dumps(parsed_json)

    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO get_runs "
            "(session_id, run_n, timestamp, signal, factor_score, confidence, price, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, run_n, timestamp, signal, factor_score, confidence, float(price), raw_json),
        )
        conn.commit()


def get_baseline(session_id: str) -> dict | None:
    """Return run #1 for the given session, decoded from raw_json, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM get_runs WHERE session_id=? AND run_n=1",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    data = json.loads(row["raw_json"])
    data.setdefault("timestamp",    row["timestamp"])
    data.setdefault("price",        row["price"])
    data.setdefault("signal",       row["signal"])
    data.setdefault("factor_score", row["factor_score"])
    return data


def get_previous_run(session_id: str, current_run_n: int) -> dict | None:
    """Return the run immediately before current_run_n, or None."""
    prev_n = current_run_n - 1
    if prev_n < 1:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM get_runs WHERE session_id=? AND run_n=?",
            (session_id, prev_n),
        ).fetchone()
    if row is None:
        return None
    data = json.loads(row["raw_json"])
    data.setdefault("timestamp",    row["timestamp"])
    data.setdefault("price",        row["price"])
    data.setdefault("signal",       row["signal"])
    data.setdefault("factor_score", row["factor_score"])
    return data


def mark_session_complete(session_id: str) -> None:
    """Set session status to 'complete'."""
    with _connect() as conn:
        conn.execute(
            "UPDATE get_sessions SET status='complete' WHERE session_id=?",
            (session_id,),
        )
        conn.commit()


def cancel_session(session_id: str) -> None:
    """Set session status to 'cancelled'."""
    with _connect() as conn:
        conn.execute(
            "UPDATE get_sessions SET status='cancelled' WHERE session_id=?",
            (session_id,),
        )
        conn.commit()


def list_active_sessions() -> list[dict]:
    """Return all sessions with status='active' as a list of dicts."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM get_sessions WHERE status='active' ORDER BY started_at",
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    """Return a single session by session_id, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM get_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def get_session_runs(session_id: str) -> list[dict]:
    """Return all runs for a session, ordered by run_n.

    Each dict includes a 'parsed' key with the decoded JSON payload,
    plus top-level convenience fields (signal, price, factor_score, timestamp).
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM get_runs WHERE session_id=? ORDER BY run_n",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["parsed"] = json.loads(d["raw_json"])
        result.append(d)
    return result


def get_run_count(session_id: str) -> int:
    """Return the number of completed runs for a session."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM get_runs WHERE session_id=?",
            (session_id,),
        ).fetchone()
    return row["cnt"] if row else 0


def get_active_session_for_ticker(ticker: str) -> dict | None:
    """Return the most recently started active session for a ticker, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM get_sessions WHERE ticker=? AND status='active' "
            "ORDER BY started_at DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    return dict(row) if row else None


def create_get2_meta(session_id: str, budget: float, currency: str = "USD") -> None:
    """Create the get2-specific metadata row for a session."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO get2_meta (session_id, budget, currency, position_status, position_qty, position_buy_price) "
            "VALUES (?, ?, ?, 'none', 0, 0)",
            (session_id, budget, currency),
        )
        conn.commit()


def update_get2_position(session_id: str, status: str, qty: float, buy_price: float) -> None:
    """Update position state: status='none'|'long', qty, buy_price."""
    with _connect() as conn:
        conn.execute(
            "UPDATE get2_meta SET position_status=?, position_qty=?, position_buy_price=? WHERE session_id=?",
            (status, qty, buy_price, session_id),
        )
        conn.commit()


def get_get2_meta(session_id: str) -> dict | None:
    """Return get2 metadata for a session, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM get2_meta WHERE session_id=?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def record_get2_trade(
    session_id: str, run_n: int, action: str, ticker: str,
    quantity: float, dollar_amount: float, fill_price: float,
    ibkr_order_id: int | None, ibkr_status: str | None, pnl: float = 0.0,
) -> None:
    """Insert a trade execution record."""
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO get2_trades "
            "(session_id, run_n, action, ticker, quantity, dollar_amount, fill_price, ibkr_order_id, ibkr_status, pnl, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, run_n, action, ticker.upper(), quantity, dollar_amount, fill_price,
             ibkr_order_id, ibkr_status, pnl, timestamp),
        )
        conn.commit()


def get_get2_trades(session_id: str) -> list[dict]:
    """Return all trades for a session, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM get2_trades WHERE session_id=? ORDER BY id DESC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_active_get2_sessions() -> list[dict]:
    """Return active get2 sessions joined with get2_meta."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.*, m.budget, m.currency, m.position_status, m.position_qty, m.position_buy_price "
            "FROM get_sessions s "
            "INNER JOIN get2_meta m ON s.session_id = m.session_id "
            "WHERE s.status='active' "
            "ORDER BY s.started_at",
        ).fetchall()
    return [dict(r) for r in rows]


def get_active_get2_session_for_ticker(ticker: str) -> dict | None:
    """Return the most recent active get2 session for ticker, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT s.*, m.budget, m.currency, m.position_status, m.position_qty, m.position_buy_price "
            "FROM get_sessions s "
            "INNER JOIN get2_meta m ON s.session_id = m.session_id "
            "WHERE s.ticker=? AND s.status='active' "
            "ORDER BY s.started_at DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    return dict(row) if row else None
