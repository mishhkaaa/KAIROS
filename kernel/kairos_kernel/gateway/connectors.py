"""Connected apps (GitHub, Google Calendar): connection state per org, the token vault, and syncing into /org.

A connector's tool backend lives in the executor (execution/connectors). Connecting hands its token to the backend
through `configure(token)`; without one it runs its built-in mock, so the demo works with no accounts. Tokens stay in
the vault and the backend: never in an invocation, an event, the audit log or a response.
"""
from __future__ import annotations

import collections
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Connector,
    ConnectorConnect,
    ConnectorStatus,
    ConnectorSyncResult,
    Event,
    EventType,
    IngestRequest,
    IngestSourceType,
    ToolInvocation,
)
from kairos_contracts.schema.common import new_id, utcnow

from ..identity import Identity

log = logging.getLogger("kairos.kernel.gateway.connectors")

CATALOG: dict[str, dict[str, Any]] = {
    "github": {"name": "GitHub", "tool": "github", "capabilities": ["github.read", "github.write"], "scopes": ["repo", "issues"],
               "default_account": "acme/reconciliation"},
    "google_calendar": {"name": "Google Calendar", "tool": "calendar", "capabilities": ["calendar.read", "calendar.write"],
                        "scopes": ["calendar.events"], "default_account": "primary"},
}


def github_repo(account: str) -> tuple[str, str]:
    """`owner/repo` from what people paste: `owner/repo`, `github.com/owner/repo`, a clone URL, with or without `.git`."""
    text = re.sub(r"^(https?://)?(www\.)?github\.com[/:]", "", account.strip().removeprefix("git@")).strip("/")
    owner, _, repo = text.removesuffix(".git").partition("/")
    repo = repo.split("/")[0]
    if not owner or not repo:
        raise KairosError("BAD_REQUEST", f"GitHub repository must be owner/repo (for example mishhkaaa/KAIROS), not {account!r}")
    return owner, repo


