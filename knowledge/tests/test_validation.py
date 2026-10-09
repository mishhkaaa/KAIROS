"""OKF linter rules. No Postgres needed."""

from kairos_contracts.testing.fakes import FIXTURE_OKF_DIR
from kairos_knowledge.okf import OKFBundle
from kairos_knowledge.validation import validate_bundle


def test_fixtures_have_no_errors():
    report = validate_bundle(OKFBundle(FIXTURE_OKF_DIR))
    assert report.ok and report.files_checked == 13
    assert not [i for i in report.issues if i.severity == "error"]


def _messages(report, severity):
    return [(i.okf_file, i.message) for i in report.issues if i.severity == severity]


def test_error_rules(tmp_path):
    (tmp_path / "index.md").write_text("---\ntype: index\ntitle: Root\ndescription: d\n---\n[a](a.md)\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("---\ntype: note\ntitle: A\ndescription: d\n---\n[gone](missing.md)\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("---\ntype: note\ntitle: Bad\nprivacy: top-secret\n---\nx\n", encoding="utf-8")
    (tmp_path / "dup").mkdir()
    (tmp_path / "dup.md").write_text("---\ntype: note\ntitle: Dup\ndescription: d\n---\nx\n", encoding="utf-8")
    (tmp_path / "dup" / "index.md").write_text("---\ntype: index\ntitle: Dup dir\ndescription: d\n---\nx\n", encoding="utf-8")

    report = validate_bundle(OKFBundle(tmp_path))
    errors = _messages(report, "error")
    assert not report.ok
    assert any(f == "a.md" and "broken link /org/missing" in m for f, m in errors)
    assert any(f == "bad.md" and "invalid frontmatter" in m for f, m in errors)
    assert {f for f, m in errors if "duplicate path /org/dup" in m} == {"dup.md", "dup/index.md"}


def test_warning_rules(tmp_path):
    (tmp_path / "index.md").write_text("---\ntype: index\ntitle: Same\ndescription: d\n---\n[b](sub/b.md)\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("---\ntype: note\ntitle: Same\n---\nx\n", encoding="utf-8")
    (tmp_path / "orphan.md").write_text("---\ntype: note\ntitle: Lonely\ndescription: d\n---\nx\n", encoding="utf-8")

    report = validate_bundle(OKFBundle(tmp_path))
    warnings = _messages(report, "warning")
    assert report.ok
    assert ("sub/b.md", "missing description") in warnings
    assert ("sub", "directory missing index.md") in warnings
    assert ("orphan.md", "orphan file (no inbound links)") in warnings
    assert sum("duplicate title 'Same'" in m for _, m in warnings) == 2
