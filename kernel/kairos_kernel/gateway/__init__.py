"""FastAPI REST + WebSocket gateway. MUST match shared/api/openapi.json.

Owner: P1 — Kernel & Execution

TODO:
  - [x] same routes as kairos_contracts.api.mock_gateway (conformance test in tests/test_contract.py)
  - [x] auth headers X-Kairos-User / X-Kairos-Org -> Principal; KairosError -> ErrorInfo JSON
  - [x] /ws/events streams EventBus.stream(task_id, types)
"""
