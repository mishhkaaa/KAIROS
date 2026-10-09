"""Contract test for P4's BrowserDriver. Needs Docker + the kairos/sandbox-browser image. SKIPs until implemented.

It starts the browser container directly (no dependency on P1's SandboxManager), so P4 can test alone:
    docker build -t kairos/sandbox-browser:latest execution/images/sandbox-browser
The container runs with the same hardening flags as P1's DockerSandboxManager, so the image is proven under them.
"""
import importlib.metadata
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from kairos_contracts.schema import SandboxInfo, SandboxSpec, SandboxStatus
from kairos_contracts.testing import contracts as c
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_execution.browser import factory

DOCKERFILE = Path(__file__).resolve().parents[1] / "images" / "sandbox-browser" / "Dockerfile"
HARDENED = ["--read-only", "--tmpfs", "/tmp", "--user", "10001", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--init"]
needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")


def test_image_version_matches_client():
    """A Playwright client/server version mismatch breaks connect(): the image tag must follow uv.lock."""
    pinned = re.search(r"^ARG PW_VERSION=([\d.]+)$", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert pinned, "Dockerfile must declare ARG PW_VERSION=<x.y.z>"
    assert pinned.group(1) == importlib.metadata.version("playwright")


@pytest.fixture(scope="module")
def driver():
    s = Settings()
    try:
        return factory.build_browser_driver(s, ServiceBundle(settings=s))
    except NotImplementedError as e:
        pytest.skip(f"not implemented yet: {e}")


@pytest.fixture(scope="module")
def browser_sandbox(driver):
    name = "kairos-browser-contract-test"
    if subprocess.run(["docker", "image", "inspect", "kairos/sandbox-browser:latest"], capture_output=True).returncode != 0:
        pytest.skip("image kairos/sandbox-browser:latest not built")
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    started = subprocess.run(["docker", "run", "-d", "--rm", "--name", name, *HARDENED, "-p", "3999:3000",
                              "kairos/sandbox-browser:latest"], capture_output=True, text=True)
    if started.returncode != 0:
        pytest.skip(f"cannot start kairos/sandbox-browser: {started.stderr.strip()[:200]}")
    time.sleep(3)
    yield SandboxInfo(sandbox_id="SB-test", status=SandboxStatus.RUNNING, spec=SandboxSpec(task_id="T-test", display=True),
                      endpoints={"playwright": "ws://127.0.0.1:3999/"})
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@needs_docker
class TestBrowser(c.BrowserDriverContract):
    @pytest.fixture(autouse=True)
    def _setup(self, driver, browser_sandbox):
        self.driver, self.sandbox = driver, browser_sandbox

    def make(self):
        return self.driver, self.sandbox, "https://example.com"
