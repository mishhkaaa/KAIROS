"""Helpers shared by all converters."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, OKFDraft, OKFFrontmatter
from kairos_contracts.util import okf_file_to_org_path

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_DATE_FIELDS = ("created_at", "updated_at")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def target_rel(req: IngestRequest) -> str:
    # KnowledgePath's pattern admits ".." segments, so the target is checked like every other segment
    rel = req.target_path.removeprefix("/org").strip("/")
    return "/".join(safe_segment(s) for s in rel.split("/")) if rel else ""


_UNSAFE = re.compile(r"[^A-Za-z0-9._\-]+")


def safe_segment(segment: str) -> str:
    """One path segment valid in a KnowledgePath; '.'/'..' (traversal) and empty segments are rejected."""
    seg = _UNSAFE.sub("-", segment.strip()).strip("-")
    if seg in ("", ".", "..") or segment.strip() in (".", ".."):
        raise KairosError("BAD_REQUEST", f"unsafe path segment {segment!r}")
    return seg


def okf_path(req: IngestRequest, *parts: str) -> str:
    """Bundle-relative .md path under the request target. Every segment is sanitised, so the result never escapes."""
    segments = [safe_segment(s) for p in parts if p for s in p.replace("\\", "/").split("/")]
    return "/".join(s for s in (target_rel(req), *segments) if s) + ".md"


def org_path(okf_file: str) -> str:
    return okf_file_to_org_path(okf_file)


def require_path(req: IngestRequest) -> Path:
    p = Path(req.uri)
    if not p.exists():
        raise KairosError("BAD_REQUEST", f"no such file or directory: {req.uri}")
    return p


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise KairosError("BAD_REQUEST", f"cannot read {path}: {e}") from e


def parse_frontmatter(text: str, source: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise KairosError("BAD_REQUEST", f"invalid YAML frontmatter in {source}: {e}") from e
    if not isinstance(fm, dict):
        raise KairosError("BAD_REQUEST", f"frontmatter in {source} is not a mapping")
    return fm, text[m.end():].lstrip("\r\n")


def to_utc(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    try:
        return to_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def draft(req: IngestRequest, okf_file: str, body: str, source_ref: str | None, **fm: Any) -> OKFDraft:
    """Converter defaults, overridden by request.options["frontmatter"] (e.g. {"privacy": "confidential"})."""
    merged = {k: v for k, v in fm.items() if v is not None}
    merged.update(req.options.get("frontmatter") or {})
    for key in _DATE_FIELDS:
        if key in merged:
            merged[key] = to_utc(merged[key])
            if merged[key] is None:
                del merged[key]
    try:
        frontmatter = OKFFrontmatter.model_validate(merged)
    except ValueError as e:
        raise KairosError("BAD_REQUEST", f"invalid frontmatter for {okf_file}: {e}") from e
    return OKFDraft(okf_file=okf_file, frontmatter=frontmatter, body=body.rstrip() + "\n", source_ref=source_ref)
