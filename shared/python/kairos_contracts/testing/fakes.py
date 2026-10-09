"""Working in-memory fakes of every interface.

Purpose: each person develops against the OTHER people's fakes from day 1, so nobody is blocked.
The fakes are intentionally simple but behave correctly w.r.t. the contract (scope filtering,
policy decisions, events, errors). They also pass kairos_contracts.testing.contracts — the same
suite the real implementations must pass.

Do not put production logic here. If a fake needs a new behaviour, that is a contract change.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import posixpath
import re
import sqlite3
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

from ..errors import KairosError
from ..schema import (
    NARRATION_EVENTS,
    A2AMessage,
    AgentManifest,
    AgentResult,
    AgentResultStatus,
    AgentThought,
    Approval,
    ApprovalStatus,
    AuditEntry,
    AuditKind,
    BrowserPage,
    ChangeKind,
    ChatMessage,
    Decision,
    EmbedRequest,
    EmbedResponse,
    Event,
    EventType,
    EvidenceSet,
    ExecRequest,
    ExecResult,
    GpuStatus,
    GraphEdge,
    GraphResult,
    IngestRequest,
    IngestResult,
    IngestSourceType,
    InvalidationReport,
    KnowledgeChange,
    KnowledgeEntry,
    KnowledgeListing,
    KnowledgeObject,
    ManifestCapabilities,
    ManifestRuntime,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    ModelInfo,
    ModelRequest,
    ModelResponse,
    NarrationPayload,
    OKFDraft,
    OKFFrontmatter,
    PolicyDecision,
    Principal,
    PrincipalKind,
    PrivacyLevel,
    Provenance,
    ResourceSnapshot,
    Risk,
    Role,
    RoutingDecision,
    RunTimeline,
    SandboxInfo,
    SandboxSpec,
    SandboxStatus,
    SearchHit,
    SearchMode,
    SearchQuery,
    SpawnRequest,
    StreamChunk,
    SyscallRequest,
    SyscallResult,
    SyscallStatus,
    TimelineStats,
    TokenUsage,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolResultStatus,
    ToolSpec,
    ToolTransport,
    TrustLevel,
    UserPermissions,
    ValidationIssue,
    ValidationReport,
    VerificationCheck,
    VerificationResult,
    WorkingSet,
    WorkingSetItem,
)
from ..schema.common import new_id
from ..util import estimate_tokens, has_capability, okf_file_to_org_path, path_allowed, privacy_allows
from ..wiring import REPO_ROOT
from . import demo_data

log = logging.getLogger("kairos.fakes")

FIXTURES_DIR = REPO_ROOT / "shared" / "fixtures"
FIXTURE_OKF_DIR = FIXTURES_DIR / "okf"
FIXTURE_MANIFESTS_DIR = FIXTURES_DIR / "manifests"


def _terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


def system_principal(org_id: str = "acme") -> Principal:
    return Principal(kind=PrincipalKind.SYSTEM, org_id=org_id, user_id="system", capabilities=["*"],
                     data_scopes=["/org/**"], max_privacy=PrivacyLevel.RESTRICTED)


def user_principal(user_id: str = "alice", org_id: str = "acme", **kw: Any) -> Principal:
    return Principal(kind=PrincipalKind.USER, org_id=org_id, user_id=user_id, **kw)


# ============================================================================ P1: events / policy / audit

class _Subscription:
    def __init__(self, cancel: Callable[[], None]):
        self._cancel = cancel

    def unsubscribe(self) -> None:
        self._cancel()


class _EventStream:
    """Registers eagerly (on creation), so events published before the first `await` are not lost."""

    def __init__(self, bus: InMemoryEventBus, pattern: str, task_id: str | None):
        self._bus, self._q = bus, asyncio.Queue()
        self._entry = (pattern, task_id, self._q)
        bus._streams.append(self._entry)

    def __aiter__(self) -> _EventStream:
        return self

    async def __anext__(self) -> Event:
        return await self._q.get()

    def close(self) -> None:
        if self._entry in self._bus._streams:
            self._bus._streams.remove(self._entry)


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subs: list[tuple[str, Callable[[Event], Awaitable[None]]]] = []
        self._streams: list[tuple[str, str | None, asyncio.Queue]] = []
        self.history: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.history.append(event)
        for pattern, handler in list(self._subs):
            if fnmatch(event.type, pattern):
                try:
                    await handler(event)
                except Exception:  # a broken subscriber must never break the publisher
                    log.exception("event handler failed for %s", event.type)
        for pattern, task_id, q in list(self._streams):
            if fnmatch(event.type, pattern) and (task_id is None or event.task_id == task_id):
                q.put_nowait(event)

    def subscribe(self, pattern: str, handler: Callable[[Event], Awaitable[None]]) -> _Subscription:
        entry = (pattern, handler)
        self._subs.append(entry)
        return _Subscription(lambda: entry in self._subs and self._subs.remove(entry))

    def stream(self, pattern: str = "*", task_id: str | None = None) -> AsyncIterator[Event]:
        return _EventStream(self, pattern, task_id)

    def of_type(self, type_: str) -> list[Event]:
        return [e for e in self.history if fnmatch(e.type, type_)]


APPROVAL_VERBS = {"write", "send", "delete", "exec", "create", "update", "upload", "click", "type"}


class FakePolicyEngine:
    """capability not granted -> DENY; mutating verb or high risk -> REQUIRES_APPROVAL; else ALLOW."""

    policy_id = "fake-default"

    async def evaluate(self, request: SyscallRequest, principal: Principal) -> PolicyDecision:
        if not has_capability(request.capability, principal.capabilities):
            return PolicyDecision(decision=Decision.DENY, policy=self.policy_id,
                                  reason=f"capability {request.capability} not granted to {principal.agent or principal.user_id}",
                                  matched_rules=["capability-check"])
        verb = request.capability.split(".")[-1]
        if request.risk in (Risk.HIGH, Risk.CRITICAL) or verb in APPROVAL_VERBS:
            return PolicyDecision(decision=Decision.REQUIRES_APPROVAL, policy=self.policy_id,
                                  reason=f"{verb} operation on external system", approval_id=new_id("APR"),
                                  matched_rules=["mutating-verb-requires-approval"])
        return PolicyDecision(decision=Decision.ALLOW, policy=self.policy_id, reason="read-only capability granted",
                              matched_rules=["capability-check"])

    async def reload(self) -> None:
        return None


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._entries: dict[str, list[AuditEntry]] = defaultdict(list)
        self._goals: dict[str, str] = {}

    async def append(self, entry: AuditEntry) -> AuditEntry:
        entries = self._entries[entry.task_id]
        stored = entry.model_copy(update={"seq": len(entries) + 1})
        entries.append(stored)
        if entry.kind == AuditKind.TASK and "goal" in entry.data:
            self._goals[entry.task_id] = entry.data["goal"]
        return stored

    async def timeline(self, task_id: str) -> RunTimeline:
        entries = self._entries.get(task_id)
        if entries is None:
            raise KairosError("TASK_NOT_FOUND", f"no audit entries for {task_id}")
        k = [e.kind for e in entries]
        stats = TimelineStats(
            agents=k.count(AuditKind.SPAWN),
            models=sorted({e.data.get("model") for e in entries if e.kind == AuditKind.MODEL and e.data.get("model")}),
            knowledge_objects=len({r for e in entries if e.kind == AuditKind.KNOWLEDGE for r in e.refs}),
            ipc_messages=k.count(AuditKind.IPC),
            tool_calls=k.count(AuditKind.TOOL),
            privileged_syscalls=sum(1 for e in entries if e.kind == AuditKind.POLICY and e.data.get("decision") != "ALLOW"),
            approvals=k.count(AuditKind.APPROVAL),
            rollbacks=k.count(AuditKind.ROLLBACK),
        )
        return RunTimeline(task_id=task_id, goal=self._goals.get(task_id, ""), entries=list(entries), stats=stats)


# ============================================================================ P1: artifacts / sandbox / tools  (+ P4: browser driver)

class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def put(self, task_id: str, name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        ref = f"artifact://{task_id}/{name}"
        self._data[ref] = data
        return ref

    async def get(self, ref: str) -> bytes:
        if ref not in self._data:
            raise KairosError("ARTIFACT_NOT_FOUND", ref)
        return self._data[ref]

    async def exists(self, ref: str) -> bool:
        return ref in self._data

    async def list(self, task_id: str) -> list[str]:
        return sorted(r for r in self._data if r.startswith(f"artifact://{task_id}/"))


class FakeSandboxManager:
    def __init__(self) -> None:
        self.sandboxes: dict[str, SandboxInfo] = {}
        self.exec_log: list[tuple[str, ExecRequest]] = []

    async def provision(self, spec: SandboxSpec) -> SandboxInfo:
        info = SandboxInfo(sandbox_id=new_id("SB"), status=SandboxStatus.RUNNING, spec=spec)
        self.sandboxes[info.sandbox_id] = info
        return info

    async def exec(self, sandbox_id: str, request: ExecRequest) -> ExecResult:
        self._get(sandbox_id)
        self.exec_log.append((sandbox_id, request))
        return ExecResult(exit_code=0, stdout=f"[fake-sandbox] {' '.join(request.command)}\n")

    async def screenshot(self, sandbox_id: str) -> bytes | None:
        self._get(sandbox_id)
        return None

    async def destroy(self, sandbox_id: str) -> None:
        info = self._get(sandbox_id)
        self.sandboxes[sandbox_id] = info.model_copy(update={"status": SandboxStatus.DESTROYED})

    async def list(self, task_id: str | None = None) -> list[SandboxInfo]:
        return [s for s in self.sandboxes.values() if task_id is None or s.spec.task_id == task_id]

    def _get(self, sandbox_id: str) -> SandboxInfo:
        if sandbox_id not in self.sandboxes:
            raise KairosError("NOT_FOUND", f"sandbox {sandbox_id}")
        return self.sandboxes[sandbox_id]


FAKE_TOOL_SPECS = [
    ToolSpec(name="jira", description="Issue tracker (mock)", transport=ToolTransport.NATIVE, operations=[
        ToolOperation(name="get_issue", capability="jira.read", description="Read an issue by key",
                      input_schema={"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}),
        ToolOperation(name="search_issues", capability="jira.read", description="Search issues by project",
                      input_schema={"type": "object", "properties": {"project": {"type": "string"}}}),
        ToolOperation(name="update_issue", capability="jira.write", description="Update fields / add a comment",
                      input_schema={"type": "object", "required": ["key"], "properties": {
                          "key": {"type": "string"}, "fields": {"type": "object"}, "comment": {"type": "string"}}},
                      risk=Risk.MEDIUM, reversible=True),
    ]),
    ToolSpec(name="fs", description="Workspace file operations", transport=ToolTransport.NATIVE, operations=[
        ToolOperation(name="read_file", capability="fs.read", description="Read a workspace file",
                      input_schema={"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}),
        ToolOperation(name="write_file", capability="fs.write", description="Write a workspace file",
                      input_schema={"type": "object", "required": ["path", "content"], "properties": {
                          "path": {"type": "string"}, "content": {"type": "string"}}}, risk=Risk.LOW, reversible=True),
    ]),
    ToolSpec(name="db", description="Demo company database (read-only queries; writes need approval)",
             transport=ToolTransport.NATIVE, operations=[
        ToolOperation(name="schema", capability="db.query", description="Tables, columns and notes of the database",
                      input_schema={"type": "object", "properties": {}}),
        ToolOperation(name="query", capability="db.query", description="Run one read-only SELECT (LIMIT <= 200)",
                      input_schema={"type": "object", "required": ["sql"], "properties": {"sql": {"type": "string"}}}),
        ToolOperation(name="write", capability="db.write", description="Run one INSERT/UPDATE/DELETE with parameters",
                      input_schema={"type": "object", "required": ["sql"], "properties": {
                          "sql": {"type": "string"}, "params": {"type": "array"}}}, risk=Risk.HIGH),
    ]),
    ToolSpec(name="browser", description="Isolated browser (Playwright)", transport=ToolTransport.BROWSER, operations=[
        ToolOperation(name="open", capability="browser.open", description="Open a URL and return title + text",
                      input_schema={"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}},
                      requires_sandbox=True),
    ]),
]


class FakeToolExecutor:
    """Mock Jira + in-memory fs + fake browser + the demo database in SQLite. Reversible where the real one will be."""

    def __init__(self) -> None:
        self.issues: dict[str, dict[str, Any]] = {
            "APOLLO-12": {"key": "APOLLO-12", "summary": "Payments DB migration", "status": "In Progress",
                          "labels": ["migration"], "comments": []},
            "APOLLO-31": {"key": "APOLLO-31", "summary": "Vendor SDK upgrade", "status": "Blocked",
                          "labels": ["vendor"], "comments": []},
        }
        self.files: dict[str, str] = {}
        self.db = demo_data.sqlite_db()
        self.invocations: list[ToolInvocation] = []
        self._undo: dict[str, tuple[str, Any]] = {}

    async def list_tools(self) -> list[ToolSpec]:
        return list(FAKE_TOOL_SPECS)

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        a, op = invocation.arguments, f"{invocation.tool}.{invocation.operation}"
        try:
            if invocation.dry_run:
                return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.SUCCESS, output={"dry_run": True})
            if op == "jira.get_issue":
                out = dict(self._issue(a["key"]))
            elif op == "jira.search_issues":
                out = {"issues": [i for k, i in self.issues.items() if k.startswith(a.get("project", ""))]}
            elif op == "jira.update_issue":
                issue = self._issue(a["key"])
                token = new_id("RB")
                self._undo[token] = ("jira", json.loads(json.dumps(issue)))
                issue.update(a.get("fields", {}))
                if a.get("comment"):
                    issue["comments"].append(a["comment"])
                return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.SUCCESS,
                                  output=dict(issue), rollback_token=token)
            elif op == "fs.read_file":
                if a["path"] not in self.files:
                    raise KairosError("NOT_FOUND", a["path"])
                out = {"content": self.files[a["path"]]}
            elif op == "fs.write_file":
                token = new_id("RB")
                self._undo[token] = ("fs", (a["path"], self.files.get(a["path"])))
                self.files[a["path"]] = a["content"]
                return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.SUCCESS,
                                  output={"path": a["path"], "bytes": len(a["content"])}, rollback_token=token)
            elif op == "db.schema":
                out = demo_data.schema_doc()
            elif op == "db.query":
                cur = self.db.execute(a["sql"])
                out = {"columns": [d[0] for d in cur.description or []], "rows": [list(r) for r in cur.fetchall()]}
            elif op == "db.write":
                cur = self.db.execute(a["sql"], list(a.get("params") or []))
                self.db.commit()
                out = {"rowcount": cur.rowcount}
            elif op == "browser.open":
                out = {"url": a["url"], "title": f"Fake page for {a['url']}", "text": "lorem ipsum"}
            else:
                raise KairosError("NOT_FOUND", f"unknown tool operation {op}")
            return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.SUCCESS, output=out)
        except KairosError as e:
            return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.ERROR, error=e.to_info())
        except sqlite3.Error as e:  # a bad statement is the caller's error, reported like the real backend's
            return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.ERROR,
                              error=KairosError("BAD_REQUEST", f"SQL error: {e}").to_info())

    async def verify(self, invocation: ToolInvocation, result: ToolResult) -> VerificationResult:
        checks: list[VerificationCheck] = [VerificationCheck(name="status_success", passed=result.status == ToolResultStatus.SUCCESS)]
        if f"{invocation.tool}.{invocation.operation}" == "jira.update_issue" and result.status == ToolResultStatus.SUCCESS:
            issue = self.issues.get(invocation.arguments["key"], {})
            for k, v in invocation.arguments.get("fields", {}).items():
                checks.append(VerificationCheck(name=f"field:{k}", passed=issue.get(k) == v, detail=str(issue.get(k))))
        return VerificationResult(invocation_id=invocation.invocation_id, passed=all(c.passed for c in checks), checks=checks)

    async def rollback(self, invocation: ToolInvocation, result: ToolResult) -> bool:
        undo = self._undo.pop(result.rollback_token or "", None)
        if undo is None:
            return False
        kind, state = undo
        if kind == "jira":
            self.issues[state["key"]] = state
        else:
            path, old = state
            if old is None:
                self.files.pop(path, None)
            else:
                self.files[path] = old
        return True

    def _issue(self, key: str) -> dict[str, Any]:
        if key not in self.issues:
            raise KairosError("NOT_FOUND", f"issue {key}")
        return self.issues[key]


# ============================================================================ P3: models / agents

def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for t in _terms(text):
        vec[int(hashlib.md5(t.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _schema_skeleton(schema: dict[str, Any], root: dict[str, Any] | None = None) -> Any:
    root = root or schema
    if "$ref" in schema:
        return _schema_skeleton(root.get("$defs", {}).get(schema["$ref"].split("/")[-1], {}), root)
    if "default" in schema:
        return schema["default"]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {k: _schema_skeleton(v, root) for k, v in schema.get("properties", {}).items()}
    return {"string": "", "integer": 0, "number": 0.0, "boolean": False, "array": []}.get(t)  # type: ignore[arg-type]


class FakeModelRouter:
    """Deterministic. `responses` maps a case-insensitive substring of the prompt to a reply (str or dict)."""

    name = "fake"

    def __init__(self, responses: dict[str, str | dict[str, Any]] | None = None, dim: int = 64) -> None:
        self.responses = responses or {}
        self.dim = dim
        self.calls: list[ModelRequest] = []

    async def route(self, request: ModelRequest) -> RoutingDecision:
        return RoutingDecision(model="fake-chat", provider="fake", local=True, reason="fake router always local")

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        prompt = "\n".join(m.content for m in request.messages)
        reply = next((r for k, r in self.responses.items() if k.lower() in prompt.lower()), None)
        parsed: dict[str, Any] | None = None
        if isinstance(reply, dict):
            parsed, content = reply, json.dumps(reply)
        elif isinstance(reply, str):
            content = reply
        elif request.json_schema:
            parsed = _schema_skeleton(request.json_schema)
            content = json.dumps(parsed)
        else:
            last_user = next((m.content for m in reversed(request.messages) if m.role == Role.USER), "")
            content = f"[fake-model] {last_user[:200]}"
        return ModelResponse(model="fake-chat", provider="fake", content=content, parsed=parsed,
                             usage=TokenUsage(prompt=estimate_tokens(prompt), completion=estimate_tokens(content)))

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        resp = await self.generate(request)
        for word in resp.content.split(" "):
            yield StreamChunk(delta=word + " ")
        yield StreamChunk(delta="", done=True, usage=resp.usage)

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        return EmbedResponse(model="fake-embed", dim=self.dim, vectors=[_hash_embed(t, self.dim) for t in request.texts])

    async def embedding_dim(self) -> int:
        return self.dim

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-chat", provider="fake", capabilities=["chat", "json"]),
                ModelInfo(name="fake-embed", provider="fake", capabilities=["embed"], embedding_dim=self.dim)]


def load_manifests(directory: Path) -> list[AgentManifest]:
    return [AgentManifest.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
            for p in sorted(directory.glob("*.yaml"))]


class FakeAgentRegistry:
    def __init__(self, manifests: list[AgentManifest] | None = None, directory: Path | None = None) -> None:
        items = manifests if manifests is not None else load_manifests(directory or FIXTURE_MANIFESTS_DIR)
        self._by_name = {m.name: m for m in items}

    async def list(self) -> list[AgentManifest]:
        return list(self._by_name.values())

    async def get(self, name: str) -> AgentManifest:
        if name not in self._by_name:
            raise KairosError("AGENT_NOT_FOUND", name)
        return self._by_name[name]

    async def match(self, goal: str, limit: int = 3) -> list[AgentManifest]:
        g = set(_terms(goal))
        scored = [(len(g & set(_terms(" ".join(m.handles) + " " + m.description))), m) for m in self._by_name.values()]
        return [m for s, m in sorted(scored, key=lambda x: -x[0]) if s > 0][:limit]


class FakeAgentRuntime:
    """Exercises the whole AgentContext surface so the kernel (P1) can be built before real agents exist.

    planner-like manifests (capabilities.agents non-empty) spawn one child per allowed agent and wait;
    others search, call the LLM, and — if they hold a *.write tool capability — issue one syscall.
    """

    async def run(self, manifest: AgentManifest, goal: str, ctx: Any) -> AgentResult:
        await ctx.log(f"{manifest.name} starting: {goal}")
        evidence = await ctx.search(SearchQuery(text=goal, top_k=3))
        resp = await ctx.llm(ModelRequest(messages=[ChatMessage(role=Role.USER, content=goal)]))
        actions: list[SyscallRequest] = []
        output: dict[str, Any] = {"answer": resp.content}
        if manifest.capabilities.agents:
            pids = [await ctx.spawn(a, f"{a}: {goal}") for a in manifest.capabilities.agents]
            output["children"] = [(await ctx.wait(p)).model_dump(mode="json") for p in pids]
        writes = [c for c in manifest.capabilities.tools if c.endswith(".write")]
        if writes:
            req = SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability=writes[0],
                                 tool=writes[0].split(".")[0], operation="update_issue", resource="APOLLO-12",
                                 arguments={"key": "APOLLO-12", "comment": f"KAIROS: {goal[:80]}"},
                                 risk=Risk.MEDIUM, justification="fake runtime demo action",
                                 evidence=[h.path for h in evidence.hits])
            res = await ctx.syscall(req)
            actions.append(req)
            output["syscall_status"] = res.status.value
        return AgentResult(pid=ctx.pid, agent=manifest.name, status=AgentResultStatus.COMPLETED,
                           summary=f"{manifest.name} finished: {resp.content[:120]}", output=output,
                           evidence=[h.path for h in evidence.hits], actions=actions)

    async def restore(self, manifest: AgentManifest, goal: str, ctx: Any, state: dict[str, Any]) -> AgentResult:
        return await self.run(manifest, goal, ctx)


# ============================================================================ P2: knowledge / firewall / memory

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)\)")
_INSTRUCTION_PATTERNS = [
    r"\bignore (all|any|your|the|previous)\b.*\b(instructions?|polic(y|ies)|rules)\b",
    r"\bdisregard\b.*\b(instructions?|polic(y|ies))\b",
    r"\byou (must|should) now\b",
    r"\b(delete|drop|wipe)\b.*\b(database|table|repository|files)\b",
    r"\b(send|email|upload|exfiltrate)\b.*\b(credentials?|passwords?|secrets?|api keys?)\b",
    r"\bsystem prompt\b",
]


def parse_okf(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        return yaml.safe_load(fm) or {}, body.lstrip("\n")
    return {}, text


class FakeContextFirewall:
    async def screen(self, hits: list[SearchHit]) -> list[SearchHit]:
        out = []
        for h in hits:
            text = f"{h.snippet}\n{h.body or ''}"
            flagged = any(re.search(p, text, re.IGNORECASE) for p in _INSTRUCTION_PATTERNS)
            out.append(h.model_copy(update={"firewall_flags": sorted(set(h.firewall_flags) | {"instruction_like"})}) if flagged else h)
        return out


class FakeKnowledgeService:
    """Loads an OKF bundle from disk into memory. Lexical = term overlap, semantic = hashed embeddings."""

    def __init__(self, okf_dir: Path | None = None, models: Any = None, firewall: Any = None, event_bus: Any = None) -> None:
        self.okf_dir = okf_dir or FIXTURE_OKF_DIR
        self.models, self.firewall, self.bus = models, firewall, event_bus
        self.objects: dict[str, KnowledgeObject] = {}
        self._vectors: dict[str, list[float]] = {}
        self._load()

    # --- loading
    def _load(self) -> None:
        self.objects.clear()
        for f in sorted(self.okf_dir.rglob("*.md")):
            rel = f.relative_to(self.okf_dir).as_posix()
            if rel.lower() == "readme.md":
                continue
            self.objects[okf_file_to_org_path(rel)] = self._to_object(rel, f.read_text(encoding="utf-8"))
        self._vectors.clear()

    def _to_object(self, rel: str, text: str) -> KnowledgeObject:
        fm_raw, body = parse_okf(text)
        fm_raw.setdefault("type", "note")
        fm_raw.setdefault("title", rel)
        fm = OKFFrontmatter.model_validate(fm_raw)
        links = []
        for target in _LINK_RE.findall(body) + [r for r in fm.related if r.endswith(".md")]:
            links.append(okf_file_to_org_path(posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))))
        links += [r for r in fm.related if r.startswith("/org")]
        return KnowledgeObject(
            path=okf_file_to_org_path(rel), okf_file=rel, frontmatter=fm, body=body, links=sorted(set(links)),
            provenance=Provenance(source=fm.source or "okf", source_ref=rel, source_version=fm.source_version,
                                  created_at=fm.created_at, updated_at=fm.updated_at, author=fm.author,
                                  generator=fm.generator, verification_status=fm.verification_status, trust=fm.trust),
            content_hash=hashlib.sha256(text.encode()).hexdigest()[:16])

    # --- access control
    def _visible(self, obj: KnowledgeObject, p: Principal) -> bool:
        return path_allowed(obj.path, p.data_scopes) and privacy_allows(obj.frontmatter.privacy, p.max_privacy)

    def _get(self, path: str, p: Principal) -> KnowledgeObject:
        path = path.rstrip("/") or "/org"
        obj = self.objects.get(path)
        if obj is None:
            raise KairosError("KNOWLEDGE_NOT_FOUND", path)
        if not self._visible(obj, p):
            raise KairosError("KNOWLEDGE_FORBIDDEN", path)
        return obj

    # --- KnowledgeService
    async def read(self, path: str, principal: Principal) -> KnowledgeObject:
        return self._get(path, principal)

    async def list(self, path: str, principal: Principal) -> KnowledgeListing:
        base = path.rstrip("/") or "/org"
        children: dict[str, bool] = {}
        for p in self.objects:
            if p.startswith(base + "/"):
                seg = p[len(base) + 1:].split("/")[0]
                child = f"{base}/{seg}"
                children[child] = children.get(child, False) or p != child
        if not children and base not in self.objects:
            raise KairosError("KNOWLEDGE_NOT_FOUND", base)
        entries = []
        for child, is_dir in sorted(children.items()):
            obj = self.objects.get(child)
            if obj and not self._visible(obj, principal):
                continue
            if not obj and not path_allowed(child, principal.data_scopes) and not any(
                    g.startswith(child + "/") for g in principal.data_scopes):
                continue
            entries.append(KnowledgeEntry(path=child, title=obj.frontmatter.title if obj else child.rsplit("/", 1)[-1],
                                          type=obj.frontmatter.type if obj else "index", is_dir=is_dir,
                                          privacy=obj.frontmatter.privacy if obj else PrivacyLevel.INTERNAL))
        return KnowledgeListing(path=base, entries=entries)

    async def search(self, query: SearchQuery, principal: Principal) -> EvidenceSet:
        q_terms = set(_terms(query.text))
        candidates, filtered = [], 0
        min_trust_rank = [TrustLevel.UNTRUSTED, TrustLevel.UNVERIFIED, TrustLevel.TRUSTED, TrustLevel.VERIFIED].index(query.min_trust)
        for obj in self.objects.values():
            if not any(obj.path == s.rstrip("/") or obj.path.startswith(s.rstrip("/") + "/") for s in query.scope):
                continue
            fm = obj.frontmatter
            if (query.types and fm.type not in query.types) or (query.tags and not set(query.tags) & set(fm.tags)):
                continue
            if [TrustLevel.UNTRUSTED, TrustLevel.UNVERIFIED, TrustLevel.TRUSTED, TrustLevel.VERIFIED].index(fm.trust) < min_trust_rank:
                continue
            if not self._visible(obj, principal):
                filtered += 1
                continue
            candidates.append(obj)
        qvec = None
        if SearchMode.SEMANTIC in query.modes and self.models is not None and candidates:
            await self._ensure_vectors()
            qvec = (await self.models.embed(EmbedRequest(texts=[query.text]))).vectors[0]
        hits = []
        for obj in candidates:
            doc_terms = _terms(f"{obj.frontmatter.title} {' '.join(obj.frontmatter.tags)} {obj.body}")
            scores: dict[str, float] = {}
            if SearchMode.LEXICAL in query.modes:
                scores["lexical"] = len(q_terms & set(doc_terms)) / (len(q_terms) or 1)
            if qvec is not None:
                scores["semantic"] = sum(a * b for a, b in zip(qvec, self._vectors[obj.path], strict=True))
            if SearchMode.GRAPH in query.modes:
                scores["graph"] = 0.1 * sum(1 for o in candidates if obj.path in o.links)
            score = sum(scores.values()) / (len(scores) or 1)
            if score <= 0:
                continue
            hits.append(SearchHit(path=obj.path, title=obj.frontmatter.title, type=obj.frontmatter.type,
                                  snippet=self._snippet(obj.body, q_terms), score=round(score, 4), scores=scores,
                                  provenance=obj.provenance, body=obj.body))
        hits.sort(key=lambda h: -h.score)
        hits = hits[: query.top_k]
        if self.firewall is not None:  # screen the whole document, not just the snippet that matched
            hits = await self.firewall.screen(hits)
        if not query.include_body:
            hits = [h.model_copy(update={"body": None}) for h in hits]
        return EvidenceSet(query=query, hits=hits, total_candidates=len(candidates), filtered_by_policy=filtered)

    async def traverse(self, path: str, principal: Principal, depth: int = 1, relations: list[str] | None = None) -> GraphResult:
        root = self._get(path, principal)
        seen, frontier, edges = {root.path}, [root.path], []
        for _ in range(depth):
            nxt = []
            for p in frontier:
                obj = self.objects.get(p)
                for dst in obj.links if obj else []:
                    target = self.objects.get(dst)
                    if target is None or not self._visible(target, principal):
                        continue
                    edges.append(GraphEdge(src=p, dst=dst, relation="links_to"))
                    if dst not in seen:
                        seen.add(dst)
                        nxt.append(dst)
            frontier = nxt
        if relations:
            edges = [e for e in edges if e.relation in relations]
        nodes = [KnowledgeEntry(path=p, title=self.objects[p].frontmatter.title, type=self.objects[p].frontmatter.type,
                                privacy=self.objects[p].frontmatter.privacy) for p in sorted(seen)]
        return GraphResult(root=root.path, nodes=nodes, edges=edges)

    async def ingest(self, request: IngestRequest) -> IngestResult:
        result = IngestResult()
        if request.source_type not in (IngestSourceType.FILE, IngestSourceType.DIRECTORY):
            result.skipped.append(f"fake ingest only supports file/directory, got {request.source_type}")
            return result
        src = Path(request.uri)
        files = [src] if src.is_file() else sorted(src.rglob("*.md"))
        for f in files:
            rel_base = request.target_path.removeprefix("/org").strip("/")
            rel = posixpath.join(rel_base, f.name) if rel_base else f.name
            obj = self._to_object(rel, f.read_text(encoding="utf-8"))
            existed = obj.path in self.objects
            self.objects[obj.path] = obj
            self._vectors.pop(obj.path, None)
            (result.updated if existed else result.created).append(obj.path)
            if self.bus is not None:
                await self.bus.publish(Event(type=EventType.KNOWLEDGE_CHANGED, source="knowledge.fake",
                                             payload=KnowledgeChange(path=obj.path, change=ChangeKind.UPDATED if existed else ChangeKind.CREATED,
                                                                     new_hash=obj.content_hash).model_dump(mode="json")))
        return result

    async def reindex(self, paths: list[str] | None = None) -> int:
        self._vectors.clear()
        await self._ensure_vectors()
        return len(self.objects)

    async def validate(self) -> ValidationReport:
        issues = []
        for obj in self.objects.values():
            if not obj.frontmatter.description:
                issues.append(ValidationIssue(okf_file=obj.okf_file, severity="warning", message="missing description"))
            for link in obj.links:
                if link not in self.objects:
                    issues.append(ValidationIssue(okf_file=obj.okf_file, severity="error", message=f"broken link {link}"))
        return ValidationReport(ok=not any(i.severity == "error" for i in issues), files_checked=len(self.objects), issues=issues)

    # --- helpers
    async def _ensure_vectors(self) -> None:
        missing = [p for p in self.objects if p not in self._vectors]
        if missing and self.models is not None:
            texts = [f"{self.objects[p].frontmatter.title}\n{self.objects[p].body}" for p in missing]
            for p, v in zip(missing, (await self.models.embed(EmbedRequest(texts=texts))).vectors, strict=True):
                self._vectors[p] = v

    @staticmethod
    def _snippet(body: str, q_terms: set[str], width: int = 220) -> str:
        for line in body.splitlines():
            if q_terms & set(_terms(line)):
                return line.strip()[:width]
        return body.strip()[:width]


class FakeMemoryService:
    def __init__(self, event_bus: Any = None) -> None:
        self.records: dict[str, MemoryRecord] = {}
        self.working_sets: dict[int, WorkingSet] = {}
        self.bus = event_bus

    async def store(self, record: MemoryRecord) -> str:
        self.records[record.memory_id] = record
        return record.memory_id

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        q = set(_terms(query.text))
        out = []
        for r in self.records.values():
            if r.org_id != query.org_id or r.kind not in query.kinds or r.scope not in query.scopes:
                continue
            if (query.owner and r.owner != query.owner) or (query.task_id and r.task_id != query.task_id):
                continue
            if r.stale and not query.include_stale:
                continue
            score = len(q & set(_terms(r.content + " " + " ".join(r.tags)))) + r.importance
            if score > r.importance or not q:
                out.append((score, r))
        return [r for _, r in sorted(out, key=lambda x: -x[0])][: query.top_k]

    async def build_working_set(self, pid: int, goal: str, evidence: EvidenceSet, memories: list[MemoryRecord], token_budget: int) -> WorkingSet:
        ws = WorkingSet(pid=pid, token_budget=token_budget)

        def add(item: WorkingSetItem) -> None:
            if ws.tokens_used + item.tokens <= token_budget or item.pinned:
                ws.items.append(item)
                ws.tokens_used += item.tokens

        add(WorkingSetItem(ref="inline", source="plan", content=goal, tokens=estimate_tokens(goal), pinned=True))
        for h in evidence.hits:
            text = h.body or h.snippet
            if h.firewall_flags:  # untrusted content is quoted as data, never as instructions
                text = f"<untrusted-data flags={','.join(h.firewall_flags)}>\n{text}\n</untrusted-data>"
            add(WorkingSetItem(ref=h.path, source="evidence", content=text, tokens=estimate_tokens(text)))
        for m in memories:
            text = m.summary or m.content
            add(WorkingSetItem(ref=m.memory_id, source="memory", content=text, tokens=estimate_tokens(text)))
        self.working_sets[pid] = ws
        return ws

    async def summarize(self, memory_ids: list[str]) -> MemoryRecord:
        parts = [self.records[i] for i in memory_ids if i in self.records]
        if not parts:
            raise KairosError("NOT_FOUND", f"no memories {memory_ids}")
        first = parts[0]
        rec = MemoryRecord(memory_id=new_id("MEM"), kind=first.kind, scope=first.scope, org_id=first.org_id,
                           owner=first.owner, content=" / ".join(p.summary or p.content for p in parts)[:2000],
                           derived_from=memory_ids)
        await self.store(rec)
        return rec

    async def consolidate(self, task_id: str) -> list[MemoryRecord]:
        out = []
        for r in list(self.records.values()):
            if r.task_id == task_id and r.kind == MemoryKind.EPISODIC and r.importance >= 0.5:
                sem = r.model_copy(update={"memory_id": new_id("MEM"), "kind": MemoryKind.SEMANTIC,
                                           "derived_from": [r.memory_id, *r.derived_from]})
                await self.store(sem)
                out.append(sem)
        return out

    async def invalidate(self, source: str) -> InvalidationReport:
        stale, frontier = [], {source}
        while frontier:
            nxt = set()
            for r in self.records.values():
                if not r.stale and frontier & set(r.derived_from):
                    self.records[r.memory_id] = r.model_copy(update={"stale": True})
                    stale.append(r.memory_id)
                    nxt.add(r.memory_id)
            frontier = nxt
        report = InvalidationReport(source=source, invalidated=stale,
                                    affected_agents=sorted({self.records[i].owner for i in stale}))
        if self.bus is not None and stale:
            await self.bus.publish(Event(type=EventType.MEMORY_INVALIDATED, source="memory.fake",
                                         payload=report.model_dump(mode="json")))
        return report

    async def rehydrate(self, pid: int) -> WorkingSet | None:
        return self.working_sets.get(pid)


# ============================================================================ AgentContext fake (for P3)

ChildRunner = Callable[[str, str, dict[str, Any]], Awaitable[AgentResult]]


def default_test_manifest(name: str = "test-agent") -> AgentManifest:
    return AgentManifest(name=name, description="Test agent with broad capabilities",
                         runtime=ManifestRuntime(entrypoint="tests:TestAgent"),
                         capabilities=ManifestCapabilities(knowledge=["read", "search"],
                                                           tools=["jira.read", "jira.write", "fs.read", "fs.write", "browser.open"],
                                                           agents=["research-agent"]))


class FakeAgentContext:
    """Stand-in for the kernel's AgentContext. P3 unit-tests agents with it; nothing else needed.

    Inspect afterwards: .logs, .narrations, .syscalls, .spawned, .spawn_requests, .sent, .checkpoints, .models.calls
    Inject: responses= (canned LLM replies), child_runner= (what spawned children return),
            auto_approve= (approve REQUIRES_APPROVAL syscalls), inbox messages via .inbox.put_nowait(msg)
    """

    def __init__(self, *, task_id: str = "T-test", pid: int = 101, ppid: int | None = None, manifest: AgentManifest | None = None,
                 principal: Principal | None = None, inputs: dict[str, Any] | None = None,
                 responses: dict[str, str | dict[str, Any]] | None = None, child_runner: ChildRunner | None = None,
                 auto_approve: bool = True, okf_dir: Path | None = None) -> None:
        self.task_id, self.pid, self.ppid, self.inputs = task_id, pid, ppid, inputs or {}
        self.manifest = manifest or default_test_manifest()
        self.principal = principal or Principal(kind=PrincipalKind.AGENT, org_id="acme", user_id="alice", pid=pid,
                                                agent=self.manifest.name, capabilities=self.manifest.all_capabilities())
        self.models = FakeModelRouter(responses)
        self.knowledge = FakeKnowledgeService(okf_dir, models=self.models, firewall=FakeContextFirewall())
        self.memory = FakeMemoryService()
        self.tools = FakeToolExecutor()
        self.policy = FakePolicyEngine()
        self.artifacts = InMemoryArtifactStore()
        self.auto_approve = auto_approve
        self.child_runner = child_runner
        self.inbox: asyncio.Queue[A2AMessage] = asyncio.Queue()
        self.logs: list[tuple[str, str, dict[str, Any] | None]] = []
        self.narrations: list[NarrationPayload] = []
        self.syscalls: list[tuple[SyscallRequest, SyscallResult]] = []
        self.spawned: dict[int, tuple[str, str, asyncio.Task]] = {}
        self.spawn_requests: dict[int, SpawnRequest] = {}  # what each spawn asked for (capabilities, scope, why)
        self.sent: list[A2AMessage] = []
        self.checkpoints: dict[str, dict[str, Any]] = {}
        self.approvals: list[Approval] = []
        self._next_pid = pid + 1
        self._cancelled = False

    def _need(self, cap: str) -> None:
        if not has_capability(cap, self.principal.capabilities):
            raise KairosError("CAPABILITY_DENIED", f"{self.manifest.name} lacks {cap}")

    async def llm(self, request: ModelRequest) -> ModelResponse:
        return await self.models.generate(request.model_copy(update={"task_id": self.task_id, "pid": self.pid}))

    async def search(self, query: SearchQuery) -> EvidenceSet:
        self._need("knowledge.search")
        return await self.knowledge.search(query, self.principal)

    async def read(self, path: str) -> KnowledgeObject:
        self._need("knowledge.read")
        return await self.knowledge.read(path, self.principal)

    async def list(self, path: str) -> KnowledgeListing:
        self._need("knowledge.read")
        return await self.knowledge.list(path, self.principal)

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        return await self.memory.recall(query)

    async def remember(self, record: MemoryRecord) -> str:
        return await self.memory.store(record)

    async def spawn(self, agent: str, goal: str, inputs: dict[str, Any] | None = None, *,
                    capabilities: list[str] | None = None, scope: list[str] | None = None, why: str | None = None) -> int:
        if agent not in self.manifest.capabilities.agents:
            raise KairosError("CAPABILITY_DENIED", f"{self.manifest.name} may not spawn {agent}")
        pid, self._next_pid = self._next_pid, self._next_pid + 1
        self.spawn_requests[pid] = SpawnRequest(agent=agent, goal=goal, task_id=self.task_id, ppid=self.pid, inputs=inputs or {},
                                                capabilities=capabilities, scope=scope, why=why)

        async def default_child(a: str, g: str, i: dict[str, Any]) -> AgentResult:
            return AgentResult(pid=pid, agent=a, status=AgentResultStatus.COMPLETED, summary=f"[fake {a}] {g}")

        runner = self.child_runner or default_child
        self.spawned[pid] = (agent, goal, asyncio.ensure_future(runner(agent, goal, inputs or {})))
        return pid

    async def wait(self, pid: int, timeout: float | None = None) -> AgentResult:
        if pid not in self.spawned:
            raise KairosError("PROCESS_NOT_FOUND", str(pid))
        result = await asyncio.wait_for(self.spawned[pid][2], timeout)
        return result.model_copy(update={"pid": pid})

    async def send(self, message: A2AMessage) -> None:
        self.sent.append(message)

    async def receive(self, timeout: float | None = None) -> A2AMessage | None:
        try:
            return await asyncio.wait_for(self.inbox.get(), timeout)
        except TimeoutError:
            return None

    async def syscall(self, request: SyscallRequest) -> SyscallResult:
        decision = await self.policy.evaluate(request, self.principal)
        if decision.decision == Decision.DENY:
            result = SyscallResult(syscall_id=request.syscall_id, status=SyscallStatus.DENIED, decision=decision)
        elif decision.decision == Decision.REQUIRES_APPROVAL and not self.auto_approve:
            self.approvals.append(Approval(approval_id=decision.approval_id or new_id("APR"), task_id=self.task_id,
                                           pid=self.pid, agent=self.manifest.name, syscall=request, decision=decision,
                                           status=ApprovalStatus.REJECTED))
            result = SyscallResult(syscall_id=request.syscall_id, status=SyscallStatus.REJECTED, decision=decision)
        else:
            inv = ToolInvocation(invocation_id=new_id("INV"), syscall_id=request.syscall_id, task_id=self.task_id,
                                 pid=self.pid, tool=request.tool, operation=request.operation, arguments=request.arguments)
            tr = await self.tools.execute(inv)
            verified = (await self.tools.verify(inv, tr)).passed
            if tr.status == ToolResultStatus.SUCCESS and not verified:
                await self.tools.rollback(inv, tr)
                status = SyscallStatus.ROLLED_BACK
            else:
                status = SyscallStatus.COMPLETED if tr.status == ToolResultStatus.SUCCESS else SyscallStatus.FAILED
            result = SyscallResult(syscall_id=request.syscall_id, status=status, decision=decision,
                                   tool_result=tr, verified=verified, error=tr.error)
        self.syscalls.append((request, result))
        return result

    async def put_artifact(self, name: str, data: bytes | str | dict, content_type: str = "application/json") -> str:
        raw = json.dumps(data).encode() if isinstance(data, dict) else data.encode() if isinstance(data, str) else data
        return await self.artifacts.put(self.task_id, name, raw, content_type)

    async def get_artifact(self, ref: str) -> bytes:
        return await self.artifacts.get(ref)

    async def log(self, message: str, level: str = "info", data: dict[str, Any] | None = None) -> None:
        self.logs.append((level, message, data))

    async def narrate(self, payload: NarrationPayload) -> None:
        if type(payload) not in NARRATION_EVENTS:
            raise KairosError("BAD_REQUEST", f"cannot narrate {type(payload).__name__}")
        if isinstance(payload, AgentThought):
            payload = payload.model_copy(update={"pid": self.pid})
        self.narrations.append(payload)

    async def checkpoint(self, state: dict[str, Any]) -> str:
        cid = new_id("CKPT")
        self.checkpoints[cid] = state
        return cid

    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


# ============================================================================ P4: converters / browser driver

class FakeMarkdownConverter:
    """Passes OKF-ish Markdown through. Real converters (jira-json, slack-export, csv, pdf…) are P4's."""

    name = "markdown"
    source_types = [IngestSourceType.FILE, IngestSourceType.DIRECTORY]

    def can_convert(self, request: IngestRequest) -> bool:
        return request.source_type in self.source_types and (Path(request.uri).is_dir() or request.uri.endswith(".md"))

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        src = Path(request.uri)
        if not src.exists():
            raise KairosError("BAD_REQUEST", f"no such file or directory: {request.uri}")
        files = [src] if src.is_file() else sorted(src.rglob("*.md"))
        base = request.target_path.removeprefix("/org").strip("/")
        drafts = []
        for f in files:
            fm, body = parse_okf(f.read_text(encoding="utf-8"))
            fm.setdefault("type", "note")
            fm.setdefault("title", f.stem.replace("-", " ").title())
            rel = f.name if src.is_file() else f.relative_to(src).as_posix()
            drafts.append(OKFDraft(okf_file=posixpath.join(base, rel) if base else rel,
                                   frontmatter=OKFFrontmatter.model_validate(fm), body=body, source_ref=str(f)))
        return drafts


