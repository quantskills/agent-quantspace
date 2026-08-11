"""AI-mined factor candidates for the 18 global-asset ETF universe.

Output of the factor_mining skill Phase 05 multi-agent protocol. Each family
module exposes a ``CANDIDATES`` list of metadata dicts::

    {
        "factor_id": str,        # unique candidate id
        "family": str,           # generator family
        "hypothesis": str,       # economic rationale
        "direction": str,        # "positive" | "negative"
        "func_name": str,        # function defined in the same module
        "params": dict,          # JSON-serializable params passed to func
    }

Every factor function follows the ``skills.compute.wrappers.Factor`` contract:
single-symbol ``DataFrame`` (DatetimeIndex named ``eob``, OHLCV columns) ->
real-valued ``pd.Series`` with the same index, item-for-item.
"""
