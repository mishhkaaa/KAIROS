---
type: system
title: Reconciliation pipeline
description: Legacy and new payment reconciliation pipelines
tags:
- reconciliation
- payments
- apollo
owner: priya
source: service-catalog
updated_at: '2026-08-31T18:00:00Z'
trust: verified
privacy: internal
---

# Reconciliation pipeline

Matches settlements from PayCo against the ledger every night.

- **Legacy pipeline:** batch jobs on VMs; being replaced by Apollo.
- **New pipeline:** streaming jobs on the [Payments API](payments-api.md) and the [Ledger DB](ledger-db.md).

Both run in parallel under [ADR-042](../decisions/ADR-042.md) until parity is proven, which doubles
reconciliation compute cost.
