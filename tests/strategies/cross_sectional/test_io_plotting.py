from __future__ import annotations

import pandas as pd
import pytest

from strategies.cross_sectional.io import load_price_data
from strategies.cross_sectional.plotting import plot_backtest_results, plot_weight_heatmap


def test_load_price_data_normalizes_symbol_eob_multiindex(tmp_path) -> None:
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "eob": ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"],
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.0, 2.0],
            "volume": [100, 200],
        }
    ).to_csv(csv_path, index=False)

    panel = load_price_data(str(csv_path))

    assert panel.index.names == ["symbol", "eob"]
    assert panel.index.get_level_values("eob").tz is None
    assert panel.loc[("AAA", panel.index.get_level_values("eob")[0]), "close"] == 1.0


def test_plotting_helpers_return_figures_and_validate_inputs(tmp_path) -> None:
    index = pd.date_range("2024-01-31", periods=3, freq="M")
    result_df = pd.DataFrame(
        {
            "cum_return": [1.0, 1.1, 1.05],
            "cum_raw_return": [1.0, 1.12, 1.08],
            "drawdown": [0.0, 0.0, -0.05],
            "cum_return_max": [1.0, 1.1, 1.1],
        },
        index=index,
    )
    figure_path = tmp_path / "chart.png"

    fig = plot_backtest_results(result_df, {"total_return": 0.05}, show_plot=False, save_path=str(figure_path))
    heatmap = plot_weight_heatmap(pd.DataFrame({"AAA": [1.0, 0.0, 1.0]}, index=index), show_plot=False)

    assert fig is not None
    assert heatmap is not None
    assert figure_path.exists()
    with pytest.raises(ValueError, match="non-empty"):
        plot_weight_heatmap(pd.DataFrame(), show_plot=False)
