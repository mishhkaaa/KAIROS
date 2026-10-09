"""A "*" network allowlist means the public internet only: never this machine, private networks or Docker's."""
from kairos_execution.tools.base import network_allowed


def test_star_allows_public_hosts_only():
    allow = {"network_allow": ["*"]}
    for url in ("http://localhost:8089/tasks", "http://127.0.0.1/", "http://192.168.1.5/", "http://10.0.0.1/",
                "http://host.docker.internal:8089", "http://vendor-docs/sdk-v5.html", "http://[::1]/"):
        assert not network_allowed(url, allow), url


def test_named_allowlists_are_unchanged():
    assert network_allowed("http://vendor-docs/sdk-v5.html", {"network_allow": ["vendor-docs:80"]})
    assert not network_allowed("https://example.com/", {"network_allow": ["vendor-docs:80"]})
