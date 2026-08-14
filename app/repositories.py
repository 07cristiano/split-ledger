"""Parameterized relational queries for SplitLedger's SQLite/PostgreSQL backends."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from app.db import (
    connect,
    execute_query,
    executemany_query,
    insert_and_get_id,
    is_postgres_database,
)
from app.security import hash_password
from app.services.dates import validate_expense_date
from app.services.money import MoneyValidationError, equal_split


DEMO_PASSWORD = "demo123"
DEMO_USERS = ("Asha", "Rohan", "Meera", "Arjun")


def fetch_user_by_name(db_path: str | Path, display_name: str) -> sqlite3.Row | None:
    with connect(db_path) as connection:
        return execute_query(
            connection,
            "SELECT id, display_name, password_hash FROM users WHERE display_name = ?",
            (display_name.strip(),),
        ).fetchone()


def fetch_user(db_path: str | Path, user_id: int) -> sqlite3.Row | None:
    with connect(db_path) as connection:
        return execute_query(
            connection, "SELECT id, display_name FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def list_users(db_path: str | Path) -> list[sqlite3.Row]:
    with connect(db_path) as connection:
        return execute_query(
            connection, "SELECT id, display_name FROM users ORDER BY LOWER(display_name)"
        ).fetchall()


def create_user(db_path: str | Path, display_name: str, password: str) -> int:
    with connect(db_path) as connection:
        return insert_and_get_id(
            connection,
            "INSERT INTO users (display_name, password_hash) VALUES (?, ?)",
            (display_name.strip(), hash_password(password)),
        )


def create_group(db_path: str | Path, name: str, creator_id: int, member_ids: list[int]) -> int:
    unique_member_ids = {creator_id, *member_ids}
    with connect(db_path) as connection:
        group_id = insert_and_get_id(
            connection,
            "INSERT INTO groups (name, creator_id) VALUES (?, ?)", (name.strip(), creator_id)
        )
        executemany_query(
            connection,
            "INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, ?)",
            [
                (group_id, user_id, "creator" if user_id == creator_id else "member")
                for user_id in sorted(unique_member_ids)
            ],
        )
        return group_id


def list_groups_for_user(db_path: str | Path, user_id: int) -> list[sqlite3.Row]:
    with connect(db_path) as connection:
        return execute_query(
            connection,
            """
            SELECT g.id, g.name, g.creator_id, COUNT(gm_all.user_id) AS member_count
            FROM groups AS g
            JOIN group_members AS gm_self ON gm_self.group_id = g.id AND gm_self.user_id = ?
            JOIN group_members AS gm_all ON gm_all.group_id = g.id
            GROUP BY g.id, g.name, g.creator_id
            ORDER BY g.created_at DESC, g.id DESC
            """,
            (user_id,),
        ).fetchall()


def fetch_group_for_member(db_path: str | Path, group_id: int, user_id: int) -> sqlite3.Row | None:
    with connect(db_path) as connection:
        return execute_query(
            connection,
            """
            SELECT g.id, g.name, g.creator_id, gm.role AS current_user_role
            FROM groups AS g
            JOIN group_members AS gm ON gm.group_id = g.id
            WHERE g.id = ? AND gm.user_id = ?
            """,
            (group_id, user_id),
        ).fetchone()


def list_group_members(db_path: str | Path, group_id: int) -> list[sqlite3.Row]:
    with connect(db_path) as connection:
        return execute_query(
            connection,
            """
            SELECT u.id, u.display_name, gm.role
            FROM group_members AS gm
            JOIN users AS u ON u.id = gm.user_id
            WHERE gm.group_id = ?
            ORDER BY LOWER(u.display_name)
            """,
            (group_id,),
        ).fetchall()


def create_equal_split_expense(
    db_path: str | Path,
    *,
    group_id: int,
    actor_id: int,
    payer_id: int,
    amount_paise: int,
    description: str,
    expense_date: str,
    participant_ids: Iterable[int],
    input_mode: str = "manual",
    raw_input: str | None = None,
) -> int:
    """Validate and persist one confirmed expense in a single database transaction."""
    participants = list(participant_ids)
    description = description.strip()
    if not description or len(description) > 120:
        raise MoneyValidationError("Description must contain 1 to 120 characters.")
    if input_mode not in {"manual", "text_draft"}:
        raise MoneyValidationError("Unsupported input mode.")
    expense_date = validate_expense_date(expense_date)

    shares = equal_split(amount_paise, participants)
    with connect(db_path) as connection:
        authorized = execute_query(
            connection,
            "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, actor_id),
        ).fetchone()
        if authorized is None:
            raise PermissionError("You are not a member of this group.")
        allowed_rows = execute_query(
            connection,
            "SELECT user_id FROM group_members WHERE group_id = ?", (group_id,)
        ).fetchall()
        allowed_ids = {int(row["user_id"]) for row in allowed_rows}
        if payer_id not in allowed_ids or not set(shares).issubset(allowed_ids):
            raise MoneyValidationError("Payer and participants must belong to this group.")

        expense_id = insert_and_get_id(
            connection,
            """
            INSERT INTO expenses
                (group_id, payer_id, amount_paise, description, expense_date, input_mode, raw_input)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, payer_id, amount_paise, description, expense_date, input_mode, raw_input),
        )
        executemany_query(
            connection,
            "INSERT INTO expense_shares (expense_id, user_id, amount_paise) VALUES (?, ?, ?)",
            [(expense_id, user_id, share_paise) for user_id, share_paise in shares.items()],
        )
        return expense_id


