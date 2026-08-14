"""Balance aggregation helpers and a deterministic greedy settlement plan."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SettlementTransfer:
    from_user_id: int
    to_user_id: int
    amount_paise: int


def settlement_plan(balances: Mapping[int, int]) -> list[SettlementTransfer]:
    """Return a valid greedy creditor/debtor settlement plan.

    Positive balances are creditors; negative balances are debtors. Each loop settles at
    least one non-zero balance, so the plan uses at most p - 1 transfers for p non-zero
    members. The function deliberately does not claim globally minimum transfer count.
    """
    if sum(balances.values()) != 0:
        raise ValueError("Balances must sum to zero before settlement.")

    debtors = [(amount, user_id) for user_id, amount in balances.items() if amount < 0]
    creditors = [(-amount, user_id) for user_id, amount in balances.items() if amount > 0]
    heapq.heapify(debtors)
    heapq.heapify(creditors)
    transfers: list[SettlementTransfer] = []

    while debtors and creditors:
        negative_debt_amount, debtor_id = heapq.heappop(debtors)
        negative_credit_amount, creditor_id = heapq.heappop(creditors)
        debt_amount = -negative_debt_amount
        credit_amount = -negative_credit_amount
        transfer_amount = min(debt_amount, credit_amount)
        transfers.append(SettlementTransfer(debtor_id, creditor_id, transfer_amount))
        remaining_debt = debt_amount - transfer_amount
        remaining_credit = credit_amount - transfer_amount
        if remaining_debt:
            heapq.heappush(debtors, (-remaining_debt, debtor_id))
        if remaining_credit:
            heapq.heappush(creditors, (-remaining_credit, creditor_id))

    return transfers


def apply_transfers(balances: Mapping[int, int], transfers: list[SettlementTransfer]) -> dict[int, int]:
    """Apply transfers to balances; primarily useful as a testable invariant."""
    result = dict(balances)
    for transfer in transfers:
        if transfer.amount_paise <= 0:
            raise ValueError("Settlement transfers must be positive.")
        result[transfer.from_user_id] += transfer.amount_paise
        result[transfer.to_user_id] -= transfer.amount_paise
    return result
