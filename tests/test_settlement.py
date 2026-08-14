from app.services.settlement import apply_transfers, settlement_plan


def test_greedy_settlement_clears_all_balances() -> None:
    balances = {1: 9_000, 2: -5_000, 3: -2_500, 4: -1_500}
    transfers = settlement_plan(balances)
    assert len(transfers) <= 3
    assert all(transfer.amount_paise > 0 for transfer in transfers)
    assert set(apply_transfers(balances, transfers).values()) == {0}


def test_unbalanced_input_is_rejected() -> None:
    try:
        settlement_plan({1: 100, 2: -50})
    except ValueError as error:
        assert "sum to zero" in str(error)
    else:
        raise AssertionError("Expected unbalanced inputs to be rejected")
