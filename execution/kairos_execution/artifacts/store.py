"""Filesystem ArtifactStore: artifact://<task_id>/<name>  <->  <root>/<task_id>/<name> (+ .meta/<name>.json)."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from kairos_contracts.errors import KairosError

_REF = re.compile(r"^artifact://(?P<task>[^/]+)/(?P<name>.+)$")
_SAFE_TASK = re.compile(r"^[A-Za-z0-9_\-]+$")


class FsArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, task_id: str, name: str) -> Path:
        if not _SAFE_TASK.match(task_id):
            raise KairosError("BAD_REQUEST", f"invalid task id {task_id!r}")
        parts = name.replace("\\", "/").split("/")
        if not name or name.startswith("/") or any(p in ("", ".", "..", ".meta") for p in parts):
            raise KairosError("BAD_REQUEST", f"invalid artifact name {name!r}")
        base = (self.root / task_id).resolve()
        path = (base / name).resolve()
        if not path.is_relative_to(base):
            raise KairosError("BAD_REQUEST", f"artifact name escapes the task folder: {name!r}")
        return path

    def _parse(self, ref: str) -> Path:
        m = _REF.match(ref)
        if not m:
            raise KairosError("BAD_REQUEST", f"not an artifact ref: {ref!r}")
        return self._path(m["task"], m["name"])

    async def put(self, task_id: str, name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(task_id, name)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            meta = self.root / task_id / ".meta" / f"{name}.json"
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({"content_type": content_type, "bytes": len(data)}), encoding="utf-8")

        await asyncio.to_thread(write)
        return f"artifact://{task_id}/{name}"

    async def get(self, ref: str) -> bytes:
        path = self._parse(ref)
        if not path.is_file():
            raise KairosError("ARTIFACT_NOT_FOUND", ref)
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, ref: str) -> bool:
        return self._parse(ref).is_file()

    async def list(self, task_id: str) -> list[str]:
        base = self.root / task_id
        if not _SAFE_TASK.match(task_id) or not base.is_dir():
            return []
        files = [p for p in base.rglob("*") if p.is_file() and ".meta" not in p.relative_to(base).parts]
        return sorted(f"artifact://{task_id}/{p.relative_to(base).as_posix()}" for p in files)

    def content_type(self, ref: str) -> str:
        m = _REF.match(ref)
        if not m:
            return "application/octet-stream"
        meta = self.root / m["task"] / ".meta" / f"{m['name']}.json"
        try:
            return json.loads(meta.read_text(encoding="utf-8"))["content_type"]
        except (OSError, ValueError, KeyError):
            return "application/octet-stream"
