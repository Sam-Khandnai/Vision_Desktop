import sqlite3

import pytest

from vision import config, db

NEW_COLUMN = [(2, "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;")]


def _conversation_columns():
    with db.connect() as conn:
        return [r[1] for r in conn.execute("PRAGMA table_info(conversations)")]


def _version():
    with db.connect() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def _backups():
    return list((config.data_dir() / "backups").glob("*.db"))


def _add_chat():
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES('keep', 'my chat', 0, 0)")


def test_new_database_gets_baseline_version_and_no_backup():
    assert _version() == db.BASELINE_VERSION
    assert _backups() == []


def test_migration_adds_column_keeps_data_and_backs_up_once(monkeypatch):
    _add_chat()
    monkeypatch.setattr(db, "MIGRATIONS", NEW_COLUMN)
    db.init_db()
    assert "pinned" in _conversation_columns()
    assert _version() == 2
    with db.connect() as conn:
        assert conn.execute("SELECT title, pinned FROM conversations WHERE id='keep'").fetchone()[:] == ("my chat", 0)
    assert len(_backups()) == 1
    # the backup is a real copy from BEFORE the migration
    old = sqlite3.connect(_backups()[0])
    assert "pinned" not in [r[1] for r in old.execute("PRAGMA table_info(conversations)")]
    assert old.execute("SELECT title FROM conversations").fetchone()[0] == "my chat"
    old.close()
    db.init_db()  # nothing pending: no second migration, no second backup
    assert len(_backups()) == 1 and _version() == 2


def test_database_from_first_release_without_version_is_upgraded(monkeypatch):
    _add_chat()
    with db.connect() as conn:
        conn.execute("PRAGMA user_version = 0")  # how databases looked before migrations existed
    monkeypatch.setattr(db, "MIGRATIONS", NEW_COLUMN)
    db.init_db()
    assert _version() == 2 and "pinned" in _conversation_columns()


def test_failed_migration_stops_with_a_backup_and_leaves_data_intact(monkeypatch):
    _add_chat()
    monkeypatch.setattr(db, "MIGRATIONS", [(2, "ALTER TABLE conversations ADD COLUMN ok INTEGER;"),
                                           (3, "ALTER TABLE no_such_table ADD COLUMN x INTEGER;")])
    with pytest.raises(RuntimeError, match="version 3"):
        db.init_db()
    assert _version() == 2  # step 2 stayed applied, step 3 was rolled back
    assert len(_backups()) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT title FROM conversations WHERE id='keep'").fetchone()[0] == "my chat"


def test_only_the_five_newest_backups_are_kept(monkeypatch):
    _add_chat()
    for i in range(7):
        monkeypatch.setattr(db, "MIGRATIONS", [(2 + i, f"ALTER TABLE conversations ADD COLUMN c{i} INTEGER;")])
        monkeypatch.setattr(db.time, "strftime", lambda fmt, i=i: f"2026010{i}-000000")
        db.init_db()
    assert len(_backups()) == db.KEEP_BACKUPS
