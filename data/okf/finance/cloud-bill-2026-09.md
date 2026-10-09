---
type: finance
title: Cloud bill 2026-09 (Apollo, to date)
description: 'How much Apollo cloud spend increased in August and September: dual-run doubled reconciliation cost'
tags:
- apollo
- cloud
- cost
- bill
owner: ananya
source: cloud-billing-export
source_version: '2026-09-18'
updated_at: '2026-09-19T08:00:00Z'
trust: verified
related:
- /org/finance/apollo-budget
- /org/finance/cloud-bill-2026-08
privacy: internal
---

# Cloud bill: September 2026 to date (Apollo cost centre)

Period 2026-09-01 to 2026-09-18. Apollo cloud spend increased again in September, as it did in August.

| Line item | Actual (lakh) |
|---|---|
| Reconciliation compute, legacy pipeline | 0.70 |
| Reconciliation compute, new pipeline | 0.70 |
| **Total** | **1.40** |

Dual-running continues ([ADR-042](../decisions/ADR-042.md)): cloud cost for reconciliation stays at twice the plan
while the migration backfill is blocked. Cumulative Apollo cloud spend: **6.9 lakh vs 5.0 lakh budget** (7 weeks
of dual-run so far, about 0.27 lakh per week). See [Apollo budget](apollo-budget.md).
