"""The KAIROS gateway client. Standard library only, so it installs anywhere Python does.

Where the gateway is, in order: the ``url`` argument, ``$KAIROS_URL``, the address saved by ``kairos connect``, then
``http://localhost:8089``. How requests are signed, in order: the ``token`` argument, ``$KAIROS_TOKEN``, a session saved
by ``login_dev`` / ``login_code`` for this gateway, then the dev headers (``$KAIROS_USER``, default ``alice``, and
``$KAIROS_ORG``, default ``acme``), which a gateway accepts only in dev mode.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://localhost:8089"
FINAL = ("completed", "failed", "cancelled")


def config_dir() -> Path:
    return Path(os.environ.get("KAIROS_CONFIG_DIR") or Path.home() / ".config" / "kairos")


class KairosError(Exception):
    """A gateway error: ``status`` is the HTTP status (0 when unreachable) and ``code`` the KAIROS error code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}" if status else message)
        self.status, self.code, self.message = status, code, message


class _Store:
    """The saved default gateway and one session per gateway, in ``~/.config/kairos`` (or ``$KAIROS_CONFIG_DIR``)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or config_dir()

    def _read(self, name: str) -> Any:
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, name: str, data: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / name
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)  # sessions are bearer tokens
        except OSError:
            pass

    def url(self) -> str | None:
        return (self._read("config.json") or {}).get("url")

    def set_url(self, url: str) -> None:
        self._write("config.json", {**(self._read("config.json") or {}), "url": url})

    def session(self, url: str) -> dict[str, Any] | None:
        s = (self._read("sessions.json") or {}).get(url)
        if s and s.get("expires_at", "") > time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()):
            return s
        return None

    def set_session(self, url: str, session: dict[str, Any] | None) -> None:
        all_ = self._read("sessions.json") or {}
        if session is None:
            all_.pop(url, None)
        else:
            all_[url] = session
        self._write("sessions.json", all_)


class Kairos:
    """A client for one KAIROS gateway.

    >>> m = Kairos("http://localhost:8089")
    >>> task = m.ask("Why is Project Apollo over budget?", on_entry=lambda e: print(e["summary"]))
    >>> print(task["result"]["summary"])
    """

    def __init__(self, url: str | None = None, *, token: str | None = None, user: str | None = None,
                 org: str | None = None, timeout: float = 30, remember: bool = True,
                 config: str | os.PathLike[str] | None = None) -> None:
        self._store = _Store(Path(config) if config else None)
        self.url = (url or os.environ.get("KAIROS_URL") or self._store.url() or DEFAULT_URL).rstrip("/")
        self.token = token or os.environ.get("KAIROS_TOKEN")
        if not self.token and remember:
            saved = self._store.session(self.url)
            self.token = saved["token"] if saved else None
        self.user = user or os.environ.get("KAIROS_USER", "alice")
        self.org = org or os.environ.get("KAIROS_ORG", "acme")
        self.timeout = timeout
        self.remember = remember

    def __repr__(self) -> str:
        return f"Kairos({self.url!r}, signed_in={bool(self.token)})"

    # -- transport --------------------------------------------------------------------------------------------------

    def headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {"X-Kairos-User": self.user, "X-Kairos-Org": self.org}

    def request(self, method: str, path: str, body: Any = None, *, params: dict[str, Any] | None = None,
                raw: bytes | None = None, content_type: str | None = None, timeout: float | None = None) -> Any:
        """Call any gateway route; returns parsed JSON (or bytes for non-JSON responses)."""
        query = {k: v for k, v in (params or {}).items() if v is not None}
        target = self.url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {**self.headers(), "Accept": "application/json", "User-Agent": "kairos-os-python"}
        if data is not None:
            headers["Content-Type"] = content_type or "application/json"
        req = urllib.request.Request(target, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                payload = r.read()
                if "json" in (r.headers.get("Content-Type") or "") or payload[:1] in (b"{", b"["):
                    return json.loads(payload) if payload else None
                return payload
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read() or b"{}")
            except ValueError:
                err = {}
            detail = err.get("detail")
            message = err.get("message") or (detail if isinstance(detail, str) else json.dumps(detail) if detail else e.reason)
            raise KairosError(e.code, err.get("code", "HTTP_ERROR"), str(message)) from None
        except (urllib.error.URLError, OSError) as e:
            raise KairosError(0, "UNREACHABLE", f"cannot reach the KAIROS gateway at {self.url}: {e}") from None

    def get(self, route: str, /, **params: Any) -> Any:
        return self.request("GET", route, params=params)

    def post(self, route: str, body: Any = None, /, **params: Any) -> Any:
        return self.request("POST", route, body, params=params)

    # -- system -----------------------------------------------------------------------------------------------------

    def health(self) -> bool:
        try:
            return bool((self.get("/health") or {}).get("ok"))
        except KairosError:
            return False

    def status(self) -> dict[str, Any]:
        return self.get("/system/status")

    def resources(self) -> dict[str, Any]:
        return self.get("/system/resources")

    def config(self) -> dict[str, Any]:
        """The whole running system as one picture (``GET /system/config``); secrets are redacted."""
        return self.get("/system/config")

    def models(self) -> Any:
        return self.get("/models")

    # -- identity ---------------------------------------------------------------------------------------------------

    def auth_config(self) -> dict[str, Any]:
        return self.get("/auth/config")

    def _signed_in(self, session: dict[str, Any]) -> dict[str, Any]:
        self.token = session["token"]
        if self.remember:
            self._store.set_session(self.url, session)
        return session

    def login_dev(self, email: str, name: str = "") -> dict[str, Any]:
        """Sign in by email (gateways in dev mode). Demo people: alice (owner), priya (approver), sam (viewer) @acme.example."""
        return self._signed_in(self.post("/auth/dev", {"email": email, "name": name}))

    def login_code(self, code: str) -> dict[str, Any]:
        """Sign in with a one-time code from the console (your name in the menu bar, then Sign in on your phone)."""
        return self._signed_in(self.post("/auth/pair/redeem", {"code": code.strip()}))

    def login_google(self, id_token: str) -> dict[str, Any]:
        return self._signed_in(self.post("/auth/google", {"id_token": id_token}))

    def logout(self) -> None:
        try:
            if self.token:
                self.post("/auth/logout")
        finally:
            self.token = None
            if self.remember:
                self._store.set_session(self.url, None)

    def me(self) -> dict[str, Any]:
        """Who you are: user, org, role and permissions."""
        return self.get("/auth/me")

    def pairing_code(self) -> dict[str, Any]:
        """Create a one-time code that signs the same person in elsewhere (a phone, a shell)."""
        return self.post("/auth/pair")

    # -- tasks ------------------------------------------------------------------------------------------------------

    def create_task(self, goal: str, *, priority: str = "normal", **fields: Any) -> dict[str, Any]:
        return self.post("/tasks", {"goal": goal, "priority": priority, **fields})

    def tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = self.get("/tasks", status=status) or []
        return sorted(rows, key=lambda t: t.get("created_at") or "", reverse=True)

    def task(self, task_id: str) -> dict[str, Any]:
        return self.get(f"/tasks/{task_id}")

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self.post(f"/tasks/{task_id}/cancel")

    def resume(self, task_id: str) -> dict[str, Any]:
        return self.post(f"/tasks/{task_id}/resume")

    def artifacts(self, task_id: str) -> Any:
        return self.get(f"/tasks/{task_id}/artifacts")

    def artifact(self, task_id: str, name: str) -> Any:
        return self.get(f"/tasks/{task_id}/artifacts/{urllib.parse.quote(name)}")

    def audit(self, task_id: str) -> dict[str, Any]:
        """The task's hash-chained journal: ``entries`` and ``chain_verified``."""
        return self.get(f"/audit/{task_id}")

    def wait(self, task_id: str, *, on_entry: Callable[[dict[str, Any]], None] | None = None,
             on_approval: Callable[[dict[str, Any]], None] | None = None, poll: float = 1.2,
             timeout: float | None = None) -> dict[str, Any]:
        """Follow a task until it ends. ``on_entry`` gets each new journal entry (the story of the run) and
        ``on_approval`` each approval the task raises. Returns the final task."""
        seen: set[str] = set()
        asked: set[str] = set()
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            if on_entry:
                for e in (self.audit(task_id) or {}).get("entries", []):
                    if e.get("entry_id") not in seen:
                        seen.add(e.get("entry_id"))
                        on_entry(e)
            if on_approval:
                for a in self.approvals("pending"):
                    if a.get("task_id") == task_id and a["approval_id"] not in asked:
                        asked.add(a["approval_id"])
                        on_approval(a)
            t = self.task(task_id)
            if t.get("status") in FINAL:
                return t
            if deadline and time.monotonic() > deadline:
                raise TimeoutError(f"{task_id} is still {t.get('status')}")
            time.sleep(poll)

    def ask(self, goal: str, *, priority: str = "normal", wait: bool = True, **kw: Any) -> dict[str, Any]:
        """Start a task and (by default) wait for it; keyword arguments go to :meth:`wait`."""
        t = self.create_task(goal, priority=priority)
        return self.wait(t["task_id"], **kw) if wait else t

    # -- governance -------------------------------------------------------------------------------------------------

    def approvals(self, status: str | None = "pending") -> list[dict[str, Any]]:
        return self.get("/approvals", status=status) or []

    def approve(self, approval_id: str, comment: str | None = None) -> dict[str, Any]:
        return self.post(f"/approvals/{approval_id}/approve", {"comment": comment})

    def reject(self, approval_id: str, comment: str | None = None) -> dict[str, Any]:
        return self.post(f"/approvals/{approval_id}/reject", {"comment": comment})

    def policies(self) -> Any:
        return self.get("/policies")

    # -- agents -----------------------------------------------------------------------------------------------------

    def agents(self, task_id: str | None = None) -> list[dict[str, Any]]:
        """The process table: every agent with its PID, state and task."""
        return self.get("/agents", task_id=task_id) or []

    def agent_tree(self, task_id: str | None = None) -> Any:
        return self.get("/agents/tree", task_id=task_id)

    def agent(self, pid: int) -> dict[str, Any]:
        return self.get(f"/agents/{pid}")

    def pause(self, pid: int) -> Any:
        return self.post(f"/agents/{pid}/pause")

    def resume_agent(self, pid: int) -> Any:
        return self.post(f"/agents/{pid}/resume")

    def kill(self, pid: int) -> Any:
        return self.post(f"/agents/{pid}/kill")

    def registry(self) -> dict[str, Any]:
        """Agent templates and tools the gateway knows."""
        return {"agents": self.get("/registry/agents"), "tools": self.get("/registry/tools")}

    def sandboxes(self, task_id: str | None = None) -> Any:
        return self.get("/sandboxes", task_id=task_id)

    # -- knowledge and memory ---------------------------------------------------------------------------------------

    def search(self, query: str, *, top_k: int = 8, scope: str | None = None) -> dict[str, Any]:
        """Hybrid search over /org; ``hits`` carry ``path``, ``title``, ``score``, ``snippet`` and ``firewall_flags``."""
        return self.get("/knowledge/search", q=query, top_k=top_k, scope=scope)

    def tree(self, path: str = "/org") -> Any:
        return self.get("/knowledge/tree", path=path)

    def read(self, path: str) -> dict[str, Any]:
        """One /org document: ``frontmatter`` and ``body``."""
        return self.get("/knowledge/object", path=path)

    def graph(self, path: str | None = None, depth: int | None = None) -> Any:
        return self.get("/knowledge/graph", path=path, depth=depth)

    def memory(self, owner: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
        return self.get("/memory", owner=owner, task_id=task_id) or []

    def upload(self, files: Iterable[str | os.PathLike[str] | tuple[str, bytes]], target: str = "/org/uploads",
               privacy: str | None = None) -> dict[str, Any]:
        """Add files to /org (paths, or ``(name, bytes)`` pairs). Returns ``created``, ``updated``, ``skipped``, ``errors``."""
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in {"target_folder": target, **({"privacy": privacy} if privacy else {})}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for f in files:
            name, data = f if isinstance(f, tuple) else (Path(f).name, Path(f).read_bytes())
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                         f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self.request("POST", "/knowledge/upload", raw=b"".join(parts),
                            content_type=f"multipart/form-data; boundary={boundary}", timeout=max(self.timeout, 120))

    def mounts(self) -> list[dict[str, Any]]:
        return self.get("/knowledge/mounts") or []

    def mount(self, host_path: str, name: str) -> dict[str, Any]:
        """Mirror a folder **of the machine running the gateway** into /org/mnt/<name> (watched, read-only)."""
        return self.request("POST", "/knowledge/mounts", {"name": name, "host_path": host_path}, timeout=300)

    def unmount(self, name: str) -> Any:
        return self.request("DELETE", f"/knowledge/mounts/{name}")

    # -- connectors -------------------------------------------------------------------------------------------------

    def connectors(self) -> Any:
        return self.get("/connectors")

    def sync(self, connector_id: str) -> Any:
        return self.post(f"/connectors/{connector_id}/sync")
