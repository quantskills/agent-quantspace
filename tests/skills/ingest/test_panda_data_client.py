"""Offline tests for PandaDataClient configuration handling."""

from __future__ import annotations

from skills.ingest import PandaDataClient


def test_client_ignores_pandaai_env_names(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.setenv("PANDAAI_USERNAME", "alias-user")
    monkeypatch.setenv("PANDAAI_PASSWORD", "alias-pass")
    monkeypatch.chdir(tmp_path)

    client = PandaDataClient()

    assert client._username == ""
    assert client._password == ""


def test_client_loads_panda_data_dotenv_from_current_working_directory(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.delenv("PANDAAI_USERNAME", raising=False)
    monkeypatch.delenv("PANDAAI_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PANDA_DATA_USERNAME=dotenv-user\nPANDA_DATA_PASSWORD=dotenv-pass\n",
        encoding="utf-8",
    )

    client = PandaDataClient()

    assert client._username == "dotenv-user"
    assert client._password == "dotenv-pass"
