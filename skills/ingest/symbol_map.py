"""Symbol format conversion between QuantSpace and panda_data.

QuantSpace uses ``<EXCHANGE>.<CODE>`` (e.g. ``SHSE.510300``, ``SHFE.RB99``).
panda_data uses ``<CODE>.<EXCHANGE>`` (e.g. ``510300.SH``, ``RB_DOMINANT.SHF``).

Conversion is bidirectional and covers the exchanges defined in
``AGENTS.md`` plus panda_data's HK and US (NASDAQ basic) suffixes.

For Chinese futures, the dominant continuous contract convention also
differs: QuantSpace ``<EX>.<PRODUCT>99`` maps to panda_data
``<PRODUCT>_DOMINANT.<EX>``. Non-dominant contracts (e.g. ``RB2501``)
round-trip unchanged.
"""

from __future__ import annotations

# QuantSpace exchange prefix  <->  panda_data exchange suffix
_QS_TO_PD: dict[str, str] = {
    "SHSE": "SH",
    "SZSE": "SZ",
    "SHFE": "SHF",
    "DCE": "DCE",
    "CZCE": "CZC",
    "CFFEX": "CFE",
    "INE": "INE",
    "GFEX": "GFE",
    "HKEX": "HK",
    "NASDAQ": "NB",
}
_PD_TO_QS: dict[str, str] = {v: k for k, v in _QS_TO_PD.items()}

_DOMINANT_TAG = "_DOMINANT"
_DOMINANT_SUFFIX = "99"


def to_panda_data_symbol(qs_symbol: str) -> str:
    """Convert a QuantSpace symbol to panda_data native format.

    Parameters
    ----------
    qs_symbol : str
        QuantSpace symbol, e.g. ``"SHSE.510300"`` or ``"SHFE.RB99"``.

    Returns
    -------
    str
        panda_data symbol, e.g. ``"510300.SH"`` or ``"RB_DOMINANT.SHF"``.

    Raises
    ------
    ValueError
        If the exchange prefix is not recognised.
    """
    if "." not in qs_symbol:
        raise ValueError(f"Not a QuantSpace symbol (missing '.'): {qs_symbol!r}")
    prefix, code = qs_symbol.split(".", 1)
    if prefix not in _QS_TO_PD:
        raise ValueError(
            f"Unknown QuantSpace exchange prefix {prefix!r} in {qs_symbol!r}; "
            f"known prefixes: {sorted(_QS_TO_PD)}"
        )
    pd_suffix = _QS_TO_PD[prefix]

    # Chinese futures dominant contract: RB99 -> RB_DOMINANT
    if prefix in {"SHFE", "DCE", "CZCE", "CFFEX", "INE", "GFEX"} and code.endswith(
        _DOMINANT_SUFFIX
    ):
        product = code[: -len(_DOMINANT_SUFFIX)]
        if product:  # guard against a bare "99"
            code = f"{product}{_DOMINANT_TAG}"

    return f"{code}.{pd_suffix}"


def to_quantspace_symbol(pd_symbol: str) -> str:
    """Convert a panda_data symbol to QuantSpace internal format.

    Parameters
    ----------
    pd_symbol : str
        panda_data symbol, e.g. ``"510300.SH"`` or ``"RB_DOMINANT.SHF"``.

    Returns
    -------
    str
        QuantSpace symbol, e.g. ``"SHSE.510300"`` or ``"SHFE.RB99"``.

    Raises
    ------
    ValueError
        If the exchange suffix is not recognised.
    """
    if "." not in pd_symbol:
        raise ValueError(f"Not a panda_data symbol (missing '.'): {pd_symbol!r}")
    code, suffix = pd_symbol.rsplit(".", 1)
    if suffix not in _PD_TO_QS:
        raise ValueError(
            f"Unknown panda_data exchange suffix {suffix!r} in {pd_symbol!r}; "
            f"known suffixes: {sorted(_PD_TO_QS)}"
        )
    qs_prefix = _PD_TO_QS[suffix]

    # Chinese futures dominant contract: RB_DOMINANT -> RB99
    if qs_prefix in {"SHFE", "DCE", "CZCE", "CFFEX", "INE", "GFEX"} and code.endswith(
        _DOMINANT_TAG
    ):
        product = code[: -len(_DOMINANT_TAG)]
        if product:
            code = f"{product}{_DOMINANT_SUFFIX}"

    return f"{qs_prefix}.{code}"


def try_to_panda_data_symbol(symbol: str) -> str:
    """Best-effort conversion: return panda_data form, pass through on failure.

    Useful when callers may mix QuantSpace and native panda_data symbols.
    """
    try:
        return to_panda_data_symbol(symbol)
    except ValueError:
        return symbol


def try_to_quantspace_symbol(symbol: str) -> str:
    """Best-effort conversion: return QuantSpace form, pass through on failure."""
    try:
        return to_quantspace_symbol(symbol)
    except ValueError:
        return symbol
