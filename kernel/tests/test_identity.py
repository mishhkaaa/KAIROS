"""Who may do what (orgs, members, roles, sessions), the connector vault, uploads and mounted folders."""
import pytest
from fastapi.testclient import TestClient
from kairos_contracts.schema import ToolResult, ToolResultStatus
from kairos_kernel.gateway.app import create_app
from kairos_kernel.testing import done, manifest


def _kernel(make_kernel, **overrides):
    async def planner(goal, ctx):
        return done(ctx, "ok")

    return make_kernel({"planner-agent": planner}, [manifest("planner-agent")], **overrides)


@pytest.fixture
def dev(make_kernel):
    with TestClient(create_app(_kernel(make_kernel))) as c:
        yield c


def signin(c, email, name=""):
    r = c.post("/auth/dev", json={"email": email, "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_dev_mode_keeps_header_callers_working_as_owners_of_the_seeded_org(dev):
    me = dev.get("/auth/me").json()
    assert (me["user"]["user_id"], me["role"], me["org"]["org_id"]) == ("alice", "owner", "acme")
    assert "members.manage" in me["permissions"]
    assert dev.get("/auth/config").json() == {"mode": "dev", "google_client_id": None}
    roles = [r["role"] for r in dev.get("/orgs/acme/roles").json()]
    assert roles[0] == "owner" and set(roles) == {"owner", "admin", "approver", "member", "viewer"}
    assert dev.post("/tasks", json={"goal": "x", "metadata": {"root_agent": "planner-agent"}}).status_code == 201


def test_roles_decide_what_a_signed_in_member_may_do(dev):
    assert dev.post("/orgs/acme/members", json={"email": "Bob@acme.example", "role": "viewer"}).json()["status"] == "invited"
    bob = signin(dev, "bob@acme.example", "Bob")
    me = dev.get("/auth/me", headers=bob).json()
    assert (me["role"], me["org"]["org_id"]) == ("viewer", "acme")  # the invitation became a membership at sign-in
    assert dev.get("/knowledge/tree", headers=bob).status_code == 200
    denied = dev.post("/tasks", json={"goal": "x"}, headers=bob)
    assert denied.status_code == 403 and denied.json()["code"] == "PERMISSION_DENIED"
    assert "task.create" in denied.json()["message"]
    assert dev.post("/approvals/A-1/approve", json={}, headers=bob).status_code == 403
    assert dev.get("/system/config", headers=bob).status_code == 403

    assert dev.patch("/orgs/acme/members/bob", json={"role": "approver"}).json()["role"] == "approver"
    assert dev.post("/approvals/A-nope/approve", json={}, headers=bob).status_code == 404  # allowed now; no such approval


def test_the_demo_org_has_teammates_waiting_and_its_domain_lets_colleagues_in(dev):
    members = {m["email"]: m for m in dev.get("/orgs/acme/members").json()}
    assert (members["priya@acme.example"]["role"], members["priya@acme.example"]["status"]) == ("approver", "invited")
    sam = dev.get("/auth/me", headers=signin(dev, "sam@acme.example", "Sam")).json()
    assert (sam["role"], "task.create" in sam["permissions"]) == ("viewer", False)
    newcomer = dev.get("/auth/me", headers=signin(dev, "lee@acme.example")).json()
    assert (newcomer["org"]["org_id"], newcomer["role"]) == ("acme", "member")


def test_org_guard_rails(dev):
    dev.post("/orgs/acme/members", json={"email": "ann@acme.example", "role": "admin"})
    ann = signin(dev, "ann@acme.example")
    made_owner = dev.patch("/orgs/acme/members/zed@acme.example", json={"role": "owner"}, headers=ann)
    assert made_owner.status_code == 404
    dev.post("/orgs/acme/members", json={"email": "zed@acme.example", "role": "member"})
    assert dev.patch("/orgs/acme/members/zed@acme.example", json={"role": "owner"}, headers=ann).json()["code"] == "PERMISSION_DENIED"
    assert dev.patch("/orgs/acme/members/alice", json={"role": "admin"}).json()["code"] == "CONFLICT"  # the last owner
    assert dev.delete("/orgs/acme/members/alice").status_code == 409
    assert dev.post("/orgs/acme/members", json={"email": "ann@acme.example"}).status_code == 409
    assert dev.get("/orgs/other/members", headers=ann).json()["code"] == "PERMISSION_DENIED"


def test_a_new_user_creates_an_org_and_owns_it(dev):
    newbie = signin(dev, "dana@startup.io", "Dana")
    me = dev.get("/auth/me", headers=newbie).json()
    assert me["org"] is None and me["permissions"] == []
    assert dev.get("/tasks", headers=newbie).json()["code"] == "PERMISSION_DENIED"  # join or create an org first
    org = dev.post("/orgs", json={"name": "Startup Labs", "domain": "startup.io"}, headers=newbie).json()
    assert org["org_id"] == "startup-labs" and org["member_count"] == 1
    me = dev.get("/auth/me", headers=newbie).json()
    assert (me["org"]["org_id"], me["role"]) == ("startup-labs", "owner")
    assert dev.post("/auth/logout", headers=newbie).status_code == 204
    assert dev.get("/auth/me", headers=newbie).status_code == 401


def test_google_mode_requires_a_session(make_kernel, monkeypatch):
    k = _kernel(make_kernel)
    k.settings.auth = "google"
    k.settings.google_client_id = "client-123.apps.googleusercontent.com"
    with TestClient(create_app(k)) as c:
        assert c.get("/auth/config").json() == {"mode": "google", "google_client_id": "client-123.apps.googleusercontent.com"}
        assert c.get("/tasks").status_code == 401
        assert c.get("/health").status_code == 200
        assert c.post("/auth/dev", json={"email": "x@y.z"}).status_code == 403

        from google.oauth2 import id_token

        seen = {}

        def verify(token, request, audience):
            seen["audience"] = audience
            if token != "good":
                raise ValueError("bad signature")
            return {"email": "eve@acme.example", "email_verified": True, "name": "Eve", "picture": "https://x/eve.png"}

        monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
        assert c.post("/auth/google", json={"id_token": "forged"}).status_code == 401
        s = c.post("/auth/google", json={"id_token": "good"}).json()
        assert seen["audience"] == "client-123.apps.googleusercontent.com"
        assert s["me"]["user"]["email"] == "eve@acme.example" and s["me"]["org"] is None
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):  # no token: the socket is refused
            with c.websocket_connect("/ws/events?types=task.*") as ws:
                ws.receive_text()
        with c.websocket_connect(f"/ws/events?types=task.*&token={s['token']}"):
            pass


class StubGitHub:
    name = "github"

    def __init__(self):
        self.token = None

    def configure(self, token):
        self.token = token

    def spec(self):
        return None

    async def execute(self, inv):
        data = {"list_issues": {"issues": [{"number": 7, "title": "Backfill", "state": "open", "labels": ["apollo"],
                                            "html_url": "u", "body": "b"}]},
                "get_file": {"content": "# readme\n"}}[inv.operation]
        return ToolResult(invocation_id=inv.invocation_id, status=ToolResultStatus.SUCCESS, output=data)


class StubTools:
    def __init__(self):
        self.backends = {"github": StubGitHub()}

    async def list_tools(self):
        return []


def test_connectors_keep_tokens_in_the_vault_and_hand_them_to_the_backend(make_kernel, tmp_path):
    import base64
    import os

    tools = StubTools()
    k = _kernel(make_kernel, tools=tools)
    k.settings.vault_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    with TestClient(create_app(k)) as c:
        listed = {x["connector_id"]: x for x in c.get("/connectors").json()}
        assert listed["github"]["status"] == "disconnected" and listed["google_calendar"]["capabilities"] == ["calendar.read", "calendar.write"]
        conn = c.post("/connectors/github/connect", json={"token": "ghp_secret_value", "account": "acme/recon"}).json()
        assert (conn["status"], conn["mode"], conn["connected_by"]) == ("connected", "live", "alice")
        assert "ghp_secret_value" not in str(conn)
        assert tools.backends["github"].token == "ghp_secret_value"
        identity = c.app.state.identity
        assert identity.vault.encrypted and "ghp_secret_value" not in identity.db.one("SELECT blob FROM vault")["blob"]
        assert identity.vault.get("acme", "connector:github") == {"token": "ghp_secret_value"}
        synced = c.post("/connectors/github/sync").json()
        assert synced["errors"] == [] and c.get("/connectors").json()[0]["last_sync"]
        assert c.delete("/connectors/github").status_code == 204
        assert tools.backends["github"].token is None
        assert c.post("/connectors/github/sync").status_code == 400


def test_uploads_and_mounted_folders_flow_into_org(dev, tmp_path):
    up = dev.post("/knowledge/upload", files=[("files", ("notes.md", b"# Q4 notes\n\nNothing yet.\n", "text/markdown")),
                                              ("files", ("photo.png", b"\x89PNG", "image/png"))],
                  data={"target_folder": "/org/uploads"})
    body = up.json()
    assert up.status_code == 200 and len(body["created"]) == 1 and body["skipped"] == ["photo.png (unsupported type)"]

    folder = tmp_path / "laptop-docs"
    (folder / "sub").mkdir(parents=True)
    (folder / "readme.md").write_text("# Readme\n\nThe team handbook.\n", encoding="utf-8")
    (folder / "sub" / "plan.md").write_text("# Plan\n\nShip Q4.\n", encoding="utf-8")
    (folder / "node_modules").mkdir()
    (folder / "node_modules" / "skip.md").write_text("# no\n", encoding="utf-8")
    m = dev.post("/knowledge/mounts", json={"name": "laptop", "host_path": str(folder)}).json()
    assert (m["name"], m["org_path"], m["files"], m["watching"]) == ("laptop", "/org/mnt/laptop", 2, True)
    (folder / "sub" / "plan.md").unlink()
    assert dev.post("/knowledge/mounts/laptop/sync").json()["files"] == 1
    assert dev.post("/knowledge/mounts", json={"name": "laptop", "host_path": str(folder)}).status_code == 409
    assert dev.post("/knowledge/mounts", json={"name": "nope", "host_path": str(folder / "missing")}).status_code == 400
    assert [x["name"] for x in dev.get("/knowledge/mounts").json()] == ["laptop"]
    assert dev.delete("/knowledge/mounts/laptop").status_code == 204
    assert dev.get("/knowledge/mounts").json() == []


def test_a_signed_in_person_pairs_their_phone_with_a_one_time_code(dev):
    priya = signin(dev, "priya@acme.example", "Priya")
    code = dev.post("/auth/pair", headers=priya).json()["code"]
    assert len(code) == 9 and code[4] == "-"
    phone = dev.post("/auth/pair/redeem", json={"code": code.lower().replace("-", " ")}).json()
    assert (phone["me"]["user"]["email"], phone["me"]["role"]) == ("priya@acme.example", "approver")
    assert phone["token"] != priya["Authorization"][7:]  # the phone has a session of its own
    assert dev.post("/auth/pair/redeem", json={"code": code}).status_code == 401  # one use
    assert dev.post("/auth/pair/redeem", json={"code": "ABCD-EFGH"}).status_code == 401
