"""SQLite storage (WAL mode, FTS5 for search). One short-lived connection per operation."""
from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  summary_upto INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  tool_json TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS providers(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  model_name TEXT NOT NULL DEFAULT '',
  is_default INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mcp_servers(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  transport TEXT NOT NULL,
  config_json TEXT NOT NULL DEFAULT '{}',
  enabled INTEGER NOT NULL DEFAULT 1,
  approval TEXT NOT NULL DEFAULT 'smart',
  catalog_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS profile(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  source_conversation TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(text, content='memories', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content='messages', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
"""


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def now() -> float:
    return time.time()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Schema changes for released versions go here, at the END, as (version, SQL). Never edit SCHEMA above or old entries.
# Example:  (3, "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;"),
MIGRATIONS: list[tuple[int, str]] = [
    # 2: providers can point at a local server (Ollama, LM Studio ...) that needs no API key,
    #    and they remember the context window their server really loads.
    (2, "ALTER TABLE providers ADD COLUMN kind TEXT NOT NULL DEFAULT 'cloud';\n"
        "ALTER TABLE providers ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 0;"),
    # 3: a chat remembers which provider/model answered it, and every message remembers the model that wrote it.
    (3, "ALTER TABLE conversations ADD COLUMN provider_id TEXT NOT NULL DEFAULT '';\n"
        "ALTER TABLE conversations ADD COLUMN model_name TEXT NOT NULL DEFAULT '';\n"
        "ALTER TABLE messages ADD COLUMN model_name TEXT NOT NULL DEFAULT '';"),
]
BASELINE_VERSION = 1  # SCHEMA above is version 1 (databases from the first releases have user_version 0)
KEEP_BACKUPS = 5

# Columns the code needs. A database that was stamped with a version number but built from a different
# schema (e.g. by an interrupted release) still gets the columns it is missing: ALTER TABLE cannot say
# "ADD COLUMN IF NOT EXISTS", so we compare with the real table and add only what is absent.
REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
    "providers": {
        "kind": "TEXT NOT NULL DEFAULT 'cloud'",
        "context_tokens": "INTEGER NOT NULL DEFAULT 0",
    },
    "conversations": {
        "provider_id": "TEXT NOT NULL DEFAULT ''",
        "model_name": "TEXT NOT NULL DEFAULT ''",
    },
    "messages": {
        "model_name": "TEXT NOT NULL DEFAULT ''",
    },
}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _missing_columns() -> dict[str, list[str]]:
    """Which columns the code needs but this database file does not have yet, per table."""
    missing: dict[str, list[str]] = {}
    with connect() as conn:
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, columns in REQUIRED_COLUMNS.items():
            if table not in existing:
                continue
            have = _table_columns(conn, table)
            gone = [name for name in columns if name not in have]
            if gone:
                missing[table] = gone
    return missing


def _reconcile_schema() -> None:
    """Add any column the code needs but the file lacks (the file stays usable: it is copied first)."""
    with connect() as conn:
        for table, columns in REQUIRED_COLUMNS.items():
            have = _table_columns(conn, table)
            for name in columns:
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {columns[name]}")
            # earlier builds stored the answering model in `model` and the local flag in `local`: carry them over
            if table == "messages" and "model" in have and "model_name" not in have:
                conn.execute("UPDATE messages SET model_name=model WHERE model_name='' AND model<>''")
            if table == "providers" and "local" in have and "kind" not in have:
                conn.execute("UPDATE providers SET kind='local' WHERE local=1")


def _read_version(path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _backup(path, version: int):
    folder = config.data_dir() / "backups"
    folder.mkdir(exist_ok=True)
    dest = folder / f"vision-v{version}-{time.strftime('%Y%m%d-%H%M%S')}.db"
    src, dst = sqlite3.connect(path), sqlite3.connect(dest)
    try:
        src.backup(dst)  # consistent copy even while the database is in WAL mode
    finally:
        dst.close()
        src.close()
    for old in sorted(folder.glob("vision-v*.db"))[:-KEEP_BACKUPS]:
        old.unlink()
    return dest


def init_db() -> None:
    path = config.db_path()
    existing = path.exists() and path.stat().st_size > 0
    start = max(_read_version(path), BASELINE_VERSION) if existing else BASELINE_VERSION
    pending = [(v, sql) for v, sql in sorted(MIGRATIONS) if v > start]
    backup = _backup(path, start) if (existing and pending) else None
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {start}")
    for version, sql in pending:
        with connect() as conn:
            try:
                conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
            except Exception as exc:
                raise RuntimeError(
                    f"Database migration to version {version} failed: {exc}. "
                    + (f"Your data was backed up to {backup}." if backup else "")
                ) from exc
    # A database can carry the right version number yet a different schema (an interrupted release).
    # Bring the file up to the columns the code needs - after a backup - so chats keep working.
    if existing and _missing_columns():
        _backup(path, start)
        _reconcile_schema()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ---- key/value helpers (profile & settings) ----

def kv_get_all(table: str) -> dict[str, str]:
    assert table in ("profile", "settings")
    with connect() as conn:
        return {r["key"]: r["value"] for r in conn.execute(f"SELECT key, value FROM {table}")}


def kv_set(table: str, key: str, value: str) -> None:
    assert table in ("profile", "settings")
    with connect() as conn:
        conn.execute(
            f"INSERT INTO {table}(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def setting_bool(key: str, default: bool) -> bool:
    value = kv_get_all("settings").get(key)
    if value is None:
        return default
    return value == "1"
