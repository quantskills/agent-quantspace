from __future__ import annotations

from skills.factor_mining import (
    SCHEMA_VERSION,
    AnalyzePort,
    ArtifactStorePort,
    FactorExecutionPort,
    FactorSpec,
    ReportPort,
    ResearchBrief,
)


def test_factor_mining_public_exports_include_contracts_and_ports() -> None:
    import skills.factor_mining as fm

    assert SCHEMA_VERSION == "1.4.0"
    assert ResearchBrief is not None
    assert FactorSpec is not None
    assert FactorExecutionPort is not None
    assert AnalyzePort is not None
    assert ArtifactStorePort is not None
    assert ReportPort is not None
    assert fm.FactorExecutionAdapter is not None
    assert fm.DataManagerArtifactStore is not None
    assert fm.AnalyzeAdapter is not None
    assert "FactorExecutionAdapter" in fm.__all__
    assert "AnalyzeAdapter" in fm.__all__
    assert not hasattr(fm, "FactorComputeResult")
    assert "FactorComputeResult" not in fm.__all__


def test_analyze_public_exports_include_facade() -> None:
    import skills.analyze as analyze

    assert analyze.AnalyzeFacade is not None
    assert analyze.ENGINE_VERSION == "3.0.0"
    assert analyze.ANALYZE_SCHEMA_VERSION == "3.0.0"
    assert "AnalyzeFacade" in analyze.__all__
    assert "ProtocolSnapshot" in analyze.__all__
