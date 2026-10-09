"""Settings.from_env: KAIROS_<FIELD> parsing for fields that aren't plain strings."""

from kairos_contracts.wiring import Settings


def test_knowledge_watch_defaults_off(monkeypatch):
    monkeypatch.delenv("KAIROS_KNOWLEDGE_WATCH", raising=False)
    assert Settings.from_env(dotenv=None).knowledge_watch is False


def test_knowledge_watch_from_env(monkeypatch):
    monkeypatch.setenv("KAIROS_KNOWLEDGE_WATCH", "true")
    assert Settings.from_env(dotenv=None).knowledge_watch is True
    monkeypatch.setenv("KAIROS_KNOWLEDGE_WATCH", "false")
    assert Settings.from_env(dotenv=None).knowledge_watch is False


def test_firewall_llm_from_env(monkeypatch):
    monkeypatch.delenv("KAIROS_FIREWALL_LLM", raising=False)
    assert Settings.from_env(dotenv=None).firewall_llm is False
    monkeypatch.setenv("KAIROS_FIREWALL_LLM", "true")
    assert Settings.from_env(dotenv=None).firewall_llm is True


def test_redis_default_is_ipv4_loopback(monkeypatch):
    # "localhost" resolves to ::1 first on Windows, and the Redis client times out instead of falling back
    monkeypatch.delenv("KAIROS_REDIS_URL", raising=False)
    assert Settings.from_env(dotenv=None).redis_url.startswith("redis://127.0.0.1:")
