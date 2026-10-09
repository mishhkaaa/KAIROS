"""Demo preflight / QA checklist that runs anywhere (Windows laptop, Linux node, macOS). P4.

    uv run python scripts/preflight.py [--gateway http://127.0.0.1:8089] [--no-warm]

Every line prints a tick or a cross; the exit code is the number of failures. Also warms the models and measures
generation speed: a model "100% GPU" in `ollama ps` can still crawl when another process holds VRAM, because Windows
spills the overflow into shared memory. The Linux appliance keeps scripts/preflight.sh (systemd, compose GPU).
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "python"))
from kairos_contracts.wiring import Settings  # noqa: E402

GREEN, RED, DIM, END = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
MIN_TOKENS_PER_S = 25.0
failures = 0


def check(label: str, fn: Callable[[], object]) -> None:
    """Pass when fn returns something truthy; a string is shown as detail."""
    global failures
    try:
        out = fn()
        ok = bool(out)
        detail = f"  {out}" if isinstance(out, str) else ""
    except Exception as e:  # noqa: BLE001 — any error is a failed check
        ok, detail = False, f"  ({type(e).__name__}: {str(e)[:120]})"
    print(f"  {GREEN + 'ok ' if ok else RED + 'XX '}{END} {label}{detail}")
    failures += 0 if ok else 1


def skip(label: str, why: str) -> None:
    print(f"  {DIM}-- {END} {label}: {why}")


def run(*cmd: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gateway", default=os.getenv("KAIROS_URL", "http://127.0.0.1:8080"))
    ap.add_argument("--no-warm", action="store_true", help="skip warming models and the speed check")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    s = Settings.from_env()
    gw = httpx.Client(base_url=a.gateway.rstrip("/"), timeout=10, headers={"X-Kairos-User": "preflight", "X-Kairos-Org": "acme"})
    ollama = httpx.Client(base_url=s.ollama_url.rstrip("/"), timeout=180)
    linux = platform.system() == "Linux"

    print(f"gateway {a.gateway}")
    status: dict = {}

    def ready() -> bool:
        status.update(gw.get("/system/status").json())
        return status["ready"] is True

    check("gateway /system/status ready", ready)
    check("all components real", lambda: not [c["component"] for c in status.get("components", []) if c["mode"] != "real"])
    check("all components healthy", lambda: all(c["ok"] for c in status.get("components", [])))

    print("services")
    if linux and shutil.which("systemctl"):
        check("kairosd.service active", lambda: run("systemctl", "is-active", "--quiet", "kairosd").returncode == 0)
    else:
        skip("kairosd.service", "not a systemd host (kairosd runs in a terminal)")
    running = run("docker", "ps", "--format", "{{.Names}}").stdout.split() if shutil.which("docker") else []
    check("docker reachable", lambda: shutil.which("docker") and run("docker", "info").returncode == 0)
    check("vendor-docs container running (browser sandbox target)", lambda: any("vendor-docs" in n for n in running))
    check("postgres reachable", lambda: _pg_ok(s.database_url))

    print("models")
    cfg = yaml.safe_load(Path(s.models_config).read_text(encoding="utf-8")) or {}
    chat = cfg.get("default")
    wanted = sorted({cfg.get("embedding"), chat, cfg.get("latency_critical") or chat,
                     *(v for k, v in (cfg.get("by_task_class") or {}).items() if k not in ("code", "vision"))} - {None})
    tags = {m["name"] for m in ollama.get("/api/tags").json().get("models", [])}
    for m in wanted:
        check(f"pulled: {m}", lambda m=m: m in tags or f"{m}:latest" in tags)
    if a.no_warm:
        skip("warm + speed", "--no-warm")
    else:
        emb = cfg.get("embedding")
        if emb:
            check(f"warm: {emb}", lambda: ollama.post("/api/embed", json={"model": emb, "input": "warmup", "keep_alive": -1}).is_success)
        for m in [x for x in wanted if x != emb]:
            def speed(m: str = m) -> str | bool:
                r = ollama.post("/api/generate", json={"model": m, "prompt": "Write two sentences about budgets.", "stream": False,
                                                        "keep_alive": -1, "options": {"num_predict": 80}}).json()
                tps = r["eval_count"] / max(r["eval_duration"] / 1e9, 1e-6)
                return f"{tps:.0f} tok/s" if tps >= MIN_TOKENS_PER_S else False
            check(f"warm + generation speed >= {MIN_TOKENS_PER_S:.0f} tok/s: {m}", speed)
        loaded = ollama.get("/api/ps").json().get("models", [])
        for m in loaded:
            check(f"fully on the GPU: {m['name']}", lambda m=m: m.get("size_vram", 0) >= m.get("size", 1))

    print("sandboxes + browser")
    for img in ("kairos/sandbox-base:latest", "kairos/sandbox-browser:latest"):
        check(f"image {img}", lambda img=img: run("docker", "image", "inspect", img).returncode == 0)
    check("browser smoke (vendor-docs through the sandbox)", lambda: run(sys.executable, "scripts/browser_smoke.py", timeout=180).returncode == 0)

    print("knowledge")
    check("bundle valid (scripts/check_okf.py)", lambda: run(sys.executable, "scripts/check_okf.py").returncode == 0)
    check("search 'apollo budget' returns hits",
          lambda: len(gw.get("/knowledge/search", params={"q": "apollo budget", "top_k": 3}).json()["hits"]) > 0)
    check("no task running (safe to reset memories)", lambda: not [t for t in gw.get("/tasks").json()
                                                                   if t["status"] in ("queued", "planning", "running", "waiting_approval")])

    print("host")
    data = Path(s.data_dir)
    check(f"{data} has > 10 GB free", lambda: shutil.disk_usage(data if data.exists() else ROOT).free > 10 * 2**30)
    if linux:
        check("lid switch ignored", lambda: any("HandleLidSwitch=ignore" in p.read_text() for p in Path("/etc/systemd/logind.conf.d").glob("*")))
    else:
        skip("lid switch", "Linux appliance only (on a laptop: plug in AC and set the lid to do nothing)")
    if shutil.which("tailscale"):
        check("tailscale up", lambda: run("tailscale", "status").returncode == 0)
    else:
        skip("tailscale", "not installed (the laptop is the node)")

    print()
    print(f"preflight: {'all green' if failures == 0 else f'{failures} check(s) failed'}")
    return failures


def _pg_ok(url: str) -> bool:
    import psycopg

    dsn = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, connect_timeout=3):
        return True


if __name__ == "__main__":
    t0 = time.monotonic()
    code = main()
    print(f"({time.monotonic() - t0:.0f} s)")
    sys.exit(code)
