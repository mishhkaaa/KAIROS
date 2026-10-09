"""OKF bundle I/O: parse/serialize Markdown + YAML frontmatter, resolve links, map /org paths <-> files.

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] loader over settings.okf_dir using kairos_contracts.util.okf_file_to_org_path
  - [x] writer that preserves unknown frontmatter keys (OKF is extensible)
  - [ ] git-backed versioning: content_hash + version, diffable changes
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from pathlib import Path
from typing import Any

import yaml
from kairos_contracts.schema import ChangeKind, KnowledgeChange, KnowledgeObject, OKFDraft, OKFFrontmatter, Provenance
from kairos_contracts.util import okf_file_to_org_path

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)\)")
_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse_okf(text: str) -> tuple[dict[str, Any], str]:
    """Tolerant OKF parser: no (or malformed) frontmatter still returns something usable."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            _, fm_raw, body = parts
            try:
                fm = yaml.safe_load(fm_raw) or {}
            except yaml.YAMLError:
                fm = {}
            if isinstance(fm, dict):
                return fm, body.lstrip("\n")
    return {}, text


def _default_title(rel: str, body: str) -> str:
    m = _HEADING_RE.search(body)
    if m:
        return m.group(1).strip()
    return Path(rel).stem


def _serialize_frontmatter(fm: OKFFrontmatter) -> str:
    data = {k: v for k, v in fm.model_dump(mode="json", exclude_none=True).items() if v not in ([], {}, "")}
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True, width=1000)


class OKFBundle:
    """Loads and writes the on-disk OKF Markdown bundle rooted at `root`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def load_all(self) -> dict[str, KnowledgeObject]:
        objects: dict[str, KnowledgeObject] = {}
        if not self.root.exists():
            return objects
        for f in sorted(self.root.rglob("*.md")):
            rel = f.relative_to(self.root).as_posix()
            if rel.lower() == "readme.md":
                continue
            text = f.read_text(encoding="utf-8")
            obj = self._to_object(rel, text)
            objects[obj.path] = obj
        return objects

    def _to_object(self, rel: str, text: str) -> KnowledgeObject:
        fm_raw, body = parse_okf(text)
        fm_raw = dict(fm_raw)
        fm_raw.setdefault("type", "note")
        fm_raw.setdefault("title", _default_title(rel, body))
        fm = OKFFrontmatter.model_validate(fm_raw)
        links = self._resolve_links(rel, body, fm)
        return KnowledgeObject(
            path=okf_file_to_org_path(rel),
            okf_file=rel,
            frontmatter=fm,
            body=body,
            links=links,
            provenance=Provenance(
                source=fm.source or "okf",
                source_ref=rel,
                source_version=fm.source_version,
                created_at=fm.created_at,
                updated_at=fm.updated_at,
                author=fm.author,
                generator=fm.generator,
                verification_status=fm.verification_status,
                trust=fm.trust,
            ),
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        )

    def _resolve_links(self, rel: str, body: str, fm: OKFFrontmatter) -> list[str]:
        links: set[str] = set()
        base_dir = posixpath.dirname(rel)
        for target in _LINK_RE.findall(body):
            resolved = posixpath.normpath(posixpath.join(base_dir, target))
            links.add(okf_file_to_org_path(resolved))
        for r in fm.related:
            if r.startswith("/org"):
                links.add(r.rstrip("/"))
            elif r.endswith(".md"):
                resolved = posixpath.normpath(posixpath.join(base_dir, r))
                links.add(okf_file_to_org_path(resolved))
        return sorted(links)

    def read_text(self, okf_file: str) -> str | None:
        p = self.root / okf_file
        return p.read_text(encoding="utf-8") if p.exists() else None

    def write_draft(self, draft: OKFDraft) -> KnowledgeChange:
        """Create or update one OKF file with exactly the draft's frontmatter: its timestamps are the source's
        (provenance), so nothing is stamped here. An unchanged draft is not rewritten and comes back with
        old_hash == new_hash, which callers treat as "skipped"."""
        path = self.root / draft.okf_file
        org_path = okf_file_to_org_path(draft.okf_file)
        old_hash = None
        if path.exists():
            old_text = path.read_text(encoding="utf-8")
            old_hash = _hash(old_text)
            old_fm_raw, old_body = parse_okf(old_text)
            try:
                old_fm = OKFFrontmatter.model_validate({"type": "note", "title": "", **old_fm_raw})
            except ValueError:
                old_fm = None
            if old_fm is not None and old_fm == draft.frontmatter and old_body.strip() == draft.body.strip():
                return KnowledgeChange(path=org_path, change=ChangeKind.UPDATED, old_hash=old_hash, new_hash=old_hash)
        text = f"---\n{_serialize_frontmatter(draft.frontmatter)}---\n\n{draft.body.strip()}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")  # LF on every OS, so content hashes match
        return KnowledgeChange(
            path=org_path,
            change=ChangeKind.UPDATED if old_hash else ChangeKind.CREATED,
            old_hash=old_hash,
            new_hash=_hash(text),
        )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


__all__ = ["OKFBundle", "parse_okf"]
