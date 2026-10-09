"""FastAPI REST + WebSocket gateway. Route set MUST match shared/api/openapi.json (the mock gateway)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fnmatch import fnmatch
from typing import Any

from fastapi import Body, Depends, FastAPI, File, Form, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from kairos_contracts import CONTRACT_VERSION
from kairos_contracts.api import artifact_headers, artifact_media_type
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    TERMINAL_STATES,
    AgentManifest,
    AgentProcess,
    Approval,
    ApprovalResolution,
    ApprovalStatus,
    AuthConfig,
    AuthMode,
    Checkpoint,
    Connector,
    ConnectorConnect,
    ConnectorSyncResult,
    DevLogin,
    Event,
    EvidenceSet,
    GoogleLogin,
    GraphResult,
    IngestRequest,
    IngestResult,
    KnowledgeListing,
    KnowledgeMount,
    KnowledgeMountCreate,
    KnowledgeObject,
    Me,
    Member,
    MemberInvite,
    MemberUpdate,
    MemoryQuery,
    MemoryRecord,
    ModelInfo,
    Org,
    OrgCreate,
    OrgRole,
    PairCode,
    PairRedeem,
    PolicyDocument,
    Principal,
    PrincipalKind,
    PrivacyLevel,
    ProcessTreeNode,
    ResourceSnapshot,
    RunTimeline,
    SandboxInfo,
    SearchQuery,
    Session,
    SpawnRequest,
    SystemConfig,
    SystemStatus,
    Task,
    TaskCreate,
    TaskStatus,
    ToolSpec,
    ValidationReport,
)

from .. import __version__
from ..identity import Identity
from ..kernel import Kernel
from ..policy.engine import load_policy_documents
from .auth import Caller, me_of, need_factory, resolve
from .config import build_system_config
from .connectors import ConnectorService
from .files import FileService

log = logging.getLogger("kairos.kernel.gateway")


def user_principal(user: str, org: str, roles: str = "") -> Principal:
    return Principal(kind=PrincipalKind.USER, org_id=org, user_id=user, roles=[r for r in roles.split(",") if r],
                     capabilities=["*"], data_scopes=["/org/**"], max_privacy=PrivacyLevel.INTERNAL)


def create_app(kernel: Kernel) -> FastAPI:
    k = kernel
    svc = kernel.services
    identity = Identity(k.settings)
    files = FileService(k, identity.db)
    connectors = ConnectorService(k, identity)
    need = need_factory(identity)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await k.boot()
        for row in identity.db.all("SELECT DISTINCT org_id FROM vault"):
            await connectors.restore(row["org_id"])
        await files.start()
        try:
            yield
        finally:
            await files.stop()
            await k.shutdown()

    app = FastAPI(title="KAIROS Gateway API", version=CONTRACT_VERSION, lifespan=lifespan,
                  description="KAIROS kernel gateway (real implementation of shared/api/openapi.json).")
    app.state.kernel = kernel
    app.state.identity = identity
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(KairosError)
    async def _kairos_error(_: Request, exc: KairosError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_info().model_dump(mode="json"))

    Authed = Depends(need(None, org=False))  # signed in (any role, even before joining an org)
    Member_ = Depends(need(None))  # signed in and in an org

    # ------------------------------------------------------------------ system
    @app.get("/health", tags=["system"])
    async def health() -> dict[str, Any]:
        return {"ok": k.ready}

    @app.get("/system/status", response_model=SystemStatus, tags=["system"])
    async def system_status() -> SystemStatus:
        comps = k.components()
        return SystemStatus(ready=k.ready, version=__version__, contract_version=CONTRACT_VERSION,
                            uptime_s=round(time.monotonic() - k.started_at, 1), components=comps)

    @app.get("/system/resources", response_model=ResourceSnapshot, tags=["system"], dependencies=[Member_])
    async def system_resources() -> ResourceSnapshot:
        snap = await svc.probe.snapshot() if svc.probe else ResourceSnapshot(cpu_percent=0, ram_used_mb=0, ram_total_mb=0)
        sandboxes = await svc.sandbox.list() if svc.sandbox else []
        return snap.model_copy(update={
            "running_processes": sum(1 for p in k.procs.list() if p.state not in TERMINAL_STATES),
            "queued_tasks": k.tasks.queued(),
            "active_sandboxes": sum(1 for s in sandboxes if s.status.value == "running"),
            "tokens_last_minute": k.quotas.tokens_last_minute()})

    @app.get("/system/config", response_model=SystemConfig, tags=["system"], dependencies=[Depends(need("config.read"))])
    async def system_config() -> SystemConfig:
        cfg = await build_system_config(k)
        # Switches the Settings centre shows next to the firewall: how people sign in, whether the vault is encrypted.
        cfg.feature_flags.update({"google_sign_in": identity.mode == "google", "vault_encrypted": identity.vault.encrypted,
                                  "folder_mounts": True})
        return cfg

    @app.get("/models", response_model=list[ModelInfo], tags=["system"], dependencies=[Member_])
    async def list_models() -> list[ModelInfo]:
        return await svc.require("models").list_models()

    # ------------------------------------------------------------------ tasks
    @app.post("/tasks", response_model=Task, status_code=201, tags=["tasks"])
    async def create_task(body: TaskCreate, c: Caller = Depends(need("task.create"))) -> Task:
        return await k.tasks.create(body, c.principal)

    @app.get("/tasks", response_model=list[Task], tags=["tasks"], dependencies=[Member_])
    async def list_tasks(status: TaskStatus | None = None) -> list[Task]:
        return k.tasks.list(status)

    @app.get("/tasks/{task_id}", response_model=Task, tags=["tasks"], dependencies=[Member_])
    async def get_task(task_id: str) -> Task:
        return k.tasks.get(task_id)

    @app.post("/tasks/{task_id}/cancel", response_model=Task, tags=["tasks"], dependencies=[Depends(need("task.cancel"))])
    async def cancel_task(task_id: str) -> Task:
        return await k.tasks.cancel(task_id)

    @app.post("/tasks/{task_id}/resume", response_model=Task, tags=["tasks"], dependencies=[Depends(need("task.cancel"))])
    async def resume_task(task_id: str) -> Task:
        return await k.tasks.resume(task_id)

    @app.post("/tasks/{task_id}/checkpoint", response_model=list[Checkpoint], tags=["tasks"], dependencies=[Depends(need("task.cancel"))])
    async def checkpoint_task(task_id: str) -> list[Checkpoint]:
        k.tasks.get(task_id)
        return [await k.lifecycle.checkpoint(p.pid) for p in k.procs.list(task_id)
                if p.state not in TERMINAL_STATES and p.pid in k.lifecycle.contexts]

    @app.get("/tasks/{task_id}/artifacts", response_model=list[str], tags=["tasks"], dependencies=[Member_])
    async def task_artifacts(task_id: str) -> list[str]:
        k.tasks.get(task_id)
        return await svc.artifacts.list(task_id) if svc.artifacts else []

    @app.get("/tasks/{task_id}/artifacts/{name:path}", tags=["tasks"], response_class=Response, dependencies=[Member_],
             responses={200: {"content": {"application/octet-stream": {}}, "description": "the artifact bytes"}})
    async def task_artifact(task_id: str, name: str) -> Response:
        k.tasks.get(task_id)
        ref = f"artifact://{task_id}/{name}"
        if svc.artifacts is None:
            raise KairosError("ARTIFACT_NOT_FOUND", ref)
        data = await svc.artifacts.get(ref)  # the store rejects names that escape the task folder
        return Response(data, media_type=artifact_media_type(name), headers=artifact_headers(name))

    # ------------------------------------------------------------------ processes
    @app.get("/agents", response_model=list[AgentProcess], tags=["agents"], dependencies=[Member_])
    async def list_processes(task_id: str | None = None) -> list[AgentProcess]:
        return k.procs.list(task_id)

    @app.get("/agents/tree", response_model=list[ProcessTreeNode], tags=["agents"], dependencies=[Member_])
    async def process_tree(task_id: str | None = None) -> list[ProcessTreeNode]:
        return k.procs.tree(task_id)

    @app.post("/agents/spawn", response_model=AgentProcess, status_code=201, tags=["agents"], dependencies=[Depends(need("task.cancel"))])
    async def spawn(body: SpawnRequest) -> AgentProcess:
        return k.procs.get(await k.lifecycle.spawn(body))

    @app.get("/agents/{pid}", response_model=AgentProcess, tags=["agents"], dependencies=[Member_])
    async def get_process(pid: int) -> AgentProcess:
        return k.procs.get(pid)

    @app.post("/agents/{pid}/pause", response_model=AgentProcess, tags=["agents"], dependencies=[Depends(need("task.cancel"))])
    async def pause(pid: int) -> AgentProcess:
        await k.lifecycle.pause(pid)
        return k.procs.get(pid)

    @app.post("/agents/{pid}/resume", response_model=AgentProcess, tags=["agents"], dependencies=[Depends(need("task.cancel"))])
    async def resume(pid: int) -> AgentProcess:
        await k.lifecycle.resume(pid)
        return k.procs.get(pid)

    @app.post("/agents/{pid}/kill", response_model=AgentProcess, tags=["agents"], dependencies=[Depends(need("task.cancel"))])
    async def kill(pid: int) -> AgentProcess:
        await k.lifecycle.kill(pid, reason="killed by user")
        return k.procs.get(pid)

    @app.post("/agents/{pid}/checkpoint", response_model=Checkpoint, tags=["agents"], dependencies=[Depends(need("task.cancel"))])
    async def checkpoint_process(pid: int) -> Checkpoint:
        return await k.lifecycle.checkpoint(pid)

    # ------------------------------------------------------------------ registry
    @app.get("/registry/agents", response_model=list[AgentManifest], tags=["registry"], dependencies=[Member_])
    async def registry_agents() -> list[AgentManifest]:
        return await svc.require("agent_registry").list()

    @app.get("/registry/tools", response_model=list[ToolSpec], tags=["registry"], dependencies=[Member_])
    async def registry_tools() -> list[ToolSpec]:
        return await svc.require("tools").list_tools()

    # ------------------------------------------------------------------ knowledge (user principal)
    @app.get("/knowledge/search", response_model=EvidenceSet, tags=["knowledge"])
    async def knowledge_search(q: str, scope: list[str] = Query(default=["/org"]), top_k: int = 8,
                               c: Caller = Depends(need("knowledge.read"))) -> EvidenceSet:
        return await svc.require("knowledge").search(SearchQuery(text=q, scope=scope, top_k=top_k), c.principal)

    @app.get("/knowledge/tree", response_model=KnowledgeListing, tags=["knowledge"])
    async def knowledge_tree(path: str = "/org", c: Caller = Depends(need("knowledge.read"))) -> KnowledgeListing:
        return await svc.require("knowledge").list(path, c.principal)

    @app.get("/knowledge/object", response_model=KnowledgeObject, tags=["knowledge"])
    async def knowledge_object(path: str, c: Caller = Depends(need("knowledge.read"))) -> KnowledgeObject:
        return await svc.require("knowledge").read(path, c.principal)

    @app.get("/knowledge/graph", response_model=GraphResult, tags=["knowledge"])
    async def knowledge_graph(path: str, depth: int = 1, c: Caller = Depends(need("knowledge.read"))) -> GraphResult:
        return await svc.require("knowledge").traverse(path, c.principal, depth=depth)

    @app.post("/knowledge/ingest", response_model=IngestResult, tags=["knowledge"], dependencies=[Depends(need("knowledge.ingest"))])
    async def knowledge_ingest(body: IngestRequest) -> IngestResult:
        return await svc.require("knowledge").ingest(body)

    @app.post("/knowledge/reindex", tags=["knowledge"], dependencies=[Depends(need("knowledge.ingest"))])
    async def knowledge_reindex() -> dict[str, int]:
        return {"indexed": await svc.require("knowledge").reindex()}

    @app.post("/knowledge/validate", response_model=ValidationReport, tags=["knowledge"], dependencies=[Depends(need("knowledge.read"))])
    async def knowledge_validate() -> ValidationReport:
        return await svc.require("knowledge").validate()

    @app.get("/memory", response_model=list[MemoryRecord], tags=["knowledge"])
    async def memory(owner: str | None = None, task_id: str | None = None,
                     c: Caller = Depends(need("knowledge.read"))) -> list[MemoryRecord]:
        return await svc.require("memory").recall(MemoryQuery(text="", org_id=c.org_id, owner=owner, task_id=task_id,
                                                              include_stale=True, top_k=50))

    # ------------------------------------------------------------------ governance
    @app.get("/approvals", response_model=list[Approval], tags=["governance"], dependencies=[Member_])
    async def list_approvals(status: ApprovalStatus | None = None) -> list[Approval]:
        return k.approvals.list(status)

    @app.post("/approvals/{approval_id}/approve", response_model=Approval, tags=["governance"])
    async def approve(approval_id: str, body: ApprovalResolution = Body(default_factory=ApprovalResolution),
                      c: Caller = Depends(need("approval.resolve"))) -> Approval:
        return await k.approvals.resolve(approval_id, True, c.user_id, body.comment)

    @app.post("/approvals/{approval_id}/reject", response_model=Approval, tags=["governance"])
    async def reject(approval_id: str, body: ApprovalResolution = Body(default_factory=ApprovalResolution),
                     c: Caller = Depends(need("approval.resolve"))) -> Approval:
        return await k.approvals.resolve(approval_id, False, c.user_id, body.comment)

    @app.get("/audit/{task_id}", response_model=RunTimeline, tags=["governance"], dependencies=[Member_])
    async def audit(task_id: str) -> RunTimeline:
        k.tasks.get(task_id)
        return await k.audit.timeline(task_id)

    @app.get("/policies", response_model=list[PolicyDocument], tags=["governance"], dependencies=[Member_])
    async def policies() -> list[PolicyDocument]:
        documents = getattr(k.policy, "documents", None)
        return documents() if documents else load_policy_documents(k.settings.policies_dir)

    @app.get("/sandboxes", response_model=list[SandboxInfo], tags=["execution"], dependencies=[Member_])
    async def sandboxes(task_id: str | None = None) -> list[SandboxInfo]:
        return await svc.sandbox.list(task_id) if svc.sandbox else []

    # ------------------------------------------------------------------ identity
    @app.get("/auth/config", response_model=AuthConfig, tags=["identity"])
    async def auth_config() -> AuthConfig:
        return identity.config()

    @app.post("/auth/dev", response_model=Session, tags=["identity"])
    async def auth_dev(body: DevLogin) -> Session:
        return identity.dev_login(body)

    @app.post("/auth/google", response_model=Session, tags=["identity"])
    async def auth_google(body: GoogleLogin) -> Session:
        return identity.google_login(body)

    @app.get("/auth/me", response_model=Me, tags=["identity"])
    async def auth_me(c: Caller = Authed) -> Me:
        return me_of(identity, c)

    @app.post("/auth/pair", response_model=PairCode, tags=["identity"])
    async def auth_pair(c: Caller = Member_) -> PairCode:
        return identity.pair(c.user_id, c.org_id)

    @app.post("/auth/pair/redeem", response_model=Session, tags=["identity"])
    async def auth_pair_redeem(body: PairRedeem) -> Session:
        return identity.redeem(body)

    @app.post("/auth/logout", status_code=204, tags=["identity"])
    async def auth_logout(c: Caller = Authed) -> None:
        if c.token:
            identity.revoke(c.token)

    @app.post("/orgs", response_model=Org, status_code=201, tags=["identity"])
    async def create_org(body: OrgCreate, c: Caller = Authed) -> Org:
        if c.token is None and identity.mode == AuthMode.DEV:
            identity._upsert_user(f"{c.user_id}@local", c.user_id)  # a header caller becomes a real user to own the org
            user_id = identity.db.one("SELECT user_id FROM users WHERE email=?", (f"{c.user_id}@local",))["user_id"]
        else:
            user_id = c.user_id
        return identity.create_org(user_id, body)

    @app.get("/orgs/me", response_model=Org, tags=["identity"])
    async def org_me(c: Caller = Member_) -> Org:
        org = identity.org(c.org_id)
        if org is None:
            raise KairosError("NOT_FOUND", f"org {c.org_id}")
        return org

    def _same_org(c: Caller, org_id: str) -> None:
        if org_id != c.org_id:
            raise KairosError("PERMISSION_DENIED", "that is not your organization")

    @app.get("/orgs/{org_id}/members", response_model=list[Member], tags=["identity"])
    async def org_members(org_id: str, c: Caller = Member_) -> list[Member]:
        _same_org(c, org_id)
        return identity.members(org_id)

    @app.post("/orgs/{org_id}/members", response_model=Member, status_code=201, tags=["identity"])
    async def invite_member(org_id: str, body: MemberInvite, c: Caller = Depends(need("members.manage"))) -> Member:
        _same_org(c, org_id)
        return identity.invite(org_id, body, c.user_id, c.role)

    @app.patch("/orgs/{org_id}/members/{member}", response_model=Member, tags=["identity"])
    async def update_member(org_id: str, member: str, body: MemberUpdate, c: Caller = Depends(need("members.manage"))) -> Member:
        _same_org(c, org_id)
        return identity.update_member(org_id, member, body, c.role)

    @app.delete("/orgs/{org_id}/members/{member}", status_code=204, tags=["identity"])
    async def remove_member(org_id: str, member: str, c: Caller = Depends(need("members.manage"))) -> None:
        _same_org(c, org_id)
        identity.remove_member(org_id, member)

    @app.get("/orgs/{org_id}/roles", response_model=list[OrgRole], tags=["identity"])
    async def org_roles(org_id: str, c: Caller = Member_) -> list[OrgRole]:
        _same_org(c, org_id)
        return identity.roles

    # ------------------------------------------------------------------ connectors
    @app.get("/connectors", response_model=list[Connector], tags=["connectors"])
    async def list_connectors(c: Caller = Member_) -> list[Connector]:
        return connectors.list(c.org_id)

    @app.post("/connectors/{connector_id}/connect", response_model=Connector, tags=["connectors"])
    async def connect_connector(connector_id: str, body: ConnectorConnect = Body(default_factory=ConnectorConnect),
                                c: Caller = Depends(need("connectors.manage"))) -> Connector:
        return await connectors.connect(c.org_id, connector_id, body, c.user_id)

    @app.delete("/connectors/{connector_id}", status_code=204, tags=["connectors"])
    async def disconnect_connector(connector_id: str, c: Caller = Depends(need("connectors.manage"))) -> None:
        await connectors.disconnect(c.org_id, connector_id)

    @app.post("/connectors/{connector_id}/sync", response_model=ConnectorSyncResult, tags=["connectors"])
    async def sync_connector(connector_id: str, c: Caller = Depends(need("connectors.manage"))) -> ConnectorSyncResult:
        return await connectors.sync(c.org_id, connector_id)

    # ------------------------------------------------------------------ files from outside /org
    @app.post("/knowledge/upload", response_model=IngestResult, tags=["knowledge"])
    async def knowledge_upload(files_: list[UploadFile] = File(..., alias="files"), target_folder: str = Form("/org/uploads"),
                               privacy: str | None = Form(None), c: Caller = Depends(need("knowledge.ingest"))) -> IngestResult:
        batch = [(f.filename or "upload", await f.read()) for f in files_]
        return await files.upload(batch, target_folder, privacy, c.user_id)

    @app.get("/knowledge/mounts", response_model=list[KnowledgeMount], tags=["knowledge"], dependencies=[Depends(need("knowledge.read"))])
    async def list_mounts() -> list[KnowledgeMount]:
        return files.list()

    @app.post("/knowledge/mounts", response_model=KnowledgeMount, status_code=201, tags=["knowledge"])
    async def add_mount(body: KnowledgeMountCreate, c: Caller = Depends(need("knowledge.ingest"))) -> KnowledgeMount:
        return await files.add(body, c.user_id)

    @app.post("/knowledge/mounts/{name}/sync", response_model=KnowledgeMount, tags=["knowledge"], dependencies=[Depends(need("knowledge.ingest"))])
    async def sync_mount(name: str) -> KnowledgeMount:
        return await files.sync(name)

    @app.delete("/knowledge/mounts/{name}", status_code=204, tags=["knowledge"], dependencies=[Depends(need("knowledge.ingest"))])
    async def remove_mount(name: str) -> None:
        await files.remove(name)

    # ------------------------------------------------------------------ events
    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket, task_id: str | None = None, types: str = "*", token: str | None = None) -> None:
        """Replays the task's history first (so late subscribers see the whole run), then streams live events."""
        try:
            resolve(identity, None, ws.headers.get("x-kairos-user", "alice"), ws.headers.get("x-kairos-org", "acme"), "", token)
        except KairosError:
            await ws.close(code=4401)
            return
        await ws.accept()
        patterns = [t.strip() for t in types.split(",") if t.strip()] or ["*"]
        stream = k.bus.stream("*", task_id)  # register before snapshotting history: nothing can fall in between

        def wanted(ev: Event) -> bool:
            return any(fnmatch(ev.type, p) for p in patterns)

        async def watch_disconnect() -> None:
            with contextlib.suppress(WebSocketDisconnect):
                while True:
                    await ws.receive_text()

        closed = asyncio.create_task(watch_disconnect())
        try:
            replayed = set()
            for ev in list(k.history.get(task_id, ())) if task_id else []:
                replayed.add(ev.event_id)
                if wanted(ev):
                    await ws.send_text(ev.model_dump_json())
            while not closed.done():
                nxt = asyncio.ensure_future(stream.__anext__())
                done, _ = await asyncio.wait({nxt, closed}, return_when=asyncio.FIRST_COMPLETED)
                if nxt not in done:
                    nxt.cancel()
                    break
                ev = nxt.result()
                if ev.event_id not in replayed and wanted(ev):
                    await ws.send_text(ev.model_dump_json())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            closed.cancel()
            close = getattr(stream, "close", None)
            if close:
                close()

    return app
