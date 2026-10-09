"""Contract tests for P4's converters. Each converter must convert its sample in tests/samples/. SKIP until implemented."""
from pathlib import Path

import pytest
from kairos_contracts.testing import contracts as c
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_knowledge.ingestion import factory

SAMPLES = Path(__file__).parent / "samples"
# converter.name -> sample file/dir. Add a row for every converter you ship.
SAMPLE_FOR = {
    "markdown": SAMPLES / "markdown",
    "jira-json": SAMPLES / "jira-export.json",
    "slack-export": SAMPLES / "slack-export",
    "csv": SAMPLES / "budget.csv",
    "document": SAMPLES / "steering-notes.docx",  # skips unless the `ingest` extra (markitdown) is installed
}


def _converters():
    s = Settings()
    try:
        return factory.build_converters(s, ServiceBundle(settings=s))
    except NotImplementedError as e:
        pytest.skip(f"not implemented yet: {e}")


@pytest.fixture(params=sorted(SAMPLE_FOR))
def converter_name(request):
    return request.param


class TestConverters(c.SourceConverterContract):
    @pytest.fixture(autouse=True)
    def _pick(self, converter_name):
        self.name = converter_name

    def make(self):
        conv = next((cv for cv in _converters() if cv.name == self.name), None)
        if conv is None:
            pytest.skip(f"converter {self.name!r} not shipped yet")
        return conv, str(SAMPLE_FOR[self.name])