class ConnectorService:
    def __init__(self, kernel: Any, identity: Identity) -> None:
        self.k = kernel
        self.identity = identity
        self.recent: dict[str, collections.deque[str]] = {cid: collections.deque(maxlen=5) for cid in CATALOG}
        if kernel.bus is not None:
            kernel.bus.subscribe("syscall.requested", self._on_syscall)

    async def _on_syscall(self, event: Event) -> None:
        capability = str(event.payload.get("capability", ""))
        for cid, spec in CATALOG.items():
            if capability in spec["capabilities"] and event.pid:
                try:
                    agent = self.k.procs.get(event.pid).agent
                except KairosError:
                    continue
                if agent not in self.recent[cid]:
                    self.recent[cid].appendleft(agent)

    def _backend(self, cid: str) -> Any:
        tools = self.k.services.tools
        backend = getattr(tools, "backends", {}).get(CATALOG[cid]["tool"]) if tools is not None else None
        if backend is None or not hasattr(backend, "configure"):
            raise KairosError("NOT_FOUND", f"no {CATALOG[cid]['name']} tool backend is wired in")
        return backend

    def _spec(self, cid: str) -> dict[str, Any]:
        if cid not in CATALOG:
            raise KairosError("NOT_FOUND", f"connector {cid}")
        return CATALOG[cid]

    def get(self, org_id: str, cid: str) -> Connector:
        spec = self._spec(cid)
        meta = self.identity.vault.meta(org_id, f"connector:{cid}") or {}
        return Connector(connector_id=cid, name=spec["name"], capabilities=spec["capabilities"],
                         status=ConnectorStatus.CONNECTED if meta else ConnectorStatus.DISCONNECTED,
                         mode=meta.get("mode", "mock"), scopes=spec["scopes"] if meta else [],
                         connected_by=meta.get("connected_by"), connected_at=meta.get("connected_at"),
                         last_sync=meta.get("last_sync"), recent_agents=list(self.recent[cid]))

    def list(self, org_id: str) -> list[Connector]:
        return [self.get(org_id, cid) for cid in CATALOG]

    async def _changed(self, c: Connector) -> None:
        if self.k.bus is not None:
            await self.k.bus.publish(Event(type=EventType.CONNECTOR_CHANGED, source="gateway.connectors", payload=c.model_dump(mode="json")))

    async def connect(self, org_id: str, cid: str, body: ConnectorConnect, by: str) -> Connector:
        spec = self._spec(cid)
        token = (body.token or "").strip() or None
        account = (body.account or "").strip() or spec["default_account"]
        if cid == "github":
            account = "/".join(github_repo(account))
        meta = {"connected_by": by, "connected_at": utcnow().isoformat(), "mode": "live" if token else "mock",
                "account": account}
        self.identity.vault.put(org_id, f"connector:{cid}", {"token": token} if token else {}, meta)
        self._backend(cid).configure(token)
        c = self.get(org_id, cid)
        await self._changed(c)
        return c

    async def disconnect(self, org_id: str, cid: str) -> None:
        self._spec(cid)
        self.identity.vault.delete(org_id, f"connector:{cid}")
        self._backend(cid).configure(None)
        await self._changed(self.get(org_id, cid))

    async def restore(self, org_id: str) -> None:
        """At boot: hand each connected org's tokens back to the backends (one org per box today)."""
        for cid in CATALOG:
            secret = self.identity.vault.get(org_id, f"connector:{cid}")
            if secret and secret.get("token"):
                try:
                    self._backend(cid).configure(secret["token"])
                except KairosError:
                    pass

    async def _call(self, cid: str, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(cid)
        backend = self._backend(cid)
        # A sync is the org's own read (connectors.manage), not an agent's syscall: no task or process behind it.
        inv = ToolInvocation(invocation_id=new_id("INV"), syscall_id="connector-sync", task_id="T-connectorsync", pid=1,
                             tool=spec["tool"], operation=operation, arguments=arguments)
        res = await backend.execute(inv)
        if res.status.value != "success":
            raise KairosError("TOOL_FAILED", f"{spec['name']} {operation}: {res.error.message if res.error else res.status.value}")
        return res.output or {}

    async def sync(self, org_id: str, cid: str) -> ConnectorSyncResult:
        """Bring the connected account's content into /org: GitHub issues and README under /org/github/<repo>, the next
        two weeks of the calendar as one note under /org/calendar."""
        meta = self.identity.vault.meta(org_id, f"connector:{cid}")
        if not meta:
            raise KairosError("BAD_REQUEST", f"connect {self._spec(cid)['name']} first")
        account = meta.get("account") or self._spec(cid)["default_account"]
        staging = Path(self.k.settings.data_dir) / "sync" / new_id("SY")
        staging.mkdir(parents=True, exist_ok=True)
        result = ConnectorSyncResult()
        try:
            if cid == "github":
                owner, repo = github_repo(account)
                issues = (await self._call(cid, "list_issues", {"owner": owner, "repo": repo, "state": "all"})).get("issues", [])
                for i in issues:
                    body = (f"# #{i['number']} {i['title']}\n\n**State:** {i['state']}  \n**Labels:** {', '.join(i.get('labels') or []) or 'none'}  \n"
                            f"**Link:** {i.get('html_url') or ''}\n\n{i.get('body') or ''}\n")
                    (staging / f"issue-{i['number']}.md").write_text(body, encoding="utf-8")
                try:
                    readme = await self._call(cid, "get_file", {"owner": owner, "repo": repo, "path": "README.md"})
                    (staging / "readme.md").write_text(readme.get("content", ""), encoding="utf-8")
                except KairosError as e:
                    result.errors.append(str(e))
                target = f"/org/github/{owner}-{repo}"
            else:
                events = (await self._call(cid, "list_events", {"calendar_id": account, "max_results": 25})).get("events", [])
                lines = ["# Upcoming meetings", "", f"From the {account} calendar, synced {utcnow():%Y-%m-%d %H:%M} UTC.", ""]
                lines += [f"- **{e.get('summary') or '(no title)'}**: {e.get('start')} to {e.get('end')}"
                          + (f", with {', '.join(e['attendees'])}" if e.get("attendees") else "")
                          + (f" ([Meet]({e['meet_link']}))" if e.get("meet_link") else "") for e in events]
                (staging / "upcoming.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
                target = "/org/calendar"
            knowledge = self.k.services.require("knowledge")
            for f in sorted(staging.glob("*.md")):
                res = await knowledge.ingest(IngestRequest(source_type=IngestSourceType.FILE, uri=str(f), target_path=target,
                                                           options={"frontmatter": {"source": cid, "trust": "unverified"}}))
                result.created += res.created
                result.updated += res.updated
                # A README's relative links point at repository files that are not synced: expected, not a failure.
                result.errors += [e for e in res.errors if "broken link" not in e]
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        self.identity.vault.put(org_id, f"connector:{cid}", self.identity.vault.get(org_id, f"connector:{cid}") or {},
                                {**meta, "last_sync": utcnow().isoformat()})
        await self._changed(self.get(org_id, cid))
        return result
