import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app.db import connect, initialize_database
from app.repositories import (
    create_equal_split_expense,
    group_balances,
    list_group_members,
    seed_demo_data,
)
from app.services.money import MoneyValidationError
from app.services.settlement import apply_transfers, settlement_plan


def test_confirmed_expense_preserves_balance_invariants(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    initialize_database(db_path)
    seed_demo_data(db_path)
    members = list_group_members(db_path, 1)
    member_ids = [int(member["id"]) for member in members]
    payer_id = member_ids[0]
    create_equal_split_expense(
        db_path,
        group_id=1,
        actor_id=payer_id,
        payer_id=payer_id,
        amount_paise=100,
        description="Tea",
        expense_date="2026-08-11",
        participant_ids=member_ids[:3],
    )
    balances = group_balances(db_path, 1)
    assert sum(int(row["balance_paise"]) for row in balances) == 0
    assert next(int(row["balance_paise"]) for row in balances if int(row["id"]) == payer_id) == 67


def test_non_member_cannot_write_expense(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    initialize_database(db_path)
    seed_demo_data(db_path)
    members = list_group_members(db_path, 1)
    member_ids = [int(member["id"]) for member in members]
    with pytest.raises(PermissionError):
        create_equal_split_expense(
            db_path,
            group_id=1,
            actor_id=999,
            payer_id=member_ids[0],
            amount_paise=100,
            description="Tea",
            expense_date="2026-08-11",
            participant_ids=member_ids,
        )


def test_description_longer_than_120_characters_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    initialize_database(db_path)
    seed_demo_data(db_path)
    members = list_group_members(db_path, 1)
    member_ids = [int(member["id"]) for member in members]
    with pytest.raises(MoneyValidationError, match="1 to 120 characters"):
        create_equal_split_expense(
            db_path,
            group_id=1,
            actor_id=member_ids[0],
            payer_id=member_ids[0],
            amount_paise=100,
            description="x" * 121,
            expense_date="2026-08-11",
            participant_ids=member_ids[:2],
        )


def test_failed_share_insert_rolls_back_the_entire_expense(tmp_path: Path) -> None:
    db_path = tmp_path / "transaction.db"
    initialize_database(db_path)
    seed_demo_data(db_path)
    member_ids = [int(member["id"]) for member in list_group_members(db_path, 1)]
    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER force_share_failure
            BEFORE INSERT ON expense_shares
            BEGIN
                SELECT RAISE(ABORT, 'forced share failure');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced share failure"):
        create_equal_split_expense(
            db_path,
            group_id=1,
            actor_id=member_ids[0],
            payer_id=member_ids[0],
            amount_paise=100,
            description="Rollback proof",
            expense_date=date.today().isoformat(),
            participant_ids=member_ids[:3],
        )

    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM expense_shares").fetchone()[0] == 0


def test_many_remainder_expenses_preserve_all_financial_invariants(tmp_path: Path) -> None:
    db_path = tmp_path / "many-expenses.db"
    initialize_database(db_path)
    seed_demo_data(db_path)
    member_ids = [int(member["id"]) for member in list_group_members(db_path, 1)]

    scenarios = [
        (101, member_ids[0], member_ids[:3]),
        (2_503, member_ids[1], member_ids[1:]),
        (9_999, member_ids[2], member_ids),
        (1, member_ids[3], member_ids[:2]),
        (74_321, member_ids[0], member_ids[2:]),
    ]
    for amount_paise, payer_id, participants in scenarios:
        create_equal_split_expense(
            db_path,
            group_id=1,
            actor_id=member_ids[0],
            payer_id=payer_id,
            amount_paise=amount_paise,
            description=f"Invariant case {amount_paise}",
            expense_date=date.today().isoformat(),
            participant_ids=participants,
        )

    with connect(db_path) as connection:
        stored_expenses = connection.execute(
            """
            SELECT e.id, e.amount_paise, SUM(es.amount_paise) AS share_total
            FROM expenses AS e
            JOIN expense_shares AS es ON es.expense_id = e.id
            GROUP BY e.id, e.amount_paise
            """
        ).fetchall()
    assert len(stored_expenses) == len(scenarios)
    assert all(int(row["amount_paise"]) == int(row["share_total"]) for row in stored_expenses)

    balances = {int(row["id"]): int(row["balance_paise"]) for row in group_balances(db_path, 1)}
    assert sum(balances.values()) == 0
    transfers = settlement_plan(balances)
    assert all(transfer.amount_paise > 0 for transfer in transfers)
    assert set(apply_transfers(balances, transfers).values()) == {0}
