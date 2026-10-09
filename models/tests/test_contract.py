"""Contract tests for the real router. Needs a running Ollama with the embedding model and at least one chat model pulled
(skips otherwise) and an implemented factory."""
import httpx
import pytest
import yaml
from kairos_contracts.testing import contracts as c
from kairos_contracts.wiring import REPO_ROOT, ServiceBundle, Settings
from kairos_models import factory


def _missing_models(ollama_url: str) -> str | None:
    """Why the suite can't run on this Ollama, or None. Ollama installed for something else must not turn the suite red."""
    try:
        tags = httpx.get(f"{ollama_url}/api/tags", timeout=2).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return "ollama not reachable"
    pulled = {m["name"] for m in tags} | {m["name"].split(":")[0] for m in tags}
    embed = yaml.safe_load((REPO_ROOT / "models" / "models.yaml").read_text(encoding="utf-8"))["embedding"]
    if embed not in pulled and embed.split(":")[0] not in pulled:
        return f"embedding model {embed} not pulled (ollama pull {embed})"
    if not any("embed" not in m["name"] for m in tags):
        return "no chat model pulled (ollama pull llama3.2:3b, or the models in models/models.yaml)"
    return None


def _build(fn):
    s = Settings.from_env()
    if reason := _missing_models(s.ollama_url):
        pytest.skip(reason)
    try:
        return fn(s, ServiceBundle(settings=s))
    except NotImplementedError as e:
        pytest.skip(f"not implemented yet: {e}")


class TestRouter(c.ModelRouterContract):
    def make(self):
        return _build(factory.build_model_router)


@pytest.mark.parametrize("names,reason", [
    ([], "embedding model"),
    (["nomic-embed-text:latest"], "no chat model"),
    (["llama3.2:3b"], "embedding model"),
    (["llama3.2:3b", "nomic-embed-text:latest"], None),
])
def test_suite_skips_when_models_are_missing(monkeypatch, names, reason):
    class Tags:
        def json(self):
            return {"models": [{"name": n} for n in names]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: Tags())
    got = _missing_models("http://ollama")
    assert (got is None) if reason is None else (reason in got)
