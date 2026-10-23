import sqlite3

import pytest

from vision import config, db

REAL = list(db.MIGRATIONS)  # the migrations that ship with the app
LATEST = max([db.BASELINE_VERSION] + [v for v, _ in REAL])
NEW_COLUMN = [(LATEST + 1, "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;")]


def _columns(table):
    with db.connect() as conn:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _version():
    with db.connect() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def _backups():
    return list((config.data_dir() / "backups").glob("*.db"))


def _add_chat():
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES('keep', 'my chat', 0, 0)")


def test_new_database_is_at_the_latest_version_and_has_no_backup():
    assert _version() == LATEST
    assert {"kind", "context_tokens"} <= set(_columns("providers"))
    assert _backups() == []


def test_migration_adds_column_keeps_data_and_backs_up_once(monkeypatch):
    _add_chat()
    monkeypatch.setattr(db, "MIGRATIONS", REAL + NEW_COLUMN)
    db.init_db()
    assert "pinned" in _columns("conversations")
    assert _version() == LATEST + 1
    with db.connect() as conn:
        assert conn.execute("SELECT title, pinned FROM conversations WHERE id='keep'").fetchone()[:] == ("my chat", 0)
    assert len(_backups()) == 1
    old = sqlite3.connect(_backups()[0])  # the backup is a real copy from BEFORE the migration
    assert "pinned" not in [r[1] for r in old.execute("PRAGMA table_info(conversations)")]
    assert old.execute("SELECT title FROM conversations").fetchone()[0] == "my chat"
    old.close()
    db.init_db()  # nothing pending: no second migration, no second backup
    assert len(_backups()) == 1 and _version() == LATEST + 1


def test_database_from_the_first_release_is_upgraded_through_every_migration():
    path = config.db_path()
    for suffix in ("", "-wal", "-shm"):
        (path.parent / (path.name + suffix)).unlink(missing_ok=True)
    legacy = sqlite3.connect(path)  # exactly what version 0.1.x created: baseline schema, user_version 0
    legacy.executescript(db.SCHEMA)
    legacy.execute("INSERT INTO providers(id, name, base_url, model_name, is_default) VALUES('p1', 'Old', 'https://x/v1', 'm', 1)")
    legacy.commit()
    legacy.close()
    db.init_db()
    assert _version() == LATEST
    assert {"kind", "context_tokens"} <= set(_columns("providers"))
    with db.connect() as conn:
        row = conn.execute("SELECT name, kind, context_tokens FROM providers WHERE id='p1'").fetchone()
    assert tuple(row) == ("Old", "cloud", 0)  # old providers stay cloud providers
    assert len(_backups()) == 1


def test_failed_migration_stops_with_a_backup_and_leaves_data_intact(monkeypatch):
    _add_chat()
    monkeypatch.setattr(db, "MIGRATIONS", REAL + [(LATEST + 1, "ALTER TABLE conversations ADD COLUMN ok INTEGER;"),
                                                  (LATEST + 2, "ALTER TABLE no_such_table ADD COLUMN x INTEGER;")])
    with pytest.raises(RuntimeError, match=f"version {LATEST + 2}"):
        db.init_db()
    assert _version() == LATEST + 1  # the good step stayed applied, the bad one was rolled back
    assert len(_backups()) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT title FROM conversations WHERE id='keep'").fetchone()[0] == "my chat"


def test_only_the_five_newest_backups_are_kept(monkeypatch):
    _add_chat()
    for i in range(7):
        monkeypatch.setattr(db, "MIGRATIONS", REAL + [(LATEST + 1 + i, f"ALTER TABLE conversations ADD COLUMN c{i} INTEGER;")])
        monkeypatch.setattr(db.time, "strftime", lambda fmt, i=i: f"2026010{i}-000000")
        db.init_db()
    assert len(_backups()) == db.KEEP_BACKUPS


def test_wrong_schema_at_the_latest_version_is_repaired_with_a_backup():
    """A database stamped with the right version but built from a different schema (an interrupted
    release) still gets the columns the code needs, so chatting keeps working."""
    path = config.db_path()
    for suffix in ("", "-wal", "-shm"):
        (path.parent / (path.name + suffix)).unlink(missing_ok=True)
    old = sqlite3.connect(path)  # exactly what the broken release created: version 3, wrong columns
    old.executescript(db.SCHEMA)
    old.execute("ALTER TABLE providers ADD COLUMN local INTEGER NOT NULL DEFAULT 0")
    old.execute("ALTER TABLE messages ADD COLUMN model TEXT NOT NULL DEFAULT ''")
    old.execute("INSERT INTO providers(id, name, base_url, model_name, is_default, local) VALUES('p1','Ollama','http://localhost:11434/v1','llama3',1,1)")
    old.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES('c1','chat',0,0)")
    old.execute("INSERT INTO messages(conversation_id, role, content, model, created_at) VALUES('c1','assistant','hi','llama3',0)")
    old.execute(f"PRAGMA user_version = {LATEST}")
    old.commit()
    old.close()

    db.init_db()  # must repair, not crash
    assert _version() == LATEST == 3
    assert {"kind", "context_tokens"} <= set(_columns("providers"))
    assert {"provider_id", "model_name"} <= set(_columns("conversations"))
    assert "model_name" in _columns("messages")
    with db.connect() as conn:
        assert conn.execute("SELECT kind FROM providers WHERE id='p1'").fetchone()[0] == "local"  # old flag carried over
        assert conn.execute("SELECT model_name FROM messages WHERE conversation_id='c1'").fetchone()[0] == "llama3"
    assert len(_backups()) == 1  # the file was copied before it was changed
