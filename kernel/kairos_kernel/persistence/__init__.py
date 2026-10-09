"""Kernel state store + boot recovery (blueprint §5).

Owner: P1 — Kernel & Execution

TODO:
  - [x] SQLAlchemy models for tasks, processes, approvals, checkpoints under $KAIROS_DATA_DIR/kernel.db
  - [x] on boot: RUNNING pids -> RETRYING/resume from checkpoint; publish system.ready
  - [x] shutdown suspends; boot resumes unfinished tasks from the root checkpoint (max_restarts), re-queues queued ones
"""
