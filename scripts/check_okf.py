"""Check the demo bundle (P4): valid OKF, no broken links, size target, QA paths exist, must-have facts are corroborated.

    uv run python scripts/check_okf.py            # M3 target: >= 60 files
    uv run python scripts/check_okf.py --min 30   # M1 gate
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import yaml
from kairos_contracts.testing.fakes import FakeKnowledgeService

ROOT = Path(__file__).resolve().parents[1]
OKF, QA = ROOT / "data" / "okf", ROOT / "data" / "qa.yaml"

# Each must-have fact (P4 brief §6.6) must be backed by >= 2 documents: every pattern of a fact must match the file.
FACTS = {
    "cloud cost doubled by ADR-042 dual-run": [r"dual-run|dual-running|both (reconciliation )?pipelines", r"doubl"],
    "backfill failed on duplicate reconciliation ids": [r"backfill", r"dup(licate)?s? recon(ciliation)? ids?"],
    "SDK v5 blocked on certification": [r"SDK v5|v5 SDK", r"certification"],
    "emergency support contract": [r"emergency (SDK v5 migration )?support", r"contract"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=60, help="minimum number of OKF files")
    args = ap.parse_args()
    problems: list[str] = []

    ks = FakeKnowledgeService(OKF)  # raises if any file has invalid frontmatter
    report = asyncio.run(ks.validate())
    for issue in report.issues:
        if issue.severity == "error":
            problems.append(f"{issue.okf_file}: {issue.message}")
        else:
            print(f"warning  {issue.okf_file}: {issue.message}")
    if report.files_checked < args.min:
        problems.append(f"only {report.files_checked} files (need >= {args.min})")

    for q in yaml.safe_load(QA.read_text(encoding="utf-8"))["questions"]:
        for path in q["expected"]:
            if path not in ks.objects:
                problems.append(f"qa.yaml: {path} does not exist ({q['q']})")

    texts = {p: f"{o.frontmatter.title}\n{o.body}" for p, o in ks.objects.items()}
    for fact, patterns in FACTS.items():
        hits = [p for p, t in texts.items() if all(re.search(rx, t, re.IGNORECASE) for rx in patterns)]
        print(f"fact     {fact}: {len(hits)} docs")
        if len(hits) < 2:
            problems.append(f"fact '{fact}' backed by {len(hits)} document(s), need >= 2")

    print(f"checked  {report.files_checked} files")
    if problems:
        raise SystemExit("FAIL\n  " + "\n  ".join(problems))
    print("OK")


if __name__ == "__main__":
    main()
