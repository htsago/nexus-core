import sqlite3
from pathlib import Path

from src.config import settings


def _assert_fts5() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
    except sqlite3.OperationalError as exc:
        raise RuntimeError("SQLite FTS5 is required but not available.") from exc
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.SQLITE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    _assert_fts5()
    conn = get_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                framework    TEXT    NOT NULL,
                url          TEXT    NOT NULL,
                checksum     TEXT    NOT NULL,
                ingested_at  TEXT    NOT NULL,
                chunk_count  INTEGER NOT NULL DEFAULT 0,
                UNIQUE(framework, url)
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
                framework, url, chunk_id, content,
                tokenize='porter unicode61'
            )
            """
        )
    conn.close()


def upsert_source(
    framework: str, url: str, checksum: str, ingested_at: str, chunk_count: int
) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO sources (framework, url, checksum, ingested_at, chunk_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(framework, url) DO UPDATE SET
                checksum    = excluded.checksum,
                ingested_at = excluded.ingested_at,
                chunk_count = excluded.chunk_count
            """,
            (framework, url, checksum, ingested_at, chunk_count),
        )
    conn.close()


def get_source(framework: str, url: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sources WHERE framework = ? AND url = ?", (framework, url)
    ).fetchone()
    conn.close()
    return row


def replace_fts_chunks(framework: str, url: str, chunks: list[str]) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "DELETE FROM content_fts WHERE framework = ? AND url = ?", (framework, url)
        )
        conn.executemany(
            "INSERT INTO content_fts (framework, url, chunk_id, content) VALUES (?, ?, ?, ?)",
            [(framework, url, str(i), chunk) for i, chunk in enumerate(chunks)],
        )
    conn.close()


def fts_search(framework: str, query: str, k: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT framework, url, chunk_id, content, rank
        FROM content_fts
        WHERE framework = ? AND content MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (framework, query, k),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_sources(framework: str | None = None) -> list[dict]:
    conn = get_connection()
    if framework:
        rows = conn.execute(
            "SELECT * FROM sources WHERE framework = ? ORDER BY ingested_at DESC",
            (framework,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY framework, ingested_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_fts_chunks(framework: str) -> list[dict]:
    """Retrieve all stored chunks for a framework (used during FAISS rebuild)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT framework, url, chunk_id, content FROM content_fts WHERE framework = ?",
        (framework,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
