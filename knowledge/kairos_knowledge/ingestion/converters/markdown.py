"""Markdown file or directory -> OKF notes. Existing frontmatter is kept; missing fields are filled."""
from __future__ import annotations

import re
from pathlib import Path

from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft

from .base import draft, okf_path, parse_frontmatter, read_text, require_path

_HEADING = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _description(body: str) -> str | None:
    for block in re.split(r"\n\s*\n", body):
        text = block.strip()
        if not text or text.startswith(("#", "|", "```", "<!--", "---", ">")):
            continue
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_`]", "", re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE))
        text = " ".join(text.split())
        return text if len(text) <= 160 else text[:157].rsplit(" ", 1)[0] + "..."
    return None


class MarkdownConverter:
    name = "markdown"
    source_types = [IngestSourceType.FILE, IngestSourceType.DIRECTORY]

    def can_convert(self, request: IngestRequest) -> bool:
        p = Path(request.uri)
        if p.is_file():
            return p.suffix.lower() == ".md"
        return p.is_dir() and next(p.rglob("*.md"), None) is not None

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        src = require_path(request)
        files = [src] if src.is_file() else sorted(src.rglob("*.md"))
        trust = request.options.get("trust", "unverified")
        drafts = []
        for f in files:
            fm, body = parse_frontmatter(read_text(f), str(f))
            heading = _HEADING.search(body)
            fm.setdefault("type", "note")
            fm.setdefault("title", heading.group(1) if heading else f.stem.replace("-", " ").replace("_", " ").title())
            if not fm.get("description"):
                fm["description"] = _description(body)
            fm.setdefault("source", "markdown")
            fm.setdefault("trust", trust)
            rel = f.stem if src.is_file() else f.relative_to(src).with_suffix("").as_posix()
            drafts.append(draft(request, okf_path(request, rel), body, str(f), **fm))
        return drafts
