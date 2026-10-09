"""P4 unit tests for converter edge cases (the contract suite covers the happy path per converter)."""
import asyncio
import json
from pathlib import Path

import pytest
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, IngestSourceType
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_knowledge.ingestion.converters import CsvConverter, JiraJsonConverter, MarkdownConverter, SlackConverter
from kairos_knowledge.ingestion.factory import build_converters

SAMPLES = Path(__file__).parent / "samples"


def req(uri, source_type=IngestSourceType.FILE, target="/org/imported", **options):
    return IngestRequest(source_type=source_type, uri=str(uri), target_path=target, options=options)


def run(coro):
    return asyncio.run(coro)


def pick(r):
    s = Settings()
    return next(c.name for c in build_converters(s, ServiceBundle(settings=s)) if c.can_convert(r))


def test_factory_priority_routes_each_sample():
    assert pick(req(SAMPLES / "slack-export", IngestSourceType.DIRECTORY)) == "slack-export"
    assert pick(req(SAMPLES / "markdown", IngestSourceType.DIRECTORY)) == "markdown"
    assert pick(req(SAMPLES / "jira-export.json")) == "jira-json"
    assert pick(req(SAMPLES / "budget.csv")) == "csv"


def test_jira_null_assignee_adf_and_links(tmp_path):
    export = {"issues": [
        {"key": "APOLLO-14", "fields": {"summary": "Dedupe recon ids", "status": None, "assignee": None,
                                        "updated": "2026-09-10T08:30:00.000+0000",
                                        "issuelinks": [{"outwardIssue": {"key": "APOLLO-12"}}, {"inwardIssue": {"key": "X-1"}}],
                                        "description": {"type": "doc", "content": [
                                            {"type": "paragraph", "content": [{"type": "text", "text": "Two ids collide."}]}]},
                                        "comment": {"comments": [{"author": {"displayName": "Rahul"}, "created": "2026-09-11",
                                                                  "body": "Fixed | verified"}]}}},
        {"key": "APOLLO-12", "fields": {"summary": "Migration"}}]}
    f = tmp_path / "export.json"
    f.write_text(json.dumps(export), encoding="utf-8")
    drafts = {d.okf_file: d for d in run(JiraJsonConverter().convert(req(f)))}
    d = drafts["imported/apollo-14.md"]
    assert "Two ids collide." in d.body and "**Rahul**" in d.body
    assert d.frontmatter.status == "unknown" and d.frontmatter.owner is None
    assert d.frontmatter.related == ["/org/imported/apollo-12"]
    assert d.frontmatter.updated_at.year == 2026 and d.frontmatter.updated_at.utcoffset().total_seconds() == 0
    assert drafts["imported/index.md"].frontmatter.type == "index"


def test_jira_rejects_non_export(tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"issues": 3}', encoding="utf-8")
    with pytest.raises(KairosError) as ei:
        run(JiraJsonConverter().convert(req(f)))
    assert ei.value.code == "BAD_REQUEST"


def test_slack_users_mentions_links_and_threads(tmp_path):
    (tmp_path / "users.json").write_text(json.dumps([{"id": "U1", "real_name": "Priya"}, {"id": "U2", "name": "marco"}]))
    ch = tmp_path / "apollo-eng"
    ch.mkdir()
    (ch / "2026-09-12.json").write_text(json.dumps([
        {"user": "U2", "ts": "1757667900.2", "thread_ts": "1757667600.1", "text": "ok <@U1>, see <https://x.io/a|doc>"},
        {"user": "U1", "ts": "1757667600.1", "thread_ts": "1757667600.1", "text": "backfill failed"},
        {"user": "U1", "ts": "1757670000.3", "subtype": "channel_join", "text": "joined"},
        {"user": "U1", "ts": "1757671000.4", "text": "separate topic"}]))
    (d,) = run(SlackConverter().convert(req(tmp_path, IngestSourceType.DIRECTORY)))
    assert d.okf_file == "imported/apollo-eng/2026-09-12.md"
    assert d.body.count("## Thread") == 2 and "joined" not in d.body
    assert "**marco**" in d.body and "@Priya" in d.body and "[doc](https://x.io/a)" in d.body
    assert d.body.index("backfill failed") < d.body.index("ok @Priya")


def test_csv_bom_pipes_and_type_option(tmp_path):
    f = tmp_path / "cloud-bill.csv"
    f.write_text("﻿service,cost\nrecon|compute,0.9\n", encoding="utf-8")
    (d,) = run(CsvConverter().convert(req(f)))
    assert d.frontmatter.type == "finance" and "service" in d.frontmatter.description
    assert "recon\\|compute" in d.body and "﻿" not in d.body
    (d2,) = run(CsvConverter().convert(req(f, type="note", frontmatter={"privacy": "confidential"})))
    assert d2.frontmatter.type == "note" and d2.frontmatter.privacy == "confidential"


def test_markdown_keeps_frontmatter_and_normalises_dates(tmp_path):
    f = tmp_path / "adr.md"
    f.write_text("---\ntype: decision\ntitle: ADR-1\nupdated_at: 2026-09-01\n---\n# Heading\n\nBody text here.\n", encoding="utf-8")
    (d,) = run(MarkdownConverter().convert(req(f)))
    assert d.frontmatter.type == "decision" and d.frontmatter.title == "ADR-1"
    assert d.frontmatter.description == "Body text here." and d.frontmatter.updated_at.tzinfo is not None
    assert d.okf_file == "imported/adr.md"


def test_markdown_bad_yaml_is_bad_request(tmp_path):
    f = tmp_path / "bad.md"
    f.write_text("---\ntitle: [unclosed\n---\nbody\n", encoding="utf-8")
    with pytest.raises(KairosError) as ei:
        run(MarkdownConverter().convert(req(f)))
    assert ei.value.code == "BAD_REQUEST"


def test_jira_traversal_key_is_skipped(tmp_path):
    f = tmp_path / "export.json"
    f.write_text(json.dumps({"issues": [{"key": "../../outside", "fields": {}}, {"key": "APOLLO-1", "fields": {}}]}))
    files = sorted(d.okf_file for d in run(JiraJsonConverter().convert(req(f))))
    assert files == ["imported/apollo-1.md", "imported/index.md"]


def test_paths_are_sanitised_and_never_escape(tmp_path):
    (tmp_path / "My Notes (v2).md").write_text("# Notes\n\nText.\n", encoding="utf-8")
    (d,) = run(MarkdownConverter().convert(req(tmp_path, IngestSourceType.DIRECTORY)))
    assert d.okf_file == "imported/My-Notes-v2.md"
    with pytest.raises(KairosError) as ei:
        run(MarkdownConverter().convert(req(tmp_path, IngestSourceType.DIRECTORY, target="/org/../etc")))
    assert ei.value.code == "BAD_REQUEST"
