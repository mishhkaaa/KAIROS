import pytest
from kairos_contracts.wiring import Settings


@pytest.fixture(autouse=True, scope="session")
def _dotenv_loaded():
    """Load .env once, before the first knowledge test. Most tests here build Settings.from_env(dotenv=None), which reads
    only the environment; without this they reached Postgres only if an earlier test (the CLI's) had happened to load
    .env, so a file run on its own (test_contract.py: all 14 contract tests) skipped. The environment still wins."""
    Settings.from_env()
