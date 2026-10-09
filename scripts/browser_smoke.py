"""Production-like browser check (P4). Starts kairos/sandbox-browser with P1's sandbox flags, drives it with the
real PlaywrightDriver, opens the offline vendor site and saves a screenshot. Proves: vendor-docs DNS from inside
the sandbox, run-server under read-only/uid 10001, screenshots.

Linux (the RTX node): on the internal kairos_sandbox network only, reached at the container IP (P1's "ip" mode).
Windows/macOS (Docker Desktop): container IPs aren't routable from the host, so like P1's "port" mode it publishes
:3000 on 127.0.0.1 from the default bridge and also joins kairos_sandbox (this dev mode has internet egress).

    docker compose -f infra/compose/docker-compose.yml up -d vendor-docs
    uv run python scripts/browser_smoke.py            # -> .data/smoke/vendor.png
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from kairos_contracts.schema import SandboxInfo, SandboxSpec, SandboxStatus
from kairos_execution.browser.driver import PlaywrightDriver

ROOT = Path(__file__).resolve().parents[1]
NAME = "kairos-browser-smoke"
NETWORK = "kairos_sandbox"
URL = "http://vendor-docs/sdk-v5.html"
EXPECT = "2026-10-20"
FLAGS = ["--read-only", "--tmpfs", "/tmp", "--user", "10001", "--cap-drop", "ALL",
         "--security-opt", "no-new-privileges", "--init"]
PORT_MODE = sys.platform != "linux"


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


async def drive(endpoint: str) -> bytes:
    sb = SandboxInfo(sandbox_id="SB-smoke", status=SandboxStatus.RUNNING, spec=SandboxSpec(task_id="T-smoke", display=True),
                     endpoints={"playwright": endpoint})
    drv = PlaywrightDriver()
    try:
        for attempt in range(30):  # run-server needs a few seconds to listen
            try:
                page = await drv.open(sb, URL)
                break
            except Exception:
                if attempt == 29:
                    raise
                await drv.close(sb)
                await asyncio.sleep(1)
        print(f"title: {page.title!r}\nlinks: {page.links}")
        if EXPECT not in page.text:
            raise SystemExit(f"FAIL: {EXPECT} not on the page:\n{page.text[:500]}")
        return await drv.screenshot(sb)
    finally:
        await drv.close(sb)


def main() -> None:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    net = ["-p", "127.0.0.1::3000"] if PORT_MODE else ["--network", NETWORK]
    docker("run", "-d", "--rm", "--name", NAME, *FLAGS, *net, "kairos/sandbox-browser:latest")
    try:
        if PORT_MODE:
            docker("network", "connect", NETWORK, NAME)
            endpoint = f"ws://127.0.0.1:{docker('port', NAME, '3000/tcp').splitlines()[0].rsplit(':', 1)[1]}/"
        else:
            nets = json.loads(docker("inspect", "-f", "{{json .NetworkSettings.Networks}}", NAME))
            endpoint = f"ws://{nets[NETWORK]['IPAddress']}:3000/"
        print(f"{'port' if PORT_MODE else 'ip'} mode: {endpoint}")
        png = asyncio.run(drive(endpoint))
        out = ROOT / ".data" / "smoke" / "vendor.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        print(f"OK: screenshot {out} ({len(png)} bytes)")
    finally:
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


if __name__ == "__main__":
    main()
