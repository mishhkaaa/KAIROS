"""DockerSandboxManager: hardened, disposable task containers (blueprint §30).

Defaults: non-root, read-only root fs (+ /tmp tmpfs), all capabilities dropped, no-new-privileges,
CPU/memory/pids limits, network=none unless allowlisted, only the task workspace mounted, forced timeout.
Browser sandboxes (spec.display) run P4's kairos/sandbox-browser image and expose Playwright on :3000.

Endpoint mode (KAIROS_SANDBOX_ENDPOINT): "ip" (Linux appliance: kairosd reaches the container's IP on the internal
network) or "port" (Docker Desktop on Windows/macOS, where the host can't reach container IPs). Either way a sandbox
never has internet:
- display=False: network=none -> network_mode "none"; allowlist -> internal kairos_sandbox only.
- display=True: internal kairos_sandbox only. In port mode a relay container (the sandbox-base image running a small
  TCP forwarder) sits on the default bridge AND kairos_sandbox, publishes 127.0.0.1:<port> and forwards it to the
  browser's Playwright server, and nothing else. An internal network can't publish ports, which is why the relay
  exists; the browser itself stays internal, so page subresources can't reach the internet either.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    ExecRequest,
    ExecResult,
    NetworkMode,
    SandboxInfo,
    SandboxSpec,
    SandboxStatus,
)
from kairos_contracts.schema.common import new_id

log = logging.getLogger("kairos.execution.sandbox")

LABEL = "kairos.sandbox"
BROWSER_IMAGE = os.getenv("KAIROS_BROWSER_IMAGE", "kairos/sandbox-browser:latest")
SANDBOX_NETWORK = os.getenv("KAIROS_SANDBOX_NETWORK", "kairos_sandbox")
# Browser sandboxes allowed the public internet ("*") join this network instead: a plain bridge with a route out,
# and none to kairos_sandbox (other sandboxes, the internal vendor site).
WEB_NETWORK = os.getenv("KAIROS_WEB_NETWORK", "kairos_web")
RELAY_IMAGE = os.getenv("KAIROS_SANDBOX_RELAY_IMAGE", "kairos/sandbox-base:latest")
PLAYWRIGHT_PORT = 3000

# Runs in the relay container: forward every connection on :3000 to <browser>:3000, byte for byte (WebSockets included).
RELAY_SOURCE = """
import asyncio, sys
target, port = sys.argv[1], int(sys.argv[2])
async def pipe(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    finally:
        w.close()
async def handle(r, w):
    try:
        tr, tw = await asyncio.open_connection(target, port)
    except OSError:
        w.close()
        return
    await asyncio.gather(pipe(r, tw), pipe(tr, w), return_exceptions=True)
async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()
asyncio.run(main())
"""


def default_endpoint_mode() -> str:
    return os.getenv("KAIROS_SANDBOX_ENDPOINT", "ip" if platform.system() == "Linux" else "port")


class DockerSandboxManager:
    def __init__(self, workspaces_root: Path, client: Any = None, endpoint_mode: str | None = None) -> None:
        self.workspaces_root = Path(workspaces_root)
        self._client = client
        self.endpoint_mode = endpoint_mode or default_endpoint_mode()
        self.sandboxes: dict[str, SandboxInfo] = {}
        self._containers: dict[str, Any] = {}
        self._relays: dict[str, Any] = {}
        self._deadlines: dict[str, float] = {}
        self._reaper: asyncio.Task | None = None
        self._cleaned = False

    # ------------------------------------------------------------------ docker plumbing
    def client(self) -> Any:
        if self._client is None:
            try:
                import docker

                self._client = docker.from_env()
                self._client.ping()
            except Exception as e:
                self._client = None
                raise KairosError("SANDBOX_FAILED", f"docker is not available: {e}") from e
        return self._client

    def _cleanup_stale(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        for c in self.client().containers.list(all=True, filters={"label": LABEL}):
            if c.labels.get(LABEL) not in self.sandboxes:
                log.info("removing stale sandbox container %s", c.name)
                c.remove(force=True)

    def _ensure_network(self, name: str = SANDBOX_NETWORK) -> str:
        nets = self.client().networks.list(names=[name])
        if not nets:
            self.client().networks.create(name, driver="bridge", internal=name != WEB_NETWORK, labels={LABEL: "network"})
        return name

    def run_kwargs(self, sandbox_id: str, spec: SandboxSpec, workspace: Path) -> dict[str, Any]:
        """Pure function of the spec — unit-tested without Docker."""
        kw: dict[str, Any] = {
            "image": BROWSER_IMAGE if spec.display else spec.image,
            "name": f"kairos-{sandbox_id.lower()}",
            "detach": True,
            "labels": {LABEL: sandbox_id, "kairos.task": spec.task_id, "kairos.pid": str(spec.pid or "")},
            "mem_limit": f"{spec.memory_mb}m",
            "nano_cpus": int(spec.cpu * 1e9),
            "pids_limit": 256,
            "security_opt": ["no-new-privileges"],
            "environment": dict(spec.env),
            "volumes": {str(workspace.resolve()): {"bind": "/workspace", "mode": "rw"}},
        }
        for m in spec.mounts:
            kw["volumes"][m.source] = {"bind": m.target, "mode": "ro" if m.read_only else "rw"}
        if spec.display:
            kw["shm_size"] = "1g"  # Chromium needs it; the browser image runs as its own non-root user
        else:
            kw.update(read_only=True, tmpfs={"/tmp": "rw,size=64m"}, cap_drop=["ALL"], user="10001", working_dir="/workspace")
        if spec.gpu:
            from docker.types import DeviceRequest

            kw["device_requests"] = [DeviceRequest(count=-1, capabilities=[["gpu"]])]
        if spec.network == NetworkMode.NONE and not spec.display:
            kw["network_mode"] = "none"
        elif spec.display and "*" in spec.network_allow:
            kw["network"] = WEB_NETWORK  # the public web; the kernel checks every URL is a public host
        else:
            kw["network"] = SANDBOX_NETWORK  # internal: no route to the internet, in either endpoint mode
        return kw

    def relay_kwargs(self, sandbox_id: str, target: str) -> dict[str, Any]:
        """The port-mode relay for a browser sandbox: publishes 127.0.0.1:<random> and forwards it to target:3000."""
        return {
            "image": RELAY_IMAGE,
            "name": f"kairos-{sandbox_id.lower()}-relay",
            "detach": True,
            "command": ["python3", "-c", RELAY_SOURCE, target, str(PLAYWRIGHT_PORT)],
            "labels": {LABEL: sandbox_id, "kairos.role": "relay"},
            "ports": {f"{PLAYWRIGHT_PORT}/tcp": ("127.0.0.1", None)},
            "mem_limit": "64m",
            "nano_cpus": 250_000_000,
            "pids_limit": 64,
            "read_only": True,
            "cap_drop": ["ALL"],
            "user": "10001",
            "security_opt": ["no-new-privileges"],
        }

    # ------------------------------------------------------------------ SandboxManager
    async def provision(self, spec: SandboxSpec) -> SandboxInfo:
        sandbox_id = new_id("SB")
        workspace = self.workspaces_root / spec.task_id
        workspace.mkdir(parents=True, exist_ok=True)
        # The sandbox runs as uid 10001. On a Linux host a bind mount keeps the host's ownership, so the task's own
        # workspace must be writable by that user (Docker Desktop on Windows and macOS does not enforce this).
        if os.name == "posix" and workspace.stat().st_uid != 10001:
            os.chmod(workspace, 0o777)

        def start() -> Any:
            self._cleanup_stale()
            kw = self.run_kwargs(sandbox_id, spec, workspace)
            if "network" in kw:
                self._ensure_network(kw["network"])
            container = self.client().containers.run(**kw)
            container.reload()
            relay = None
            if spec.display and self.endpoint_mode == "port":
                # The relay starts on the default bridge (to publish its port) and joins the sandbox network to reach
                # the browser by name; the browser never touches the bridge.
                relay = self.client().containers.run(**self.relay_kwargs(sandbox_id, kw["name"]))
                self.client().networks.get(self._ensure_network(kw["network"])).connect(relay)
                relay.reload()
            return container, relay

        try:
            container, relay = await asyncio.to_thread(start)
        except KairosError:
            raise
        except Exception as e:
            raise KairosError("SANDBOX_FAILED", f"could not start sandbox: {e}") from e
        if relay is not None:
            self._relays[sandbox_id] = relay
        endpoints = self._endpoints(relay or container) if spec.display else {}
        info = SandboxInfo(sandbox_id=sandbox_id, status=SandboxStatus.RUNNING, spec=spec, endpoints=endpoints)
        self.sandboxes[sandbox_id], self._containers[sandbox_id] = info, container
        self._deadlines[sandbox_id] = time.monotonic() + spec.timeout_s
        self._start_reaper()
        if spec.display:
            await self._wait_for_port(endpoints.get("playwright", ""))
        return info

    def _endpoints(self, container: Any) -> dict[str, str]:
        attrs = container.attrs.get("NetworkSettings", {})
        if self.endpoint_mode == "port":
            binding = (attrs.get("Ports") or {}).get(f"{PLAYWRIGHT_PORT}/tcp") or []
            if binding:
                return {"playwright": f"ws://127.0.0.1:{binding[0]['HostPort']}/"}
        ip = ((attrs.get("Networks") or {}).get(SANDBOX_NETWORK) or {}).get("IPAddress")
        return {"playwright": f"ws://{ip}:{PLAYWRIGHT_PORT}/"} if ip else {}

    async def _wait_for_port(self, url: str, timeout: float = 30.0) -> None:
        """Ready = the server inside answers HTTP. (Docker's port proxy accepts TCP before the server listens.)"""
        if not url:
            return
        host, port = url.removeprefix("ws://").rstrip("/").rsplit(":", 1)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), 1)
                writer.write(b"GET / HTTP/1.1\r\nHost: sandbox\r\nConnection: close\r\n\r\n")
                await writer.drain()
                if await asyncio.wait_for(reader.read(1), 1):
                    return
            except (OSError, TimeoutError):
                pass
            finally:
                if writer is not None:  # always release the socket, including on timeouts
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
            await asyncio.sleep(0.3)
        raise KairosError("SANDBOX_FAILED", f"browser endpoint {url} not ready after {timeout}s")

    def _get(self, sandbox_id: str) -> Any:
        if sandbox_id not in self._containers:
            raise KairosError("NOT_FOUND", f"sandbox {sandbox_id}")
        return self._containers[sandbox_id]

    async def exec(self, sandbox_id: str, request: ExecRequest) -> ExecResult:
        container = self._get(sandbox_id)
        t0 = time.monotonic()

        def run() -> Any:
            return container.exec_run(request.command, workdir=request.workdir, demux=True)

        try:
            res = await asyncio.wait_for(asyncio.to_thread(run), request.timeout_s)
        except TimeoutError as e:
            raise KairosError("TIMEOUT", f"command exceeded {request.timeout_s}s") from e
        out, errb = res.output if isinstance(res.output, tuple) else (res.output, b"")
        return ExecResult(exit_code=res.exit_code, stdout=(out or b"").decode(errors="replace")[-100_000:],
                          stderr=(errb or b"").decode(errors="replace")[-100_000:], duration_s=time.monotonic() - t0)

    async def screenshot(self, sandbox_id: str) -> bytes | None:
        self._get(sandbox_id)
        return None  # browser screenshots come from the BrowserDriver (P4)

    async def destroy(self, sandbox_id: str) -> None:
        container = self._containers.pop(sandbox_id, None)
        self._deadlines.pop(sandbox_id, None)
        for c in (self._relays.pop(sandbox_id, None), container):
            if c is None:
                continue
            try:
                await asyncio.to_thread(c.remove, force=True)
            except Exception:
                log.exception("removing container %s for %s failed", getattr(c, "name", "?"), sandbox_id)
        if sandbox_id in self.sandboxes:
            self.sandboxes[sandbox_id] = self.sandboxes[sandbox_id].model_copy(update={"status": SandboxStatus.DESTROYED})

    async def list(self, task_id: str | None = None) -> list[SandboxInfo]:
        return [s for s in self.sandboxes.values() if task_id is None or s.spec.task_id == task_id]

    # ------------------------------------------------------------------ timeouts
    def _start_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.get_running_loop().create_task(self._reap())

    async def _reap(self) -> None:
        while self._deadlines:
            now = time.monotonic()
            for sandbox_id, deadline in list(self._deadlines.items()):
                if now > deadline:
                    log.warning("sandbox %s hit its timeout; destroying", sandbox_id)
                    await self.destroy(sandbox_id)
            await asyncio.sleep(1)
