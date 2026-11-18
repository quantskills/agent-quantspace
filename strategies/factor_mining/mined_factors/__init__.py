"""Candidate lists the workflow turns into ``FactorSpec`` objects.

``CANDIDATES`` is the default list. A candidate names its factor function by ``module``
and ``name``: a public indicator of ``skills.compute.indicators`` or a function in a
``strategies/<domain>/mined_factors/`` package. Either way the function follows the
``skills.compute.wrappers.Factor`` contract: one symbol's bars (index ``eob``) in, a
float Series on the same index out.
"""

from strategies.factor_mining.mined_factors.baseline import CANDIDATES

__all__ = ["CANDIDATES"]
