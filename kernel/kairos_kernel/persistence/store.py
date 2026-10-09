"""Kernel state store: tasks, processes, approvals, checkpoints, agent results, idempotency records.

Rows keep the full Pydantic model as JSON plus a few indexed columns. Survives restarts
($KAIROS_DATA_DIR/kernel.db — /sovereign-data on the appliance).
"""
from __future__ import annotations

from pathlib import Path

from kairos_contracts.schema import AgentProcess, AgentResult, Approval, Checkpoint, SyscallResult, Task

from .db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, status TEXT, created_at TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processes(pid INTEGER PRIMARY KEY, task_id TEXT, state TEXT, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS processes_task ON processes(task_id);
CREATE TABLE IF NOT EXISTS approvals(approval_id TEXT PRIMARY KEY, task_id TEXT, status TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checkpoints(checkpoint_id TEXT PRIMARY KEY, pid INTEGER, task_id TEXT, created_at TEXT,
                                       data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS checkpoints_pid ON checkpoints(pid);
CREATE TABLE IF NOT EXISTS results(pid INTEGER PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY, data TEXT NOT NULL);
"""


class StateStore:
    def __init__(self, path: Path | str) -> None:
        self.db = Database(path)
        self.db.script(SCHEMA)

    # --- tasks
    def put_task(self, t: Task) -> None:
        self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?)",
                        (t.task_id, t.status.value, t.created_at.isoformat(), t.model_dump_json()))

    def tasks(self) -> list[Task]:
        return [Task.model_validate_json(r["data"]) for r in self.db.all("SELECT data FROM tasks ORDER BY created_at")]

    # --- processes
    def put_process(self, p: AgentProcess) -> None:
        self.db.execute("INSERT OR REPLACE INTO processes VALUES (?,?,?,?)",
                        (p.pid, p.task_id, p.state.value, p.model_dump_json()))

    def processes(self) -> list[AgentProcess]:
        return [AgentProcess.model_validate_json(r["data"]) for r in self.db.all("SELECT data FROM processes ORDER BY pid")]

    def max_pid(self) -> int:
        row = self.db.one("SELECT MAX(pid) AS m FROM processes")
        return int(row["m"]) if row and row["m"] is not None else 100

    # --- approvals
    def put_approval(self, a: Approval) -> None:
        self.db.execute("INSERT OR REPLACE INTO approvals VALUES (?,?,?,?)",
                        (a.approval_id, a.task_id, a.status.value, a.model_dump_json()))

    def approvals(self) -> list[Approval]:
        return [Approval.model_validate_json(r["data"]) for r in self.db.all("SELECT data FROM approvals")]

    # --- checkpoints
    def put_checkpoint(self, c: Checkpoint) -> None:
        self.db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?,?)",
                        (c.checkpoint_id, c.pid, c.task_id, c.created_at.isoformat(), c.model_dump_json()))

    def latest_checkpoint(self, pid: int) -> Checkpoint | None:
        row = self.db.one("SELECT data FROM checkpoints WHERE pid=? ORDER BY created_at DESC LIMIT 1", (pid,))
        return Checkpoint.model_validate_json(row["data"]) if row else None

    # --- agent results
    def put_result(self, r: AgentResult) -> None:
        self.db.execute("INSERT OR REPLACE INTO results VALUES (?,?)", (r.pid, r.model_dump_json()))

    def result(self, pid: int) -> AgentResult | None:
        row = self.db.one("SELECT data FROM results WHERE pid=?", (pid,))
        return AgentResult.model_validate_json(row["data"]) if row else None

    # --- syscall idempotency
    def put_idempotent(self, key: str, r: SyscallResult) -> None:
        self.db.execute("INSERT OR REPLACE INTO idempotency VALUES (?,?)", (key, r.model_dump_json()))

    def idempotent(self, key: str) -> SyscallResult | None:
        row = self.db.one("SELECT data FROM idempotency WHERE key=?", (key,))
        return SyscallResult.model_validate_json(row["data"]) if row else None
