from __future__ import annotations

from strategies.cross_sectional.workflows import run_demo
from tests.fixtures.market_data import make_panel


def test_cross_sectional_workflow_uses_new_strategy_skill(monkeypatch, capsys) -> None:
    panel = make_panel(symbols=("AAA", "BBB"), periods=30)
    captured: dict = {}

    class FakeBacktester:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.metrics = {"sharpe_ratio": 1.25}

        def run(self) -> None:
            captured["ran"] = True

    monkeypatch.setattr(run_demo, "load_panel", lambda: panel)
    monkeypatch.setattr(run_demo, "ModularBacktester", FakeBacktester)

    run_demo.main()

    assert captured["data"] is panel
    assert captured["slippage_bp"] == 2.0
    assert captured["ran"] is True
    assert "sharpe_ratio: 1.25" in capsys.readouterr().out
