"""Slack export directory (<channel>/<YYYY-MM-DD>.json [+ users.json]) -> one OKF note per channel-day."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft

from .base import draft, okf_path, read_text, require_path

_DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
_SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_purpose", "channel_topic"}
_MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]*)?>")
_LINK = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")
_BARE_LINK = re.compile(r"<(https?://[^|>]+)>")


def _day_files(root: Path) -> list[Path]:
    return sorted(f for d in root.iterdir() if d.is_dir() for f in d.iterdir() if f.is_file() and _DAY_FILE.match(f.name))


def _load_json(path: Path) -> Any:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise KairosError("BAD_REQUEST", f"invalid JSON in {path}: {e}") from e


def _users(root: Path) -> dict[str, str]:
    f = root / "users.json"
    if not f.is_file():
        return {}
    out = {}
    for u in _load_json(f) or []:
        if isinstance(u, dict) and u.get("id"):
            prof = u.get("profile") or {}
            out[u["id"]] = prof.get("display_name") or u.get("real_name") or prof.get("real_name") or u.get("name") or u["id"]
    return out


def _clean(text: str, users: dict[str, str]) -> str:
    text = _MENTION.sub(lambda m: "@" + users.get(m.group(1), m.group(1)), text)
    text = _BARE_LINK.sub(r"\1", _LINK.sub(r"[\2](\1)", text))
    return " ".join(text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").split())


def _ts(msg: dict[str, Any]) -> float:
    try:
        return float(msg.get("ts") or 0)
    except (TypeError, ValueError):
        return 0.0


def _when(ts: float) -> datetime:
    return datetime.fromtimestamp(int(ts), UTC)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class SlackConverter:
    name = "slack-export"
    source_types = [IngestSourceType.DIRECTORY]

    def can_convert(self, request: IngestRequest) -> bool:
        p = Path(request.uri)
        return p.is_dir() and bool(_day_files(p))

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        root = require_path(request)
        if not root.is_dir():
            raise KairosError("BAD_REQUEST", f"{root} is not a Slack export directory")
        users = _users(root)
        drafts = []
        for f in _day_files(root):
            channel, day = f.parent.name, f.stem
            raw = _load_json(f)
            if not isinstance(raw, list):
                raise KairosError("BAD_REQUEST", f"{f} is not a list of messages")
            msgs = sorted((m for m in raw if isinstance(m, dict) and m.get("subtype") not in _SKIP_SUBTYPES and m.get("text")),
                          key=_ts)
            if not msgs:
                continue
            threads: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for m in msgs:
                threads[str(m.get("thread_ts") or m.get("ts"))].append(m)
            lines = [f"# #{channel} {day}"]
            for thread in threads.values():
                lines += ["", f"## Thread {_when(_ts(thread[0])):%H:%M} UTC", ""]
                for m in thread:
                    uid = m.get("user") or ""
                    who = users.get(uid) or m.get("user_name") or uid or "unknown"
                    lines.append(f"- **{who}** ({_when(_ts(m)):%H:%M}): {_clean(m['text'], users)}")
            drafts.append(draft(request, okf_path(request, channel, day), "\n".join(lines), str(f),
                                type="note", title=f"#{channel} {day}",
                                description=f"Slack #{channel} on {day}: {_plural(len(msgs), 'message')} in {_plural(len(threads), 'thread')}",
                                tags=["slack", channel], source="slack", source_version=day,
                                created_at=_when(_ts(msgs[0])), trust="unverified"))
        if not drafts:
            raise KairosError("BAD_REQUEST", f"{root} contains no Slack messages")
        return drafts
