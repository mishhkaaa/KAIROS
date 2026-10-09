---
type: note
title: Reconciliation parity report
description: Parity status between legacy and new reconciliation pipelines
tags:
- apollo
- reconciliation
- parity
owner: sara
source: parity-dashboard
updated_at: '2026-09-18T20:00:00Z'
related:
- /org/decisions/ADR-042
- /org/systems/reconciliation-pipeline
privacy: internal
trust: trusted
---

# Reconciliation parity report

ADR-042 requires the new pipeline to match the legacy pipeline for **14 consecutive days** before the legacy
pipeline is decommissioned ([APOLLO-18](../jira/apollo-18.md)).

| Window | Matching days | Status |
|---|---|---|
| 2026-08-01 to 2026-08-31 | 0 | blocked: ledger not migrated |
| 2026-09-01 to 2026-09-18 | 0 | blocked: backfill failed again 2026-09-12 |

Parity cannot start until the ledger backfill succeeds, so the dual-run (and its cost) continues.
