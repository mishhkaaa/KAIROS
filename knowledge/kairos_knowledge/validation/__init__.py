"""OKF linter.

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] frontmatter validates as OKFFrontmatter; required title/type/description
  - [x] broken links, orphan files, duplicate titles, missing index.md per directory
"""

from __future__ import annotations

import posixpath
from collections import defaultdict

from kairos_contracts.schema import OKFFrontmatter, ValidationIssue, ValidationReport
from kairos_contracts.util import okf_file_to_org_path
from pydantic import ValidationError

from ..okf import OKFBundle, _default_title, parse_okf


def validate_bundle(bundle: OKFBundle) -> ValidationReport:
    issues: list[ValidationIssue] = []
    files_checked = 0
    parsed: dict[str, tuple[OKFFrontmatter, str]] = {}
    org_path_owners: dict[str, list[str]] = defaultdict(list)

    if not bundle.root.exists():
        return ValidationReport(ok=True, files_checked=0, issues=[])

    for f in sorted(bundle.root.rglob("*.md")):
        rel = f.relative_to(bundle.root).as_posix()
        if rel.lower() == "readme.md":
            continue
        files_checked += 1
        text = f.read_text(encoding="utf-8")
        fm_raw, body = parse_okf(text)
        fm_raw = dict(fm_raw)
        fm_raw.setdefault("type", "note")
        fm_raw.setdefault("title", _default_title(rel, body))
        try:
            fm = OKFFrontmatter.model_validate(fm_raw)
        except ValidationError as e:
            issues.append(ValidationIssue(okf_file=rel, severity="error", message=f"invalid frontmatter: {e}"))
            continue
        if not fm.description:
            issues.append(ValidationIssue(okf_file=rel, severity="warning", message="missing description"))
        parsed[rel] = (fm, body)
        org_path_owners[okf_file_to_org_path(rel)].append(rel)

    for org_path, owners in org_path_owners.items():
        if len(owners) > 1:
            for rel in owners:
                issues.append(
                    ValidationIssue(
                        okf_file=rel,
                        severity="error",
                        message=f"duplicate path {org_path} (also {[o for o in owners if o != rel]})",
                    )
                )

    titles: dict[str, list[str]] = defaultdict(list)
    for rel, (fm, _body) in parsed.items():
        titles[fm.title].append(rel)
    for title, files in titles.items():
        if len(files) > 1:
            for rel in files:
                issues.append(ValidationIssue(okf_file=rel, severity="warning", message=f"duplicate title {title!r}"))

    org_paths = {okf_file_to_org_path(rel) for rel in parsed}
    inbound: dict[str, int] = dict.fromkeys(org_paths, 0)
    for rel, (fm, body) in parsed.items():
        for link in bundle._resolve_links(rel, body, fm):
            if link not in org_paths:
                issues.append(ValidationIssue(okf_file=rel, severity="error", message=f"broken link {link}"))
            elif link in inbound:
                inbound[link] += 1

    dirs_with_files = {posixpath.dirname(rel) for rel in parsed}
    dirs_with_index = {posixpath.dirname(rel) for rel in parsed if posixpath.basename(rel) == "index.md"}
    for d in sorted(dirs_with_files):
        if d and d not in dirs_with_index:
            issues.append(ValidationIssue(okf_file=d or ".", severity="warning", message="directory missing index.md"))

    for rel in parsed:
        org_path = okf_file_to_org_path(rel)
        if posixpath.basename(rel) != "index.md" and inbound.get(org_path, 0) == 0:
            issues.append(ValidationIssue(okf_file=rel, severity="warning", message="orphan file (no inbound links)"))

    ok = not any(i.severity == "error" for i in issues)
    return ValidationReport(ok=ok, files_checked=files_checked, issues=issues)


__all__ = ["validate_bundle"]
