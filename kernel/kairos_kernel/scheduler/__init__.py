"""Agent + model + resource scheduling (blueprint §22, §44).

Owner: P1 — Kernel & Execution

TODO:
  - [x] priority queues: high / normal / background with admission control
  - [x] respect max concurrent RUNNING pids and GPU share (from models.gpu monitor via ResourceSnapshot)
  - [x] score candidates from AgentRegistry.match(goal) — used when the planner asks for 'best agent'
  - [x] preemption: a high-priority task pauses a running background task until a slot frees
"""
