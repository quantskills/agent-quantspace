---
name: research
description: >
  Use when tasks need reusable research pipeline templates, factor screening,
  parameter sensitivity sweeps, or strategy comparison.
---

# Research Templates

## Components

| Function | Module | Description |
|----------|--------|-------------|
| `screen_all_indicators` | `factor_screening.py` | Batch-compute all indicators on a pool, run full_stat, return IC/IR ranking |
| `param_sweep` | `param_sensitivity.py` | Grid-sweep a factor parameter, return IC/IR vs parameter table |
| `compare_strategies` | `strategy_comparison.py` | Run multiple factor configs through ModularBacktester, compare Sharpe/MaxDD/Calmar |

## Usage

```python
from skills.research.factor_screening import screen_all_indicators
from skills.research.param_sensitivity import param_sweep
from skills.research.strategy_comparison import compare_strategies
```
