"""Offline tests for panda_data <-> QuantSpace symbol conversion."""

from __future__ import annotations

import pytest

from skills.ingest.symbol_map import (
    to_panda_data_symbol,
    to_quantspace_symbol,
    try_to_panda_data_symbol,
    try_to_quantspace_symbol,
)


class TestToPandaDataSymbol:
    @pytest.mark.parametrize(
        "qs,pd",
        [
            ("SHSE.510300", "510300.SH"),
            ("SHSE.600000", "600000.SH"),
            ("SHSE.000001", "000001.SH"),
            ("SZSE.000001", "000001.SZ"),
            ("SZSE.399001", "399001.SZ"),
            ("HKEX.0001", "0001.HK"),
            ("NASDAQ.AAPL", "AAPL.NB"),
            ("DCE.A2501", "A2501.DCE"),
            ("CFFEX.IF2501", "IF2501.CFE"),
            ("CZCE.AP2501", "AP2501.CZC"),
            ("INE.SC2501", "SC2501.INE"),
            ("GFEX.LC2501", "LC2501.GFE"),
        ],
    )
    def test_basic_mapping(self, qs, pd):
        assert to_panda_data_symbol(qs) == pd

    @pytest.mark.parametrize(
        "qs,pd",
        [
            ("SHFE.RB99", "RB_DOMINANT.SHF"),
            ("DCE.A99", "A_DOMINANT.DCE"),
            ("SHFE.ZN99", "ZN_DOMINANT.SHF"),
            ("CZCE.AP99", "AP_DOMINANT.CZC"),
        ],
    )
    def test_dominant_contract(self, qs, pd):
        assert to_panda_data_symbol(qs) == pd

    def test_non_dominant_contract_passthrough(self):
        assert to_panda_data_symbol("SHFE.RB2501") == "RB2501.SHF"

    def test_unknown_prefix_raises(self):
        with pytest.raises(ValueError, match="Unknown QuantSpace exchange prefix"):
            to_panda_data_symbol("XYZ.000001")

    def test_missing_dot_raises(self):
        with pytest.raises(ValueError, match="missing '.'"):
            to_panda_data_symbol("600000")


class TestToQuantSpaceSymbol:
    @pytest.mark.parametrize(
        "pd,qs",
        [
            ("510300.SH", "SHSE.510300"),
            ("000001.SZ", "SZSE.000001"),
            ("0001.HK", "HKEX.0001"),
            ("AAPL.NB", "NASDAQ.AAPL"),
            ("A2501.DCE", "DCE.A2501"),
            ("IF2501.CFE", "CFFEX.IF2501"),
            ("AP2501.CZC", "CZCE.AP2501"),
        ],
    )
    def test_basic_mapping(self, pd, qs):
        assert to_quantspace_symbol(pd) == qs

    @pytest.mark.parametrize(
        "pd,qs",
        [
            ("RB_DOMINANT.SHF", "SHFE.RB99"),
            ("A_DOMINANT.DCE", "DCE.A99"),
            ("ZN_DOMINANT.SHF", "SHFE.ZN99"),
        ],
    )
    def test_dominant_contract(self, pd, qs):
        assert to_quantspace_symbol(pd) == qs

    def test_unknown_suffix_raises(self):
        with pytest.raises(ValueError, match="Unknown panda_data exchange suffix"):
            to_quantspace_symbol("000001.XX")

    def test_missing_dot_raises(self):
        with pytest.raises(ValueError, match="missing '.'"):
            to_quantspace_symbol("AAPL")


class TestRoundTrip:
    @pytest.mark.parametrize(
        "qs",
        [
            "SHSE.510300",
            "SZSE.000001",
            "SHFE.RB99",
            "DCE.A2501",
            "HKEX.0001",
            "NASDAQ.AAPL",
            "CFFEX.IF99",
        ],
    )
    def test_qs_round_trip(self, qs):
        assert to_quantspace_symbol(to_panda_data_symbol(qs)) == qs


class TestBestEffortHelpers:
    def test_try_passthrough_on_failure(self):
        assert try_to_panda_data_symbol("unknown_format") == "unknown_format"
        assert try_to_quantspace_symbol("unknown_format") == "unknown_format"

    def test_try_converts_on_success(self):
        assert try_to_panda_data_symbol("SHSE.510300") == "510300.SH"
        assert try_to_quantspace_symbol("510300.SH") == "SHSE.510300"
