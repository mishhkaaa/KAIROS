"""OKFBundle.write_draft: the draft's frontmatter is written as-is (no ingest-time stamps). No Postgres needed."""

from kairos_contracts.schema import ChangeKind, OKFDraft, OKFFrontmatter
from kairos_knowledge.okf import OKFBundle, parse_okf


def _draft(**fm) -> OKFDraft:
    return OKFDraft(okf_file="jira/apollo-12.md", frontmatter=OKFFrontmatter(type="note", title="APOLLO-12", **fm), body="Body.")


def test_source_timestamps_are_kept_and_none_are_invented(tmp_path):
    bundle = OKFBundle(tmp_path)
    bundle.write_draft(_draft(updated_at="2026-09-12T18:40:00Z", source="jira"))
    fm, body = parse_okf((tmp_path / "jira" / "apollo-12.md").read_text(encoding="utf-8"))
    assert fm["updated_at"] == "2026-09-12T18:40:00Z"
    assert "created_at" not in fm
    assert body.strip() == "Body."


def test_empty_values_are_not_written(tmp_path):
    OKFBundle(tmp_path).write_draft(_draft())
    fm, _ = parse_okf((tmp_path / "jira" / "apollo-12.md").read_text(encoding="utf-8"))
    assert "related" not in fm and "tags" not in fm and "description" not in fm


def test_rewrite_is_a_noop_and_an_edit_is_an_update(tmp_path):
    bundle = OKFBundle(tmp_path)
    first = bundle.write_draft(_draft(tags=["apollo"]))
    again = bundle.write_draft(_draft(tags=["apollo"]))
    edited = bundle.write_draft(_draft(tags=["apollo", "blocked"]))
    assert first.change == ChangeKind.CREATED and first.old_hash is None
    assert again.old_hash == again.new_hash
    assert edited.change == ChangeKind.UPDATED and edited.old_hash != edited.new_hash
