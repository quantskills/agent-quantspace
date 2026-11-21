from __future__ import annotations

import pytest

from skills.live_trade import SizingLimitError, size_targets


def test_stock_targets_round_down_to_board_lots():
    (item,) = size_targets({"510300.SH": 0.35}, 100_000, {"510300.SH": 4.123})
    assert item.raw_units == pytest.approx(8489.0, abs=0.1)
    assert item.units == 8400
    assert item.lot_size == 100
    assert item.notional == pytest.approx(8400 * 4.123)


def test_futures_size_in_contracts_with_explicit_multiplier():
    sized = size_targets(
        {"RB2601.SHF": 0.5, "M2605.DCE": -0.4},
        1_000_000,
        {"RB2601.SHF": 3500.0, "M2605.DCE": 2820.0},
        multipliers={"RB2601.SHF": 10, "M2605.DCE": 10},
    )
    by_symbol = {item.symbol: item for item in sized}
    assert by_symbol["RB2601.SHF"].units == 14
    assert by_symbol["M2605.DCE"].units == -14
    assert by_symbol["RB2601.SHF"].lot_size == 1


def test_nearest_rounding_rounds_half_away_from_zero():
    sized = size_targets(
        {"RB2601.SHF": 0.5, "M2605.DCE": -0.5},
        290_000,
        {"RB2601.SHF": 1000.0, "M2605.DCE": 1000.0},
        multipliers={"RB2601.SHF": 10, "M2605.DCE": 10},
        rounding="nearest",
    )
    assert [item.units for item in sized] == [-15, 15]


def test_zero_weight_sizes_to_zero_units():
    (item,) = size_targets({"510300.SH": 0.0}, 100_000, {"510300.SH": 4.0})
    assert item.units == 0 and item.notional == 0


def test_missing_inputs_are_reported_not_guessed():
    with pytest.raises(ValueError) as error:
        size_targets({"510300.SH": 0.5, "RB2601.SHF": 0.5}, 100_000, {"RB2601.SHF": 3500.0})
    message = str(error.value)
    assert "510300.SH: missing or invalid price" in message
    assert "RB2601.SHF: futures symbol needs a contract multiplier" in message


def test_caps_raise_with_every_breach_instead_of_clipping():
    with pytest.raises(SizingLimitError) as error:
        size_targets(
            {"RB2601.SHF": 0.5, "M2605.DCE": 0.5},
            1_000_000,
            {"RB2601.SHF": 3500.0, "M2605.DCE": 2820.0},
            multipliers={"RB2601.SHF": 10, "M2605.DCE": 10},
            max_units=10,
            max_notional=400_000,
        )
    assert len(error.value.breaches) == 4


@pytest.mark.parametrize("capital", [0, -1, float("nan")])
def test_capital_must_be_positive(capital):
    with pytest.raises(ValueError, match="capital"):
        size_targets({"510300.SH": 1.0}, capital, {"510300.SH": 4.0})