def list_expenses(db_path: str | Path, group_id: int) -> list[sqlite3.Row]:
    shares_expression = (
        "STRING_AGG(share_user.display_name || ':' || es.amount_paise::text, '|' "
        "ORDER BY share_user.display_name)"
        if is_postgres_database(db_path)
        else "GROUP_CONCAT(share_user.display_name || ':' || es.amount_paise, '|')"
    )
    with connect(db_path) as connection:
        return execute_query(
            connection,
            f"""
            SELECT e.id, e.amount_paise, e.description, e.expense_date, e.input_mode,
                   payer.display_name AS payer_name,
                   {shares_expression} AS shares
            FROM expenses AS e
            JOIN users AS payer ON payer.id = e.payer_id
            JOIN expense_shares AS es ON es.expense_id = e.id
            JOIN users AS share_user ON share_user.id = es.user_id
            WHERE e.group_id = ?
            GROUP BY e.id, e.amount_paise, e.description, e.expense_date, e.input_mode, payer.display_name
            ORDER BY e.expense_date DESC, e.id DESC
            """,
            (group_id,),
        ).fetchall()


def group_balances(db_path: str | Path, group_id: int) -> list[sqlite3.Row]:
    """Return each group member's exact net balance in paise."""
    with connect(db_path) as connection:
        return execute_query(
            connection,
            """
            SELECT u.id, u.display_name,
                   CAST(COALESCE((
                       SELECT SUM(e.amount_paise)
                       FROM expenses AS e
                       WHERE e.group_id = ? AND e.payer_id = u.id
                   ), 0) - COALESCE((
                       SELECT SUM(es.amount_paise)
                       FROM expense_shares AS es
                       JOIN expenses AS e ON e.id = es.expense_id
                       WHERE e.group_id = ? AND es.user_id = u.id
                   ), 0) AS BIGINT) AS balance_paise
            FROM group_members AS gm
            JOIN users AS u ON u.id = gm.user_id
            WHERE gm.group_id = ?
            ORDER BY LOWER(u.display_name)
            """,
            (group_id, group_id, group_id),
        ).fetchall()


def seed_demo_data(db_path: str | Path) -> None:
    """Create a deterministic local demo group once, without personal data."""
    with connect(db_path) as connection:
        if is_postgres_database(db_path):
            # Serialize only the first concurrent serverless cold-start seed attempt.
            execute_query(connection, "SELECT pg_advisory_xact_lock(824695507)")
        existing = execute_query(connection, "SELECT id FROM users LIMIT 1").fetchone()
        if existing:
            return
        user_ids: dict[str, int] = {}
        for display_name in DEMO_USERS:
            user_ids[display_name] = insert_and_get_id(
                connection,
                "INSERT INTO users (display_name, password_hash) VALUES (?, ?)",
                (display_name, hash_password(DEMO_PASSWORD)),
            )
        group_id = insert_and_get_id(
            connection,
            "INSERT INTO groups (name, creator_id) VALUES (?, ?)",
            ("Weekend getaway", user_ids["Asha"]),
        )
        executemany_query(
            connection,
            "INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, ?)",
            [
                (group_id, user_id, "creator" if name == "Asha" else "member")
                for name, user_id in user_ids.items()
            ],
        )


def today_iso() -> str:
    return date.today().isoformat()
