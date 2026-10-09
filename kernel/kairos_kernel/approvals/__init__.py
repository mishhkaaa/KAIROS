"""Human approval queue.

Owner: P1 — Kernel & Execution

TODO:
  - [x] create Approval from PolicyDecision; publish approval.requested
  - [x] resolve(approve/reject) wakes the waiting syscall; APPROVAL_ALREADY_RESOLVED on double resolve
  - [x] expiry -> EXPIRED -> syscall REJECTED
"""
