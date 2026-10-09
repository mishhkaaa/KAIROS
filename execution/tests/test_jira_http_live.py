"""LIVE HTTP test: the ToolExecutor contract against a real mock-jira server.

Uses KAIROS_TEST_JIRA_URL if set; otherwise starts a throwaway `kairos/mock-jira` container (build it with
`docker build -t kairos/mock-jira:latest -f infra/compose/mock-jira.Dockerfile .`). Skipped when neither works.
"""
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest
from kairos_contracts.testing import contracts as c
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_execution import factory


def _up(url: str) -> bool:
    try:
        return httpx.get(f"{url}/rest/api/2/issue/APOLLO-12", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def jira_url():
    if os.getenv("KAIROS_TEST_JIRA_URL"):
        yield os.environ["KAIROS_TEST_JIRA_URL"]
        return
    name = f"kairos-jira-test-{uuid.uuid4().hex[:6]}"
    started = subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::8090",
                              "kairos/mock-jira:latest"], capture_output=True, text=True)
    if started.returncode != 0:
        pytest.skip(f"no mock-jira available: {started.stderr.strip()[:120]}")
    try:
        port = subprocess.run(["docker", "port", name, "8090/tcp"], capture_output=True, text=True).stdout.split(":")[-1].strip()
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while not _up(url):
            if time.monotonic() > deadline:
                pytest.skip("mock-jira container did not become ready")
            time.sleep(0.3)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


class TestToolsOverHttp(c.ToolExecutorContract):
    @pytest.fixture(autouse=True)
    def _url(self, jira_url):
        self.url = jira_url

    def make(self):
        httpx.post(f"{self.url}/_reset", timeout=5)
        s = Settings(data_dir=Path(tempfile.mkdtemp(prefix="kairos-http-")), jira_url=self.url)
        return factory.build_tool_executor(s, ServiceBundle(settings=s))
