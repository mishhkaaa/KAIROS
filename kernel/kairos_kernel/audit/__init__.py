"""Append-only audit journal + RunTimeline (blueprint §33).

Owner: P1 — Kernel & Execution

TODO:
  - [x] implement AuditLog protocol on SQLite/Postgres; pass AuditLogContract
  - [x] stretch: hash chain (prev_hash/hash) for tamper evidence
"""
