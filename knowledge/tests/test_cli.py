"""kairos-okf CLI. Needs Postgres for ingest/search."""

import shutil

import pytest
from kairos_contracts.testing.fakes import FIXTURE_OKF_DIR
from kairos_contracts.wiring import Settings
from kairos_knowledge import cli
from typer.testing import CliRunner

from .test_contract import _postgres_reachable
from .test_ingest import SAMPLES


def test_validate_fixtures_exits_zero(monkeypatch):
    monkeypatch.setenv("KAIROS_OKF_DIR", str(FIXTURE_OKF_DIR))
    result = CliRunner().invoke(cli.app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "13 files checked" in result.output and "ok=True" in result.output


def test_ingest_uses_a_converter(monkeypatch, tmp_path):
    s = Settings.from_env(dotenv=None)
    if not _postgres_reachable(s.database_url):
        pytest.skip(f"Postgres unreachable at {s.database_url}")
    okf = tmp_path / "okf"
    shutil.copytree(FIXTURE_OKF_DIR, okf)
    monkeypatch.setenv("KAIROS_OKF_DIR", str(okf))
    monkeypatch.delenv("KAIROS_MODE_CONVERTERS", raising=False)
    result = CliRunner().invoke(cli.app, ["ingest", str(SAMPLES), "--target", "/org/inbox"])
    assert result.exit_code == 0, result.output
    assert '"/org/inbox/vendor-contract"' in result.output and '"errors": []' in result.output
    assert (okf / "inbox" / "vendor-contract.md").exists()