class FakeBrowserDriver:
    """Returns canned pages; records calls in .actions. The real one connects to sandbox.endpoints['playwright']."""

    def __init__(self) -> None:
        self.actions: list[tuple[str, str, str]] = []
        self._url: dict[str, str] = {}

    def _page(self, sandbox: SandboxInfo) -> BrowserPage:
        url = self._url.get(sandbox.sandbox_id, "about:blank")
        return BrowserPage(url=url, title=f"Fake page for {url}", text="The v5 SDK release is delayed to October.",
                           links=[f"{url.rstrip('/')}/status"])

    async def open(self, sandbox: SandboxInfo, url: str) -> BrowserPage:
        self.actions.append((sandbox.sandbox_id, "open", url))
        self._url[sandbox.sandbox_id] = url
        return self._page(sandbox)

    async def click(self, sandbox: SandboxInfo, selector: str) -> BrowserPage:
        self.actions.append((sandbox.sandbox_id, "click", selector))
        return self._page(sandbox)

    async def type(self, sandbox: SandboxInfo, selector: str, text: str) -> BrowserPage:
        self.actions.append((sandbox.sandbox_id, "type", f"{selector}={text}"))
        return self._page(sandbox)

    async def screenshot(self, sandbox: SandboxInfo) -> bytes:
        return b"\x89PNG\r\n\x1a\n"  # PNG signature only

    async def close(self, sandbox: SandboxInfo) -> None:
        self._url.pop(sandbox.sandbox_id, None)


