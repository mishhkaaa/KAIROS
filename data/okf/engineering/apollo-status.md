---
type: note
title: Apollo engineering status
description: Weekly engineering status for Project Apollo
tags: [apollo, engineering, migration]
source: confluence
updated_at: 2026-09-19T16:00:00Z
trust: trusted
related: [/org/projects/apollo]
---

# Apollo engineering status (week 38)

- Database migration (APOLLO-12): six weeks late. The schema change on the ledger table needed a
  full backfill; the first attempt failed on duplicate reconciliation ids.
- Vendor SDK v5 upgrade (APOLLO-31): blocked on the vendor, support ticket open for 3 weeks.
- Old and new pipelines are still running in parallel (see [Payments API](../systems/payments-api.md)).
