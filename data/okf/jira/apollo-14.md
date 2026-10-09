---
type: note
title: APOLLO-14 Deduplicate legacy reconciliation ids
description: Jira issue APOLLO-14 (In Progress)
tags:
- jira
- migration
- data-quality
status: in progress
owner: Rahul Verma
privacy: internal
source: jira
source_version: 2026-09-15T10:00:00.000+0000
created_at: '2026-07-31T09:00:00Z'
updated_at: '2026-09-15T10:00:00Z'
verification_status: unverified
trust: trusted
related:
- /org/jira/apollo-12
---

# APOLLO-14: Deduplicate legacy reconciliation ids

- **Status:** In Progress
- **Assignee:** Rahul Verma
- **Type:** Task
- **Priority:** High
- **Due:** 2026-09-24
- **Labels:** migration, data-quality
- **Linked:** [APOLLO-12](apollo-12.md)

## Description

About 41,000 duplicate reconciliation ids from legacy retries block the ledger backfill.

v1 removed within-batch duplicates only. v2 adds a cross-batch id remap table.
