---
type: project
title: Project Apollo
description: Internal payments modernization initiative
tags: [payments, backend, q3]
status: active
owner: priya
source: jira
source_version: "APOLLO@2026-09-20"
updated_at: 2026-09-20T09:00:00Z
verification_status: verified
trust: verified
---

# Project Apollo

## Goal

Modernize the payment reconciliation pipeline and move it onto the new Payments API.

## Status

Planned go-live was 2026-08-15. Current forecast is 2026-09-26, six weeks behind schedule.
Budget is over by 31% (see finance).

## Risks

- Vendor dependency (payment SDK v5 upgrade blocked)
- Database migration delay
- Cloud cost increase

## Related

- [Payments API](../systems/payments-api.md)
- [Decision ADR-042](../decisions/ADR-042.md)
- [Apollo budget](../finance/apollo-budget.md)
- [Apollo engineering status](../engineering/apollo-status.md)
