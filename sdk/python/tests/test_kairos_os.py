"""kairos-os against a stub gateway (standard library HTTP server): headers, sessions, errors, waiting, uploads, the CLI."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kairos_os import Kairos, KairosError  # noqa: E402
from kairos_os.cli import main  # noqa: E402

SEEN: list[dict] = []


class Gateway(BaseHTTPRequestHandler):
    polls = 0

    def log_message(self, *_):
        pass

    def _send(self, status: int, body) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _record(self) -> tuple[str, dict, bytes]:
        url = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        SEEN.append({"method": self.command, "path": url.path, "query": parse_qs(url.query), "headers": dict(self.headers),
                     "body": raw})
        return url.path, parse_qs(url.query), raw

    def do_GET(self):  # noqa: N802
        path, query, _ = self._record()
        auth = self.headers.get("Authorization")
        if path == "/health":
            return self._send(200, {"ok": True})
        if path == "/auth/me":
            if auth == "Bearer bad":
                return self._send(401, {"code": "UNAUTHENTICATED", "message": "session expired"})
            return self._send(200, {"user": {"email": "priya@acme.example"}, "org": {"name": "Acme Corp"}, "role": "approver",
                                    "permissions": ["task.create", "approval.resolve"]})
        if path == "/system/status":
            return self._send(200, {"version": "0.1.0", "contract_version": "0.13.0",
                                    "components": [{"component": "kernel", "ok": True, "mode": "real"}]})
        if path == "/tasks/T-1":
            Gateway.polls += 1
            status = "completed" if Gateway.polls >= 2 else "running"
            return self._send(200, {"task_id": "T-1", "goal": "g", "status": status,
                                    "result": {"summary": "**31%** over budget", "evidence": ["/org/finance/a"]}})
        if path == "/tasks":
            return self._send(200, [{"task_id": "T-0", "goal": "old", "status": "completed", "created_at": "2026-09-30"},
                                    {"task_id": "T-1", "goal": "new", "status": "running", "created_at": "2026-10-01"}])
        if path == "/audit/T-1":
            return self._send(200, {"entries": [{"entry_id": "e1", "kind": "spawn", "summary": "Spawned planner", "actor": "kernel"}],
                                    "chain_verified": True})
        if path == "/approvals":
            return self._send(200, [{"approval_id": "APR-1", "task_id": "T-1", "agent": "action-agent",
                                     "syscall": {"capability": "jira.write", "risk": "medium"}}])
        if path == "/knowledge/search":
            return self._send(200, {"hits": [{"path": "/org/inbox/x", "title": "Vendor email", "score": 0.9, "snippet": "s",
                                              "firewall_flags": ["instruction_like"]}], "query": query["q"][0]})
        if path == "/knowledge/tree":
            return self._send(200, {"path": "/org", "entries": [{"path": "/org/finance", "title": "Finance", "is_dir": True}]})
        return self._send(404, {"code": "NOT_FOUND", "message": f"no route {path}"})

    def do_POST(self):  # noqa: N802
        path, _, raw = self._record()
        if path == "/auth/dev":
            body = json.loads(raw)
            return self._send(200, {"token": "tok-" + body["email"].split("@")[0], "expires_at": "2999-01-01T00:00:00Z",
                                    "me": {"user": {"email": body["email"]}, "org": {"name": "Acme Corp"}, "role": "approver"}})
        if path == "/auth/logout":
            return self._send(200, {"ok": True})
        if path == "/tasks":
            Gateway.polls = 0
            return self._send(200, {"task_id": "T-1", "goal": json.loads(raw)["goal"], "status": "planning"})
        if path == "/approvals/APR-1/approve":
            return self._send(200, {"approval_id": "APR-1", "status": "approved", "comment": json.loads(raw)["comment"]})
        if path == "/knowledge/upload":
            return self._send(200, {"created": ["/org/uploads/notes"], "updated": [], "skipped": [], "errors": []})
        return self._send(404, {"code": "NOT_FOUND", "message": "no"})


@pytest.fixture()
def gw(tmp_path, monkeypatch):
    for k in ("KAIROS_URL", "KAIROS_TOKEN", "KAIROS_USER", "KAIROS_ORG"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KAIROS_CONFIG_DIR", str(tmp_path / "cfg"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    SEEN.clear()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_dev_headers_until_signed_in_then_a_saved_session(gw):
    m = Kairos(gw)
    assert m.health()
    m.me()
    assert SEEN[-1]["headers"]["X-Kairos-User"] == "alice"
    m.login_dev("priya@acme.example")
    m.me()
    assert SEEN[-1]["headers"]["Authorization"] == "Bearer tok-priya"
    assert Kairos(gw).token == "tok-priya"  # remembered for this gateway
    m.logout()
    assert Kairos(gw).token is None


def test_errors_carry_status_and_code(gw):
    with pytest.raises(KairosError) as e:
        Kairos(gw, token="bad").me()
    assert (e.value.status, e.value.code) == (401, "UNAUTHENTICATED")
    with pytest.raises(KairosError) as e:
        Kairos("http://127.0.0.1:9", timeout=1).status()
    assert e.value.status == 0 and e.value.code == "UNREACHABLE"


def test_ask_waits_and_reports_the_story_and_approvals(gw):
    entries, approvals = [], []
    t = Kairos(gw).ask("Why is Apollo late?", on_entry=entries.append, on_approval=approvals.append, poll=0.01)
    assert t["status"] == "completed"
    assert [e["entry_id"] for e in entries] == ["e1"]  # each entry once, however many polls
    assert [a["approval_id"] for a in approvals] == ["APR-1"]


def test_queries_drop_unset_params_and_upload_is_multipart(gw, tmp_path):
    m = Kairos(gw)
    assert m.search("apollo budget", top_k=3)["query"] == "apollo budget"
    assert SEEN[-1]["query"] == {"q": ["apollo budget"], "top_k": ["3"]}
    f = tmp_path / "notes.md"
    f.write_text("# hi")
    assert m.upload([f, ("b.txt", b"x")])["created"] == ["/org/uploads/notes"]
    assert SEEN[-1]["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'filename="notes.md"' in SEEN[-1]["body"] and b'name="target_folder"' in SEEN[-1]["body"]


def test_tasks_newest_first(gw):
    assert [t["task_id"] for t in Kairos(gw).tasks()] == ["T-1", "T-0"]


def test_cli(gw, capsys):
    assert main(["--url", gw, "status"]) == 0
    assert "1/1 components healthy" in capsys.readouterr().out
    assert main(["--url", gw, "ask", "Why", "is", "Apollo", "late?"]) == 0
    text = capsys.readouterr().out
    assert "Spawned planner" in text and "kairos approve APR-1" in text and "31% over budget" in text
    assert main(["approve", "APR-1", "-m", "ok", "--url", gw]) == 0
    assert "APR-1 approved" in capsys.readouterr().out
    assert main(["--url", gw, "search", "vendor", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["hits"][0]["title"] == "Vendor email"
    assert main(["--url", gw, "ls"]) == 0
    assert "finance/" in capsys.readouterr().out
    assert main(["--url", gw, "connect", gw]) == 0
    assert Kairos().url == gw  # saved as the default
    assert main(["--url", "http://127.0.0.1:9", "tasks"]) == 1


def test_org_paths_survive_git_bash():
    from kairos_os.cli import org_path

    assert org_path("/org/finance") == "/org/finance"
    assert org_path("finance/apollo-budget") == "/org/finance/apollo-budget"
    assert org_path("C:/Program Files/Git/org/finance") == "/org/finance"
    assert org_path("") == "/org"
