"""Task manager: create/queue/cancel/resume tasks; TaskStatus transitions; one root planner pid per task.

Owner: P1 — Kernel & Execution

TODO:
  - [x] TaskManager.create(TaskCreate, principal) -> Task; publish task.created
  - [x] derive TaskStatus from the process tree (running / waiting_approval / completed / failed)
  - [x] cancel = kill whole tree; resume = restore from last checkpoints
  - [x] persist via persistence.StateStore
"""
