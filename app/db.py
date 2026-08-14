"""SQLite connection and schema helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    creator_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('creator', 'member')),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    payer_id INTEGER NOT NULL REFERENCES users(id),
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    description TEXT NOT NULL,
    expense_date TEXT NOT NULL,
    input_mode TEXT NOT NULL CHECK (input_mode IN ('manual', 'text_draft')),
    raw_input TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS expense_shares (
    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount_paise INTEGER NOT NULL CHECK (amount_paise >= 0),
    PRIMARY KEY (expense_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id, group_id);
CREATE INDEX IF NOT EXISTS idx_expenses_group_date ON expenses(group_id, expense_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_expense_shares_user ON expense_shares(user_id, expense_id);
"""

POSTGRES_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_display_name_lower ON users (LOWER(display_name))",
    """
    CREATE TABLE IF NOT EXISTS groups (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        creator_id BIGINT NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS group_members (
        group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('creator', 'member')),
        joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (group_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id BIGSERIAL PRIMARY KEY,
        group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
        payer_id BIGINT NOT NULL REFERENCES users(id),
        amount_paise BIGINT NOT NULL CHECK (amount_paise > 0),
        description TEXT NOT NULL,
        expense_date DATE NOT NULL,
        input_mode TEXT NOT NULL CHECK (input_mode IN ('manual', 'text_draft')),
        raw_input TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expense_shares (
        expense_id BIGINT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES users(id),
        amount_paise BIGINT NOT NULL CHECK (amount_paise >= 0),
        PRIMARY KEY (expense_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id, group_id)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_group_date ON expenses(group_id, expense_date DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_expense_shares_user ON expense_shares(user_id, expense_id)",
)


DatabaseTarget = str | Path


def is_postgres_database(target: DatabaseTarget) -> bool:
    value = str(target).strip().lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


def connect(db_path: DatabaseTarget) -> Any:
    """Open either local SQLite or persistent PostgreSQL with mapping-style rows."""
    if is_postgres_database(db_path):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("PostgreSQL requires the 'psycopg[binary]' dependency.") from error
        return psycopg.connect(str(db_path), row_factory=dict_row)

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sql_for_connection(connection: Any, query: str) -> str:
    if isinstance(connection, sqlite3.Connection):
        return query
    return query.replace("?", "%s")


def execute_query(connection: Any, query: str, parameters: Iterable[Any] = ()) -> Any:
    """Execute parameterized SQL using the active driver's placeholder syntax."""
    return connection.execute(_sql_for_connection(connection, query), tuple(parameters))


def executemany_query(connection: Any, query: str, parameter_rows: Iterable[Iterable[Any]]) -> Any:
    """Execute the same parameterized statement for several rows."""
    rows = [tuple(parameters) for parameters in parameter_rows]
    translated_query = _sql_for_connection(connection, query)
    if isinstance(connection, sqlite3.Connection):
        return connection.executemany(translated_query, rows)
    with connection.cursor() as cursor:
        cursor.executemany(translated_query, rows)
    return None


def insert_and_get_id(connection: Any, query: str, parameters: Iterable[Any]) -> int:
    """Insert one row and return its generated integer ID on SQLite or PostgreSQL."""
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.execute(query, tuple(parameters))
        return int(cursor.lastrowid)
    cursor = connection.execute(
        f"{_sql_for_connection(connection, query).rstrip().rstrip(';')} RETURNING id",
        tuple(parameters),
    )
    row = cursor.fetchone()
    return int(row["id"])


def initialize_database(db_path: DatabaseTarget) -> None:
    """Create the backend-specific schema if it does not exist."""
    with connect(db_path) as connection:
        if isinstance(connection, sqlite3.Connection):
            connection.executescript(SCHEMA)
        else:
            for statement in POSTGRES_SCHEMA:
                execute_query(connection, statement)