class FakeResourceProbe:
    """Static numbers; the real probe (P4) reads psutil + nvidia-smi."""

    async def snapshot(self) -> ResourceSnapshot:
        return ResourceSnapshot(cpu_percent=12.5, ram_used_mb=8192, ram_total_mb=32768,
                                gpu=GpuStatus(name="Fake RTX", utilization=0.1, memory_used_mb=1024, memory_total_mb=8192))


class FakePermissionsProvider:
    """PermissionsProvider for tests: every user gets `capabilities` / `data_scopes` (default: all of /org and every
    capability in the catalog), or what `users` sets for them by user id."""

    ALL = ["knowledge.*", "memory.*", "agent.*", "jira.*", "fs.*", "browser.*", "sandbox.*", "postgres.*", "database.*",
           "db.*", "external.*", "mcp.*"]

    def __init__(self, users: dict[str, UserPermissions] | None = None) -> None:
        self.users = users or {}

    async def resolve(self, user_id: str, org_id: str, roles: list[str] | None = None) -> UserPermissions:
        if user_id in self.users:
            return self.users[user_id]
        return UserPermissions(user_id=user_id, org_id=org_id, roles=list(roles or ["owner"]), permissions=["task.create"],
                               capabilities=list(self.ALL), data_scopes=["/org/**"])


