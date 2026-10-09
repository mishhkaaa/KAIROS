"""GET /system/config on the mock gateway passes the contract suite; the redaction helpers catch what they must."""
from fastapi.testclient import TestClient
from kairos_contracts.api.mock_gateway import build_mock_app
from kairos_contracts.testing.contracts import SystemConfigContract, find_secret_leaks
from kairos_contracts.util import redact_url


class TestMockSystemConfig(SystemConfigContract):
    def config(self):
        with TestClient(build_mock_app()) as c:
            r = c.get("/system/config")
            assert r.status_code == 200
            return r.json()


def test_redact_url():
    assert redact_url("postgresql+psycopg://kairos:hunter2@db:5432/m") == "postgresql+psycopg://kairos:***@db:5432/m"
    assert redact_url("redis://:hunter2@h:6379/0") == "redis://***@h:6379/0"
    assert redact_url("http://h/x?token=abc&a=1") == "http://h/x?token=***&a=1"
    assert redact_url("http://localhost:11434") == "http://localhost:11434"


def test_find_secret_leaks():
    assert find_secret_leaks({"url": "postgresql://u:***@h/db", "max_tokens": 4000, "token": None}) == []
    assert find_secret_leaks({"db": {"url": "postgresql://u:hunter2@h/db"}}) == ["$.db.url"]
    assert find_secret_leaks({"client_secret": "abc"}) == ["$.client_secret"]
    assert find_secret_leaks(["https://x/?api_key=abc"]) == ["$[0]"]
