"""Offline tests for PandaDataClient configuration handling."""

from __future__ import annotations

from skills.ingest import PandaDataClient


def test_client_accepts_pandaai_env_aliases(monkeypatch) -> None:
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.setenv("PANDAAI_USERNAME", "alias-user")
    monkeypatch.setenv("PANDAAI_PASSWORD", "alias-pass")

    client = PandaDataClient()

    assert client._username == "alias-user"
    assert client._password == "alias-pass"


def test_client_loads_dotenv_from_current_working_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.delenv("PANDAAI_USERNAME", raising=False)
    monkeypatch.delenv("PANDAAI_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PANDAAI_USERNAME=dotenv-user\nPANDAAI_PASSWORD=dotenv-pass\n",
        encoding="utf-8",
    )

    client = PandaDataClient()

    assert client._username == "dotenv-user"
    assert client._password == "dotenv-pass"
