"""Event bus (in-memory now, Redis Streams for durability) + subscriptions that wake agents.

Owner: P1 — Kernel & Execution

TODO:
  - [x] implement EventBus protocol; pass EventBusContract
  - [x] mirror to a Redis Stream (kairos:events); history replayed on boot
  - [x] wire knowledge.changed -> MemoryService.invalidate -> notify affected pids (blueprint §21)
  - [x] cron.triggered / scheduled agents (scheduler/cron.py, KAIROS_KERNEL_SCHEDULES_FILE)
"""
