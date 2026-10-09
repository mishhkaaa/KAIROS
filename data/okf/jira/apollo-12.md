---
type: note
title: APOLLO-12 Payments DB migration
description: Jira issue APOLLO-12 (In Progress)
tags:
- jira
- migration
status: in progress
owner: Priya Sharma
privacy: internal
source: jira
source_version: 2026-09-12T18:40:00.000+0000
created_at: '2026-05-22T09:00:00Z'
updated_at: '2026-09-12T18:40:00Z'
verification_status: unverified
trust: trusted
related:
- /org/jira/apollo-14
- /org/jira/apollo-18
- /org/jira/apollo-35
---

# APOLLO-12: Payments DB migration

- **Status:** In Progress
- **Assignee:** Priya Sharma
- **Type:** Epic
- **Priority:** Highest
- **Due:** 2026-08-01
- **Labels:** migration
- **Linked:** [APOLLO-14](apollo-14.md), [APOLLO-18](apollo-18.md), [APOLLO-35](apollo-35.md)

## Description

Ledger schema change (ADR-042 dual-run until parity, ADR-039 schema v2) needs a full backfill. Attempt #1 on 2026-07-30 failed on duplicate reconciliation ids. Attempt #2 on 2026-09-12 failed on cross-batch duplicates.

## Comments

- **Rahul Verma** (2026-07-30): Backfill aborted: unique constraint violation on recon_id. Legacy retries reused ids.
- **Rahul Verma** (2026-09-12): Attempt #2 failed again: duplicates across settlement batches, not only within a batch.
