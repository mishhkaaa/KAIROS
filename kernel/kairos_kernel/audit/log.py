"""Append-only audit journal on SQLite with a per-task hash chain (tamper evidence)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import AuditEntry, AuditKind, RunTimeline, TimelineStats

from ..persistence.db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit(
  task_id TEXT NOT NULL, seq INTEGER NOT NULL, entry_id TEXT NOT NULL, ts TEXT NOT NULL, kind TEXT NOT NULL,
  data TEXT NOT NULL, hash TEXT, PRIMARY KEY (task_id, seq));
"""


def entry_hash(entry: AuditEntry) -> str:
    body = entry.model_dump(mode="json", exclude={"hash"})
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def chain_ok(entries: list[AuditEntry]) -> bool:
    """Every entry's hash recomputes and links to the previous entry's hash."""
    prev = None
    for e in entries:
        if e.prev_hash != prev or entry_hash(e.model_copy(update={"hash": None})) != e.hash:
            return False
        prev = e.hash
    return True


class SqliteAuditLog:
    def __init__(self, path: Path | str) -> None:
        self.db = Database(path)
        self.db.script(SCHEMA)

    async def append(self, entry: AuditEntry) -> AuditEntry:
        with self.db.transaction() as conn:
            last = conn.execute("SELECT seq, hash FROM audit WHERE task_id=? ORDER BY seq DESC LIMIT 1",
                                (entry.task_id,)).fetchone()
            seq, prev = (last["seq"] + 1, last["hash"]) if last else (1, None)
            stored = entry.model_copy(update={"seq": seq, "prev_hash": prev, "hash": None})
            stored = stored.model_copy(update={"hash": entry_hash(stored)})
            conn.execute("INSERT INTO audit VALUES (?,?,?,?,?,?,?)",
                         (stored.task_id, seq, stored.entry_id, stored.ts.isoformat(), stored.kind.value,
                          stored.model_dump_json(), stored.hash))
        return stored

    def entries(self, task_id: str) -> list[AuditEntry]:
        rows = self.db.all("SELECT data FROM audit WHERE task_id=? ORDER BY seq", (task_id,))
        return [AuditEntry.model_validate_json(r["data"]) for r in rows]

    def verify_chain(self, task_id: str) -> bool:
        return chain_ok(self.entries(task_id))

    async def timeline(self, task_id: str) -> RunTimeline:
        entries = self.entries(task_id)
        if not entries:
            raise KairosError("TASK_NOT_FOUND", f"no audit entries for {task_id}")
        kinds = [e.kind for e in entries]
        goal = next((e.data.get("goal", "") for e in entries if e.kind == AuditKind.TASK and "goal" in e.data), "")
        stats = TimelineStats(
            agents=kinds.count(AuditKind.SPAWN),
            models=sorted({e.data["model"] for e in entries if e.kind == AuditKind.MODEL and e.data.get("model")}),
            knowledge_objects=len({r for e in entries if e.kind == AuditKind.KNOWLEDGE for r in e.refs}),
            ipc_messages=kinds.count(AuditKind.IPC),
            tool_calls=kinds.count(AuditKind.TOOL),
            privileged_syscalls=sum(1 for e in entries if e.kind == AuditKind.POLICY and e.data.get("decision") != "ALLOW"),
            approvals=kinds.count(AuditKind.APPROVAL),
            rollbacks=kinds.count(AuditKind.ROLLBACK),
        )
        return RunTimeline(task_id=task_id, goal=goal, entries=entries, stats=stats, chain_verified=chain_ok(entries))
