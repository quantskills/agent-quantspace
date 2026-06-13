"""Generic Shapley attribution helpers."""

from __future__ import annotations

import itertools
import math
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

Coalition = frozenset[Any]
CoalitionValues = Mapping[Any, float] | Iterable[tuple[Any, float]]


def exact_shapley_values(
    players: Iterable[Any],
    coalition_values: CoalitionValues,
    empty_value: float = 0.0,
    *,
    value_name: str = "value",
) -> pd.DataFrame:
    """Compute exact Shapley values from a complete coalition-value table."""
    ordered_players = _normalize_players(players)
    values = _normalize_coalition_values(coalition_values)
    empty = _coalition_value(values, frozenset(), ordered_players, empty_value)
    n_players = len(ordered_players)
    total_weight = math.factorial(n_players)
    shapley = dict.fromkeys(ordered_players, 0.0)

    for player in ordered_players:
        others = [candidate for candidate in ordered_players if candidate != player]
        player_key = frozenset([player])
        for size in range(len(others) + 1):
            weight = math.factorial(size) * math.factorial(n_players - size - 1) / total_weight
            for subset in itertools.combinations(others, size):
                coalition = frozenset(subset)
                with_player = coalition | player_key
                before = _coalition_value(values, coalition, ordered_players, empty_value)
                after = _coalition_value(values, with_player, ordered_players, empty_value)
                shapley[player] += weight * (after - before)

    return _shapley_frame(
        ordered_players,
        shapley,
        std=dict.fromkeys(ordered_players, 0.0),
        n_permutations=math.factorial(n_players),
        value_name=value_name,
        total_value=_coalition_value(values, frozenset(ordered_players), ordered_players, empty)
        - empty,
    )


def monte_carlo_shapley_values(
    players: Iterable[Any],
    value_fn: Callable[[frozenset[Any]], float],
    n_permutations: int = 128,
    random_state: int | np.random.Generator | None = None,
    *,
    value_name: str = "value",
) -> pd.DataFrame:
    """Estimate Shapley values by averaging marginal contributions over permutations."""
    ordered_players = _normalize_players(players)
    if n_permutations <= 0:
        raise ValueError("n_permutations must be positive.")

    rng = _make_rng(random_state)
    contributions = {player: np.empty(n_permutations, dtype=float) for player in ordered_players}
    indices = np.arange(len(ordered_players))

    for permutation_idx in range(n_permutations):
        coalition: frozenset[Any] = frozenset()
        previous_value = float(value_fn(coalition))
        for player_idx in rng.permutation(indices):
            player = ordered_players[int(player_idx)]
            next_coalition = coalition | frozenset([player])
            next_value = float(value_fn(next_coalition))
            contributions[player][permutation_idx] = next_value - previous_value
            coalition = next_coalition
            previous_value = next_value

    mean = {player: float(values.mean()) for player, values in contributions.items()}
    std = {
        player: float(values.std(ddof=1)) if n_permutations > 1 else 0.0
        for player, values in contributions.items()
    }
    empty = float(value_fn(frozenset()))
    total_value = float(value_fn(frozenset(ordered_players))) - empty
    return _shapley_frame(
        ordered_players,
        mean,
        std=std,
        n_permutations=n_permutations,
        value_name=value_name,
        total_value=total_value,
    )


def grouped_players(
    mapping: Mapping[Any, Any] | Iterable[tuple[Any, Any]],
) -> dict[Any, tuple[Any, ...]]:
    """Group raw players by stable first-seen group order."""
    items = mapping.items() if isinstance(mapping, Mapping) else mapping
    grouped: OrderedDict[Any, list[Any]] = OrderedDict()
    for raw_player, group_name in items:
        grouped.setdefault(group_name, []).append(raw_player)
    return {group_name: tuple(members) for group_name, members in grouped.items()}


def pairwise_interaction_matrix(
    players: Iterable[Any],
    coalition_values: CoalitionValues,
    empty_value: float = 0.0,
) -> pd.DataFrame:
    """Compute pairwise second-order interaction diagnostics."""
    ordered_players = _normalize_players(players)
    values = _normalize_coalition_values(coalition_values)
    empty = _coalition_value(values, frozenset(), ordered_players, empty_value)
    matrix = pd.DataFrame(0.0, index=ordered_players, columns=ordered_players, dtype=float)

    for left, right in itertools.combinations(ordered_players, 2):
        left_value = _coalition_value(values, frozenset([left]), ordered_players, empty_value)
        right_value = _coalition_value(values, frozenset([right]), ordered_players, empty_value)
        pair_value = _coalition_value(
            values, frozenset([left, right]), ordered_players, empty_value
        )
        interaction = pair_value - left_value - right_value + empty
        matrix.loc[left, right] = interaction
        matrix.loc[right, left] = interaction
    return matrix


def _normalize_players(players: Iterable[Any]) -> list[Any]:
    ordered = list(players)
    if len(ordered) != len(set(ordered)):
        raise ValueError("players must be unique.")
    return ordered


def _normalize_coalition_values(coalition_values: CoalitionValues) -> dict[Coalition, float]:
    items = coalition_values.items() if isinstance(coalition_values, Mapping) else coalition_values
    values: dict[Coalition, float] = {}
    for coalition, value in items:
        key = _coalition_key(coalition)
        values[key] = float(value)
    return values


def _coalition_key(coalition: Any) -> Coalition:
    if coalition is None:
        return frozenset()
    if isinstance(coalition, frozenset):
        return coalition
    if isinstance(coalition, str):
        return frozenset([coalition])
    try:
        return frozenset(coalition)
    except TypeError:
        return frozenset([coalition])


def _coalition_value(
    values: Mapping[Coalition, float],
    coalition: Coalition,
    ordered_players: list[Any],
    empty_value: float,
) -> float:
    if not coalition:
        return float(values.get(frozenset(), empty_value))
    if coalition in values:
        return values[coalition]
    raise ValueError(f"Missing coalition value for {_coalition_label(coalition, ordered_players)}.")


def _coalition_label(coalition: Coalition, ordered_players: list[Any]) -> tuple[Any, ...]:
    return tuple(player for player in ordered_players if player in coalition)


def _make_rng(random_state: int | np.random.Generator | None) -> np.random.Generator:
    if isinstance(random_state, np.random.Generator):
        return random_state
    return np.random.default_rng(random_state)


def _shapley_frame(
    ordered_players: list[Any],
    shapley: Mapping[Any, float],
    *,
    std: Mapping[Any, float],
    n_permutations: int,
    value_name: str,
    total_value: float,
) -> pd.DataFrame:
    rows = [
        {
            "player_name": str(player),
            "value": float(shapley[player]),
            "shapley_value": float(shapley[player]),
            "shapley_std": float(std[player]),
            "n_permutations": int(n_permutations),
            "value_name": value_name,
            "total_value": float(total_value),
        }
        for player in ordered_players
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "player_name",
            "value",
            "shapley_value",
            "shapley_std",
            "n_permutations",
            "value_name",
            "total_value",
        ],
    )


__all__ = [
    "exact_shapley_values",
    "grouped_players",
    "monte_carlo_shapley_values",
    "pairwise_interaction_matrix",
]
