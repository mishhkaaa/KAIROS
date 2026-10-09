# data/: the demo organization (P4 authors, P2 reviews retrieval quality)

| Path | What |
|---|---|
| `okf/` | The demo OKF bundle, "Acme / Project Apollo" (73 files). Point the system at it with `KAIROS_OKF_DIR=./data/okf`. |
| `raw/` | Source exports: Jira JSON, Slack export and a CSV. `uv run python scripts/ingest_raw.py` converts them into `okf/jira`, `okf/slack` and `okf/finance/q3-forecast.md`. |
| `qa.yaml` | 10 retrieval questions with expected top-3 paths (P2 turns them into a test). It lives outside `okf/` so the questions never become retrievable knowledge. |
| `demo-assets/security-policy-v2.md` | Dropped into `okf/policies/security.md` live for the invalidation demo. Keep it outside the bundle. |

Check the bundle with `uv run python scripts/check_okf.py`. It checks valid frontmatter, no broken links, ≥ 60 files, that every QA path exists, and that each must-have fact appears in ≥ 2 documents.

**Do not edit `shared/fixtures/okf/`.** That bundle is frozen test data that everyone's contract tests depend on. `okf/` started as a copy of it.

## Conventions
- One concept per file.
- YAML frontmatter valid as `OKFFrontmatter`: `type, title, description, tags, owner, privacy, trust, source, updated_at` (full ISO timestamps `2026-09-18T12:00:00Z`), and `related` (`/org/...` paths).
- An `index.md` per directory, and relative Markdown links between concepts.
- No non-OKF Markdown inside `okf/` (READMEs etc.): the loader rejects files without frontmatter.

## Canonical facts (every document must agree)
- Apollo go-live was planned for **2026-08-15**. The forecast is **2026-09-26**: six weeks late.
- Budget is **20.0 lakh**, actual is **26.2 lakh**: **31% over** (6.2 lakh).
  - Engineering 12.0 → 14.5: migration rework.
  - Cloud 5.0 → 6.9: 7 weeks of ADR-042 dual-run at ≈ 0.27 lakh/week. Monthly: Apr–Jul 3.2, Aug 2.3, Sep to the 18th 1.4.
  - Vendor licences 3.0 → 4.8: PayCo emergency support contract, 1.8 lakh, signed 2026-08-02, CFO-approved.
- APOLLO-12 (ledger migration, Priya) was due 2026-08-01. Backfill attempt #1 on 2026-07-30 and attempt #2 on 2026-09-12 both failed on **duplicate reconciliation ids** (legacy retries reused ids; the ADR-039 schema enforces a unique `recon_id`). The fix is APOLLO-14 (Rahul).
- ADR-042: the legacy pipeline runs until **14 consecutive parity days**. Parity is at 0 days, because the backfill has not succeeded.
- APOLLO-31 (PayCo SDK v5, Marco) is blocked on PayCo's **PCI certification**. v5 GA is now **2026-10-20** (vendor-docs site); v4 is supported until 2027-03-31.
- People:
  - Priya Sharma: Apollo lead
  - Marco Rossi: Zeus lead + PayCo SDK owner
  - Rahul Verma: data engineer
  - Sara Khan: SRE
  - Ananya Rao: finance analyst
  - Meera Iyer: CFO
  - Vikram Mehta: CTO
  - Deepak Nair: procurement
  - Li Wei: security
- Distractors: Zeus, Hermes and Atlas are on track or on budget; Iris is paused.
- Privacy: `finance/payroll-2026` is confidential.
- Firewall demo: `inbox/vendor-email-2026-09-12` contains the injected instruction.
