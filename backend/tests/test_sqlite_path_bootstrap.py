"""Regression tests for the SQLite parent-directory bootstrap.

`data/` is git-ignored, so a fresh clone has no directory for
`sqlite:///data/insurance.db`. SQLite cannot create missing directories and
`alembic upgrade head` therefore failed with "unable to open database file"
before the application bootstrap could run. `ensure_sqlite_parent_dir` closes
that gap without affecting in-memory or server-based databases.
"""

import os

from backend.app.database import ensure_sqlite_parent_dir


def test_creates_missing_parent_directory_for_relative_sqlite_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "data").exists()

    ensure_sqlite_parent_dir("sqlite:///data/insurance.db")

    assert (tmp_path / "data").is_dir()


def test_creates_nested_parent_directory_for_absolute_sqlite_path(tmp_path):
    target = tmp_path / "nested" / "deeper" / "e2e.db"

    ensure_sqlite_parent_dir(f"sqlite:///{target.as_posix()}")

    assert target.parent.is_dir()


def test_in_memory_sqlite_is_untouched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ensure_sqlite_parent_dir("sqlite://")
    ensure_sqlite_parent_dir("sqlite+pysqlite:///:memory:")

    assert os.listdir(tmp_path) == []


def test_non_sqlite_url_is_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ensure_sqlite_parent_dir("postgresql+psycopg2://user:pass@db:5432/insurance")

    assert os.listdir(tmp_path) == []
