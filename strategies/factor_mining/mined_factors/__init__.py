"""Generated factor functions and their CANDIDATES metadata.

Each function follows the ``skills.compute.wrappers.Factor`` contract: one symbol's
bars (index ``eob``) in, a float Series on the same index out. ``CANDIDATES`` is the
list the workflow turns into ``FactorSpec`` objects.
"""

from strategies.factor_mining.mined_factors.trend_momentum import CANDIDATES as TREND_CANDIDATES
from strategies.factor_mining.mined_factors.trend_momentum import roc_close

CANDIDATES = tuple(TREND_CANDIDATES)

__all__ = ["CANDIDATES", "roc_close"]
