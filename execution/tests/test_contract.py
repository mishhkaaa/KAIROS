"""Contract tests for P1 (execution side). The sandbox suite needs a running Docker daemon + kairos/sandbox-base image."""
import tempfile
from pathlib import Path

import pytest
from kairos_contracts.testing import contracts as c
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_execution import factory


def _settings() -> Settings:
    # jira_url="inprocess": the mock Jira runs inside the test process (no docker compose needed)
    return Settings(data_dir=Path(tempfile.mkdtemp(prefix="kairos-exec-")), jira_url="inprocess")


def _build(fn):
    s = _settings()
    try:
        return fn(s, ServiceBundle(settings=s))
    except NotImplementedError as e:
        pytest.skip(f"not implemented yet: {e}")


def _docker_ready() -> str | None:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.images.get("kairos/sandbox-base:latest")
    except Exception as e:  # daemon down, image missing, SDK missing
        return str(e)[:120]
    return None


class TestArtifacts(c.ArtifactStoreContract):
    def make(self):
        return _build(factory.build_artifact_store)


class TestSandbox(c.SandboxManagerContract):
    def make(self):
        reason = _docker_ready()
        if reason:
            pytest.skip(f"docker sandbox unavailable: {reason}")
        return _build(factory.build_sandbox_manager)


class TestTools(c.ToolExecutorContract):
    def make(self):
        return _build(factory.build_tool_executor)
