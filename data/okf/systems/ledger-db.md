---
type: system
title: Ledger DB
description: Payments ledger database (v2 schema with unique recon_id)
tags:
- database
- ledger
- payments
owner: rahul
source: service-catalog
updated_at: '2026-08-31T18:00:00Z'
trust: verified
privacy: internal
---

# Ledger DB

PostgreSQL cluster holding the payments ledger. The v2 schema ([ADR-039](../decisions/ADR-039.md)) adds a unique
`recon_id`, which is why duplicate reconciliation ids break the backfill. Used by the [Payments API](payments-api.md).
