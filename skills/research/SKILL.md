---
name: research
description: >
  Use when tasks need reusable research pipeline templates, factor screening,
  or parameter sensitivity sweeps.
---

# Research Templates

## Components

| Function | Module | Description |
|----------|--------|-------------|
| `screen_all_indicators` | `factor_screening.py` | Batch-compute indicators on an explicit panel and return IC/IR ranking |
| `param_sweep` | `param_sensitivity.py` | Grid-sweep one factor parameter on an explicit panel |

## Usage

```python
from skills.research.factor_screening import screen_all_indicators
from skills.research.param_sensitivity import param_sweep
```
