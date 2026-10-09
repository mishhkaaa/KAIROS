"""Convert data/raw/* exports into data/okf with P4's converters (deterministic, re-runnable).

    uv run python scripts/ingest_raw.py

Writes drafts straight into the bundle. Once P2's pipeline is live, `kairos-okf ingest` / POST /knowledge/ingest
does the same through the knowledge service (write + validate + index + knowledge.changed events).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_knowledge.ingestion.factory import build_converters

ROOT = Path(__file__).resolve().parents[1]
RAW, OKF = ROOT / "data" / "raw", ROOT / "data" / "okf"

JOBS = [
    (IngestSourceType.FILE, RAW / "jira" / "apollo-export.json", "/org/jira", {}),
    (IngestSourceType.DIRECTORY, RAW / "slack", "/org/slack", {}),
    (IngestSourceType.FILE, RAW / "finance" / "q3-forecast.csv", "/org/finance",
     {"title": "Q3 forecast", "type": "finance", "trust": "verified",
      "frontmatter": {"owner": "meera", "tags": ["finance", "forecast", "q3", "apollo"], "source": "finance-sheet",
                      "source_version": "FY26-Q3-v7", "updated_at": "2026-09-18T12:00:00Z",
                      "description": "Q3 budget, actuals and forecast per project (Apollo 38% over at quarter end)"}}),
]


def render(d: OKFDraft) -> str:
    fm = d.frontmatter.model_dump(mode="json", exclude_none=True)
    fm = {k: v for k, v in fm.items() if v != []}
    return f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000).strip()}\n---\n\n{d.body.strip()}\n"


async def main() -> None:
    s = Settings()
    converters = build_converters(s, ServiceBundle(settings=s))
    for source_type, uri, target, options in JOBS:
        req = IngestRequest(source_type=source_type, uri=str(uri), target_path=target, options=options)
        conv = next((c for c in converters if c.can_convert(req)), None)
        if conv is None:
            raise SystemExit(f"no converter for {uri}")
        drafts = await conv.convert(req)
        for d in drafts:
            out = (OKF / d.okf_file).resolve()
            if not out.is_relative_to(OKF.resolve()):
                raise SystemExit(f"refusing to write outside the bundle: {d.okf_file}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(d), encoding="utf-8", newline="\n")
        print(f"{conv.name:13} {uri.relative_to(ROOT)} -> {target} ({len(drafts)} files)")


if __name__ == "__main__":
    asyncio.run(main())
