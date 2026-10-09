"""Files from outside /org: uploads, and folders of this computer mounted into /org/mnt/<name>.

A mount is how KAIROS handles the machine's own filesystem: every supported document under the host folder is
converted to OKF, indexed and searchable by agents; the folder is watched, so an edited file is re-ingested (and the
memories built on it go stale) and a deleted one leaves /org. Mounts are read-only mirrors: agents never write back to
the host folder (writes stay governed syscalls into their sandboxed workspace).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Event,
    EventType,
    IngestRequest,
    IngestResult,
    IngestSourceType,
    KnowledgeMount,
    KnowledgeMountCreate,
)
from kairos_contracts.schema.common import new_id, utcnow
from kairos_contracts.util import org_path_to_okf_file

log = logging.getLogger("kairos.kernel.gateway.files")

# What the converters understand (markdown, csv, text and code, documents with the ingest extra, jira/slack json).
SUPPORTED = {".md", ".csv", ".json", ".txt", ".text", ".log", ".rst", ".pdf", ".docx", ".pptx", ".xlsx", ".py", ".ts", ".tsx",
             ".js", ".sql", ".sh", ".ps1", ".yaml", ".yml", ".toml", ".ini", ".java", ".go", ".rs", ".c", ".cpp", ".cs",
             ".html", ".css"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".cache", ".idea", ".vscode"}
MAX_FILES = 2000
MAX_BYTES = 25 * 1024 * 1024


def _host_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        rel_parts = p.relative_to(root).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
            continue
        if p.is_file() and p.suffix.lower() in SUPPORTED and p.stat().st_size <= MAX_BYTES:
            out.append(p)
            if len(out) >= MAX_FILES:
                break
    return out


class FileService:
    def __init__(self, kernel: Any, db: Any) -> None:
        self.k = kernel
        self.db = db
        self.db.script("CREATE TABLE IF NOT EXISTS mounts(name TEXT PRIMARY KEY, host_path TEXT NOT NULL, created_by TEXT, "
                       "created_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT '{}');")
        self.uploads_dir = Path(kernel.settings.data_dir) / "uploads"
        self._watchers: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def knowledge(self) -> Any:
        return self.k.services.require("knowledge")

    async def _emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.k.bus is not None:
            await self.k.bus.publish(Event(type=type_, source="gateway.files", payload=payload))

    async def _ingest_file(self, path: Path, target: str, label: str, frontmatter: dict[str, Any] | None = None) -> IngestResult:
        req = IngestRequest(source_type=IngestSourceType.FILE, uri=str(path), target_path=target,
                            options={"frontmatter": frontmatter} if frontmatter else {})
        res = await self.knowledge.ingest(req)
        stage = "error" if res.errors and not (res.created or res.updated) else "skipped" if not (res.created or res.updated) else "indexed"
        await self._emit(EventType.INGEST_PROGRESS, {"file": label, "stage": stage, "path": (res.created + res.updated or [None])[0],
                                                     "error": "; ".join(res.errors) or None})
        return res

    # ------------------------------------------------------------------ uploads
    async def upload(self, files: list[tuple[str, bytes]], target: str, privacy: str | None, by: str) -> IngestResult:
        if not target.startswith("/org"):
            raise KairosError("BAD_REQUEST", "target folder must be under /org")
        batch = self.uploads_dir / new_id("UP")
        batch.mkdir(parents=True, exist_ok=True)
        total = IngestResult()
        try:
            for name, data in files:
                safe = Path(name).name or "upload"
                if Path(safe).suffix.lower() not in SUPPORTED:
                    total.skipped.append(f"{safe} (unsupported type)")
                    await self._emit(EventType.INGEST_PROGRESS, {"file": safe, "stage": "skipped", "error": "unsupported type"})
                    continue
                await self._emit(EventType.INGEST_PROGRESS, {"file": safe, "stage": "received"})
                p = batch / safe
                p.write_bytes(data)
                fm = {"owner": by, **({"privacy": privacy} if privacy else {})}
                res = await self._ingest_file(p, target, safe, fm)
                total.created += res.created
                total.updated += res.updated
                total.skipped += res.skipped
                total.errors += [f"{safe}: {e}" for e in res.errors]
        finally:
            shutil.rmtree(batch, ignore_errors=True)
        return total

    # ------------------------------------------------------------------ mounts
    def _row(self, name: str) -> Any:
        row = self.db.one("SELECT * FROM mounts WHERE name=?", (name,))
        if not row:
            raise KairosError("NOT_FOUND", f"mount {name}")
        return row

    def _mount(self, row: Any) -> KnowledgeMount:
        state = json.loads(row["state"] or "{}")
        return KnowledgeMount(name=row["name"], host_path=row["host_path"], org_path=f"/org/mnt/{row['name']}",
                     files=len(state.get("files", {})), skipped=state.get("skipped", 0), watching=row["name"] in self._watchers,
                     synced_at=state.get("synced_at"), errors=state.get("errors", [])[:20])

    def list(self) -> list[KnowledgeMount]:
        return [self._mount(r) for r in self.db.all("SELECT * FROM mounts ORDER BY name")]

    async def add(self, body: KnowledgeMountCreate, by: str) -> KnowledgeMount:
        host = Path(body.host_path).expanduser()
        if not host.is_dir():
            raise KairosError("BAD_REQUEST", f"no such folder on this computer: {body.host_path}")
        okf = Path(self.k.settings.okf_dir).resolve()
        if okf == host.resolve() or okf in host.resolve().parents or host.resolve() in okf.parents:
            raise KairosError("BAD_REQUEST", "that folder overlaps the knowledge bundle itself")
        if self.db.one("SELECT 1 FROM mounts WHERE name=?", (body.name,)):
            raise KairosError("CONFLICT", f"a mount called {body.name} exists")
        self.db.execute("INSERT INTO mounts VALUES (?,?,?,?,?)", (body.name, str(host.resolve()), by, utcnow().isoformat(), "{}"))
        mount = await self.sync(body.name)
        self._watch(body.name)
        return mount.model_copy(update={"watching": True})

    async def remove(self, name: str) -> None:
        row = self._row(name)
        task = self._watchers.pop(name, None)
        if task:
            task.cancel()
        state = json.loads(row["state"] or "{}")
        await self._forget(list(state.get("files", {}).values()))
        shutil.rmtree(Path(self.k.settings.okf_dir) / "mnt" / name, ignore_errors=True)
        self.db.execute("DELETE FROM mounts WHERE name=?", (name,))

    async def _forget(self, org_paths: list[str]) -> None:
        """Delete mirrored OKF files and drop them from the index (the knowledge service drops rows for vanished files)."""
        okf = Path(self.k.settings.okf_dir)
        for path in org_paths:
            with contextlib.suppress(OSError):
                (okf / org_path_to_okf_file(path)).unlink()
        if org_paths:
            with contextlib.suppress(Exception):
                await self.knowledge.reindex(org_paths)

    async def sync(self, name: str, only: list[Path] | None = None) -> KnowledgeMount:
        """Bring /org/mnt/<name> in line with the host folder: ingest new and changed files, forget vanished ones."""
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            row = self._row(name)
            host = Path(row["host_path"])
            state = json.loads(row["state"] or "{}")
            files: dict[str, str] = state.get("files", {})  # host relative path -> org path
            mtimes: dict[str, float] = state.get("mtimes", {})
            errors: list[str] = []
            present = await asyncio.to_thread(_host_files, host) if host.is_dir() else []
            present_rel = {p.relative_to(host).as_posix(): p for p in present}
            todo = [present_rel[r] for r in present_rel if only is None or present_rel[r] in only]
            skipped = 0
            for p in todo:
                rel = p.relative_to(host).as_posix()
                mtime = p.stat().st_mtime
                if files.get(rel) and mtimes.get(rel) == mtime:
                    continue
                target = f"/org/mnt/{name}" + ("/" + str(Path(rel).parent.as_posix()) if Path(rel).parent.as_posix() != "." else "")
                try:
                    res = await self._ingest_file(p, target, f"{name}/{rel}", {"source": "file"})
                except KairosError as e:
                    res = IngestResult(errors=[e.message])
                paths = res.created + res.updated
                if paths:
                    files[rel], mtimes[rel] = paths[0], mtime
                elif res.errors:
                    skipped += 1
                    errors.append(f"{rel}: {'; '.join(res.errors)}")
            vanished = [r for r in list(files) if r not in present_rel]
            await self._forget([files.pop(r) for r in vanished])
            for r in vanished:
                mtimes.pop(r, None)
            state = {"files": files, "mtimes": mtimes, "skipped": skipped if only is None else state.get("skipped", 0) + skipped,
                     "errors": errors if only is None else (state.get("errors", []) + errors)[-50:], "synced_at": utcnow().isoformat()}
            self.db.execute("UPDATE mounts SET state=? WHERE name=?", (json.dumps(state), name))
            mount = self._mount(self._row(name))
        await self._emit(EventType.MOUNT_SYNCED, mount.model_dump(mode="json"))
        return mount

    def _watch(self, name: str) -> None:
        if name in self._watchers:
            return
        self._watchers[name] = asyncio.create_task(self._watch_loop(name), name=f"mount:{name}")

    async def _watch_loop(self, name: str) -> None:
        from watchfiles import awatch

        host = Path(self._row(name)["host_path"])
        # A folder inside WSL (a \\wsl.localhost path) or on a network share sends no change notifications: poll it.
        remote = str(host).startswith("\\\\")
        try:
            async for changes in awatch(host, debounce=800, recursive=True, force_polling=remote, poll_delay_ms=1500):
                changed = [Path(p) for _, p in changes]
                if any(not p.exists() for p in changed):
                    await self.sync(name)  # something was deleted or renamed: a full pass finds what vanished
                else:
                    await self.sync(name, only=[p for p in changed if p.is_file()])
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — a watcher failure must not take the gateway down
            log.warning("mount %s stopped watching: %s", name, e)
            self._watchers.pop(name, None)

    async def start(self) -> None:
        """At boot: catch up with changes made while KAIROS was off, then watch every mount."""
        for row in self.db.all("SELECT name FROM mounts"):
            try:
                await self.sync(row["name"])
                self._watch(row["name"])
            except Exception as e:  # noqa: BLE001
                log.warning("mount %s could not start: %s", row["name"], e)

    async def stop(self) -> None:
        for task in self._watchers.values():
            task.cancel()
        self._watchers.clear()
