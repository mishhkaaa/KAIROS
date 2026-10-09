"""KAIROS OS: the gateway client shared by the `kairos` command and the /org filesystem. Standard library only.

The gateway runs on Windows (kairosd, port 8089 for the demo). From inside WSL it is found at, in order: $KAIROS_URL,
/etc/kairos/env, the address that worked last time, localhost (mirrored networking), then the Windows host (the WSL
default route). Signed in (`kairos login`), requests carry the session token; otherwise the dev headers (KAIROS_USER,
default alice), which the gateway accepts only in dev mode.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

CONFIG = Path(os.environ.get("KAIROS_CONFIG_DIR", Path.home() / ".config" / "kairos"))
SESSION = CONFIG / "session.json"
LAST_URL = CONFIG / "url"
PORTS = (8089, 8080)


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in Path("/etc/kairos/env").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def _windows_host() -> str | None:
    try:
        route = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=2).stdout.split()
        return route[route.index("via") + 1] if "via" in route else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=1.5) as r:
            return r.status == 200
    except (OSError, urllib.error.URLError):
        return False


_url: str | None = None


def gateway_url(refresh: bool = False) -> str:
    """The gateway's address (see the module doc); remembered once found."""
    global _url
    if _url and not refresh:
        return _url
    fixed = os.environ.get("KAIROS_URL") or _env_file().get("KAIROS_URL")
    if fixed:
        _url = fixed.rstrip("/")
        return _url
    candidates: list[str] = []
    try:
        candidates.append(LAST_URL.read_text().strip())
    except OSError:
        pass
    host = _windows_host()
    for port in PORTS:
        candidates.append(f"http://localhost:{port}")
        if host:
            candidates.append(f"http://{host}:{port}")
    for c in dict.fromkeys(x for x in candidates if x):
        if _alive(c):
            _url = c
            try:
                CONFIG.mkdir(parents=True, exist_ok=True)
                LAST_URL.write_text(c)
            except OSError:
                pass
            return c
    _url = candidates[-1] if candidates else "http://localhost:8089"
    return _url


def session() -> dict[str, Any] | None:
    try:
        s = json.loads(SESSION.read_text())
    except (OSError, ValueError):
        return None
    return s if s.get("expires_at", "") > time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) else None


def save_session(s: dict[str, Any] | None) -> None:
    CONFIG.mkdir(parents=True, exist_ok=True)
    if s is None:
        SESSION.unlink(missing_ok=True)
        return
    SESSION.write_text(json.dumps(s))
    SESSION.chmod(0o600)


def _headers() -> dict[str, str]:
    s = session()
    if s:
        return {"Authorization": f"Bearer {s['token']}"}
    return {"X-Kairos-User": os.environ.get("KAIROS_USER", "alice"), "X-Kairos-Org": os.environ.get("KAIROS_ORG", "acme")}


def call(method: str, path: str, body: Any = None, *, timeout: float = 20, raw: bytes | None = None,
         content_type: str | None = None) -> Any:
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = _headers()
    if data is not None:
        headers["Content-Type"] = content_type or "application/json"
    req = urllib.request.Request(gateway_url() + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read() or b"{}")
        except ValueError:
            err = {}
        raise GatewayError(e.code, err.get("code", "HTTP_ERROR"), err.get("message") or err.get("detail") or e.reason) from None
    except (urllib.error.URLError, OSError) as e:
        global _url
        where, _url = gateway_url(), None  # look again next time: the gateway may have moved or not be up yet
        raise GatewayError(0, "UNREACHABLE", f"cannot reach the KAIROS gateway at {where}: {e}") from None


def q(**params: Any) -> str:
    kept = {k: v for k, v in params.items() if v is not None}
    return "?" + urllib.parse.urlencode(kept) if kept else ""


def upload(files: list[tuple[str, bytes]], target: str = "/org/uploads", privacy: str | None = None) -> dict[str, Any]:
    """POST /knowledge/upload as multipart/form-data."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    fields = {"target_folder": target, **({"privacy": privacy} if privacy else {})}
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for name, data in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return call("POST", "/knowledge/upload", raw=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}",
                timeout=120)


def windows_path(linux_path: str) -> str:
    """How the Windows gateway sees a path in this distro: /mnt/c/x -> C:\\x, anything else through \\\\wsl.localhost."""
    p = Path(linux_path).expanduser().resolve()
    parts = p.parts
    if len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1:
        return f"{parts[2].upper()}:\\" + "\\".join(parts[3:])
    distro = os.environ.get("WSL_DISTRO_NAME", "kairos-os")
    return f"\\\\wsl.localhost\\{distro}" + str(p).replace("/", "\\")


def render(obj: dict[str, Any]) -> str:
    """A knowledge object as a Markdown file: its frontmatter, then its body."""
    fm = {k: v for k, v in (obj.get("frontmatter") or {}).items() if v not in (None, [], "")}
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {json.dumps(v) if not isinstance(v, str) or any(c in v for c in ':#[]{}') else v}")
    lines += [f"path: {obj.get('path')}", "---", ""]
    return "\n".join(lines) + (obj.get("body") or "")
