---
type: finance
title: Cloud bill 2026-08 (Apollo)
description: 'August cloud bill: reconciliation compute doubled by dual-run'
tags:
- apollo
- cloud
- cost
- bill
owner: ananya
source: cloud-billing-export
source_version: 2026-08
updated_at: '2026-09-03T10:00:00Z'
trust: verified
related:
- /org/finance/apollo-budget
- /org/decisions/ADR-042
privacy: internal
---

# Cloud bill: August 2026 (Apollo cost centre)

| Line item | Planned (lakh) | Actual (lakh) |
|---|---|---|
| Reconciliation compute, legacy pipeline | 0.00 | 1.15 |
| Reconciliation compute, new pipeline | 1.15 | 1.15 |
| Storage and networking | 0.00 | 0.00 |
| **Total** | **1.15** | **2.30** |

The reconciliation compute line **doubled** in August. The legacy pipeline was planned to be switched off
once the ledger migration ([APOLLO-12](../jira/apollo-12.md), due 2026-08-01) completed. The migration slipped, and
under [ADR-042](../decisions/ADR-042.md) both pipelines keep running until parity is proven.
Cumulative Apollo cloud spend to 2026-08-31: 5.5 lakh against a 5.0 lakh budget.
