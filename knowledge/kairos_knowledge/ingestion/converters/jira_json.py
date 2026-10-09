"""Jira JSON export ({"issues": [...]}, REST v2 or v3/ADF) -> one OKF note per issue + an index."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft

from .base import draft, okf_path, org_path, read_text, require_path

log = logging.getLogger("kairos.knowledge.ingestion.jira_json")
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")  # Jira issue key, e.g. APOLLO-12; also keeps file paths safe
_BLOCKS = {"paragraph", "heading", "listItem", "codeBlock", "blockquote"}


def adf_text(node: Any) -> str:
    """Flatten Atlassian Document Format (v3 API) to plain text; strings pass through."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") == "hardBreak":
            return "\n"
        inner = adf_text(node.get("content"))
        return inner.rstrip("\n") + "\n\n" if node.get("type") in _BLOCKS else inner
    return str(node)


def _field(obj: Any, key: str = "name", default: str = "-") -> str:
    if isinstance(obj, dict):
        return str(obj.get(key) or default)
    return str(obj) if obj else default


class JiraJsonConverter:
    name = "jira-json"
    source_types = [IngestSourceType.FILE, IngestSourceType.API]

    def can_convert(self, request: IngestRequest) -> bool:
        p = Path(request.uri)
        if not (p.is_file() and p.suffix.lower() == ".json"):
            return False
        try:
            with p.open(encoding="utf-8-sig") as fh:
                return '"issues"' in fh.read(4096)
        except (OSError, UnicodeDecodeError):
            return False

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        src = require_path(request)
        try:
            data = json.loads(read_text(src))
        except json.JSONDecodeError as e:
            raise KairosError("BAD_REQUEST", f"invalid JSON in {src}: {e}") from e
        issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues, list):
            raise KairosError("BAD_REQUEST", f"{src} is not a Jira export (no 'issues' list)")
        valid = []
        for i in issues:
            key = i.get("key") if isinstance(i, dict) else None
            if isinstance(key, str) and _KEY.match(key):
                valid.append(i)
            else:
                log.warning("skipping issue with invalid key %r in %s", key, src)
        issues = valid
        keys = {i["key"] for i in issues}
        drafts, rows = [], []
        for issue in issues:
            key, f = issue["key"], issue.get("fields") or {}
            summary = f.get("summary") or ""
            status = _field(f.get("status"), default="unknown")
            assignee = _field(f.get("assignee"), "displayName")
            labels = [str(x) for x in f.get("labels") or []]
            links = []
            for link in f.get("issuelinks") or []:
                other = link.get("outwardIssue") or link.get("inwardIssue") or {}
                if other.get("key") in keys and other["key"] not in links:
                    links.append(other["key"])
            lines = [f"# {key}: {summary}", "",
                     f"- **Status:** {status}", f"- **Assignee:** {assignee}",
                     f"- **Type:** {_field(f.get('issuetype'))}", f"- **Priority:** {_field(f.get('priority'))}",
                     f"- **Due:** {f.get('duedate') or '-'}"]
            if labels:
                lines.append(f"- **Labels:** {', '.join(labels)}")
            if links:
                lines.append("- **Linked:** " + ", ".join(f"[{k}]({k.lower()}.md)" for k in links))
            lines += ["", "## Description", "", adf_text(f.get("description")).strip() or "_No description._"]
            comments = (f.get("comment") or {}).get("comments") or []
            if comments:
                lines += ["", "## Comments", ""]
                for c in comments:
                    who = _field(c.get("author"), "displayName")
                    lines.append(f"- **{who}** ({str(c.get('created') or '')[:10]}): {' '.join(adf_text(c.get('body')).split())}")
            drafts.append(draft(request, okf_path(request, key.lower()), "\n".join(lines), key,
                                type="note", title=f"{key} {summary}".strip(), description=f"Jira issue {key} ({status})",
                                tags=["jira", *labels], status=status.lower(), owner=assignee if assignee != "-" else None,
                                source="jira", source_version=f.get("updated") or key, updated_at=f.get("updated"),
                                created_at=f.get("created"), trust="trusted",
                                related=[org_path(okf_path(request, k.lower())) for k in links]))
            rows.append(f"| [{key}]({key.lower()}.md) | {summary.replace('|', '/')} | {status} | {assignee} |")
        if not drafts:
            raise KairosError("BAD_REQUEST", f"{src} contains no issues")
        body = "\n".join(["# Jira issues", "", "| Key | Summary | Status | Assignee |", "|---|---|---|---|", *rows])
        drafts.append(draft(request, okf_path(request, "index"), body, str(src), type="index", title="Jira issues",
                            description=f"{len(rows)} issues imported from {src.name}", tags=["jira"], source="jira",
                            trust="trusted"))
        return drafts
