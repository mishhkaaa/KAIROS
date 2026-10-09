"""Framework adapters. adapters/nooa: NVIDIA NOOA object agents -> KAIROS process (blueprint §12).

Owner: P2 — Knowledge, Memory & Console (NOOA adapter, stretch)

TODO:
  - [ ] NOOA methods/docstrings/type hints -> tool schemas; route NOOA's LLM calls through ctx.llm
  - [ ] NOOA fields -> checkpoint state; allowed_sources() -> memory mounts check
  - [ ] degrade gracefully when nooa is not installed (optional dependency)
"""
