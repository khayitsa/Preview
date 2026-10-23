"""SQLite access: one connection per request, plus schema setup.

Connections run in autocommit mode (``isolation_level=None``); code that writes opens an
explicit ``BEGIN IMMEDIATE`` transaction so concurrent writers queue instead of failing.
"""

import sqlite3

from flask import current_app, g

from . import schema


def connect(path):
    """Open a new connection. Callers are responsible for closing it."""
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=30000')
    return db


def get_db():
    """The current request's connection, opened on first use."""
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'])
    return g.db


def close_db(_exception=None):
    """Roll back anything left open (a failed request) and close the connection."""
    db = g.pop('db', None)
    if db is not None:
        if db.in_transaction:
            db.rollback()
        db.close()


def init_db(path):
    """Create missing tables and indexes and upgrade databases from older releases."""
    with connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        for statement in schema.TABLES + schema.INDEXES:
            db.execute(statement)
        for table, new_columns in schema.LATE_COLUMNS.items():
            existing = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
            for column in new_columns:
                if column not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    db.close()
