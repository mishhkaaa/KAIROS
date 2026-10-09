---
type: note
title: 'Postmortem: ledger backfill failure (duplicate recon ids)'
description: 'Why the Apollo ledger backfill failed: duplicate reconciliation ids from legacy retries'
tags:
- apollo
- postmortem
- migration
- backfill
owner: rahul
source: confluence
updated_at: '2026-09-15T11:00:00Z'
trust: verified
related:
- /org/jira/apollo-12
- /org/decisions/ADR-039
privacy: internal
---

# Postmortem: ledger backfill failure (APOLLO-12)

**Date of incident:** 2026-07-30 (attempt #1); repeated 2026-09-12 (attempt #2). **Author:** Rahul Verma. **Severity:** SEV-3.

## Summary

The full ledger backfill required by [ADR-039](../decisions/ADR-039.md) failed because the legacy reconciliation
pipeline had produced **duplicate reconciliation ids**. The new ledger schema enforces a unique `recon_id`,
so the backfill aborted on the first duplicate.

## Root cause

Retries after settlement-batch timeouts in the legacy pipeline reused the same reconciliation id for a second
batch. About 41,000 duplicate ids exist across 2024-2026 data. The first dedupe script ([APOLLO-14](../jira/apollo-14.md))
only removed duplicates *within* a batch, so attempt #2 failed on cross-batch duplicates.

## Impact

- The migration ([APOLLO-12](../jira/apollo-12.md)) is six weeks late.
- Under [ADR-042](../decisions/ADR-042.md) the legacy pipeline cannot be switched off, so reconciliation cloud cost stays doubled.

## Actions

1. Cross-batch dedupe with a deterministic id remap table (Rahul, APOLLO-14).
2. Dry-run the backfill on a production snapshot before the next attempt (Sara).
3. Add a uniqueness check to the parity report ([APOLLO-22](../jira/apollo-22.md)).
