import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "state.db"
SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "init.sql"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    sql = SCHEMA_PATH.read_text()
    with _connect() as conn:
        conn.executescript(sql)


def start_run(run_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, started_at, status) VALUES (?, ?, 'running')",
            (run_id, now),
        )


def finish_run(
    run_id: str,
    status: str,
    num_queries: int = 0,
    article_count: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    error: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """UPDATE runs SET
                completed_at  = ?,
                status        = ?,
                num_queries   = ?,
                article_count = ?,
                input_tokens  = ?,
                output_tokens = ?,
                cost_usd      = ?,
                error_message = ?
            WHERE run_id = ?""",
            (now, status, num_queries, article_count, input_tokens, output_tokens, cost_usd, error, run_id),
        )


def get_runs(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
