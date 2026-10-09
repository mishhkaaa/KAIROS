"""GET /system/config on the real gateway: contract suite, redaction with a canary secret, and content checks."""
import pytest
from fastapi.testclient import TestClient
from kairos_contracts.testing.contracts import SystemConfigContract
from kairos_kernel.gateway.app import create_app
from kairos_kernel.testing import done, manifest

CANARY = "hunter2-canary-9f3"


@pytest.fixture
def cfg(make_kernel):
    async def planner(goal, ctx):
        return done(ctx, "ok")

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent", tools=["jira.write"])])
    k.settings.database_url = f"postgresql+psycopg://kairos:{CANARY}@db:5432/kairos"
    k.settings.redis_url = f"redis://:{CANARY}@127.0.0.1:6379/0"
    with TestClient(create_app(k)) as c:
        r = c.get("/system/config")
        assert r.status_code == 200, r.text
        return r


class TestKernelSystemConfig(SystemConfigContract):
    @pytest.fixture(autouse=True)
    def _cfg(self, cfg):
        self._json = cfg.json()

    def config(self):
        return self._json


def test_canary_secret_never_appears(cfg):
    assert CANARY not in cfg.text
    urls = {e["name"]: e["url"] for e in cfg.json()["endpoints"]}
    assert urls["database"] == "postgresql+psycopg://kairos:***@db:5432/kairos"
    assert urls["redis"] == "redis://***@127.0.0.1:6379/0"


def test_content(cfg):
    body = cfg.json()
    assert body["stack"][0]["component"] == "kernel"
    assert {c["component"] for c in body["stack"]} >= {"models", "knowledge", "tools", "sandbox"}
    assert [a["name"] for a in body["agents"]] == ["planner-agent"]
    assert {r["task_class"] for r in body["models"]["routes"]} >= {"default", "embedding"}
    assert any("jira.write" in p["requires_approval"] for p in body["policies"])
    assert body["firewall"]["regex"] is True
    assert body["paths"]["policies_dir"]
