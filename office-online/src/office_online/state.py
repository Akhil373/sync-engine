import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


def get_db_path() -> Path:
    state_dir = Path.home() / ".local" / "state" / "office-online"
    db_path = state_dir / "office-online.db"
    return db_path


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn


def init_db() -> None:
    conn = get_connection()

    try:
        # state -> active, inactive, cleaned
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                local_path TEXT NOT NULL UNIQUE,
                remote_path TEXT NOT NULL,
                remote_id TEXT,
                base_local_hash TEXT,
                base_remote_hash TEXT,
                state TEXT,
                updated_at TEXT NOT NULL
            )
        """)

        conn.commit()
    finally:
        close_connection(conn)


def create_session(
    local_path: str,
    remote_path: str,
    remote_item_id: str,
    base_local_hash: str,
    base_remote_hash: str,
) -> None:
    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO files (
                local_path,
                remote_path,
                remote_id,
                base_local_hash,
                base_remote_hash,
                state,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(local_path) DO UPDATE SET
                remote_path = excluded.remote_path,
                remote_id = excluded.remote_id,
                base_local_hash = excluded.base_local_hash,
                base_remote_hash = excluded.base_remote_hash,
                state = excluded.state,
                updated_at = excluded.updated_at
            """,
            (
                str(local_path),
                remote_path,
                remote_item_id,
                base_local_hash,
                base_remote_hash,
                "active",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        conn.commit()
    finally:
        close_connection(conn)


def update_baseline(
    local_path: str,
    base_local_hash: str,
    base_remote_hash: str,
) -> None:
    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE files
            SET
                base_local_hash = ?,
                base_remote_hash = ?,
                updated_at = ?
            WHERE local_path = ?
            """,
            (
                base_local_hash,
                base_remote_hash,
                datetime.now(timezone.utc).isoformat(),
                local_path,
            ),
        )

        conn.commit()
    finally:
        close_connection(conn)


def get_stale_files(days: int) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM files WHERE state != 'cleaned' AND state != 'active' AND updated_at < ?",
            (cutoff,),
        ).fetchall()


def mark_cleaned(local_path: str) -> None:
    with (
        closing(get_connection()) as conn,
        conn,
    ):
        conn.execute(
            "UPDATE files SET state = 'cleaned', updated_at = ? WHERE local_path = ?",
            (datetime.now(timezone.utc).isoformat(), local_path),
        )


def mark_inactive(local_path: str) -> None:
    with (
        closing(get_connection()) as conn,
        conn,
    ):
        conn.execute(
            "UPDATE files SET state = 'inactive', updated_at = ? WHERE local_path = ?",
            (datetime.now(timezone.utc).isoformat(), local_path),
        )


def get_session(local_path: str):
    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            SELECT *
            FROM files
            WHERE local_path = ?
            """,
            (local_path,),
        )

        return cursor.fetchone()
    finally:
        close_connection(conn)


def close_connection(conn: sqlite3.Connection) -> None:
    conn.close()