def fake_bundle(settings: Any = None) -> Any:
    """A ServiceBundle where every service is a fake — P1 builds the kernel on top of this before anything is real."""
    from ..wiring import ServiceBundle, Settings

    s = settings or Settings()
    b = ServiceBundle(settings=s, event_bus=InMemoryEventBus(), artifacts=InMemoryArtifactStore(), models=FakeModelRouter(),
                      firewall=FakeContextFirewall(), memory=None, sandbox=FakeSandboxManager(), tools=FakeToolExecutor(),
                      browser=FakeBrowserDriver(), converters=[FakeMarkdownConverter()],
                      agent_registry=FakeAgentRegistry(), agent_runtime=FakeAgentRuntime(), probe=FakeResourceProbe(),
                      policy=FakePolicyEngine(),
                      audit=InMemoryAuditLog(), permissions=FakePermissionsProvider())
    b.knowledge = FakeKnowledgeService(s.okf_dir, b.models, b.firewall, b.event_bus)
    b.memory = FakeMemoryService(b.event_bus)
    b.modes = {k: "fake" for k in ("event_bus", "artifacts", "models", "firewall", "knowledge", "memory", "sandbox",
                                   "browser", "tools", "converters", "agent_registry", "agent_runtime", "probe", "policy", "audit")}
    return b


__all__ = [
    "fake_bundle", "FakeMarkdownConverter", "FakeBrowserDriver", "FakeResourceProbe",
    "FAKE_TOOL_SPECS", "FIXTURE_MANIFESTS_DIR", "FIXTURE_OKF_DIR", "FakeAgentContext", "FakeAgentRegistry",
    "FakeAgentRuntime", "FakeContextFirewall", "FakePermissionsProvider", "FakeKnowledgeService", "FakeMemoryService", "FakeModelRouter",
    "FakePolicyEngine", "FakeSandboxManager", "FakeToolExecutor", "InMemoryArtifactStore", "InMemoryAuditLog",
    "InMemoryEventBus", "default_test_manifest", "load_manifests", "parse_okf", "system_principal", "user_principal",
]
