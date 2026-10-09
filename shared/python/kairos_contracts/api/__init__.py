"""Gateway API contract (HTTP + WebSocket) between the kernel gateway (P1) and clients (P4 web UI, CLI, mobile).

The mock gateway in mock_gateway.py IS the spec: shared/api/openapi.json is exported from it,
and P1's real gateway must expose the same (method, path) set — see route_signatures().

Auth (MVP): every request carries  X-Kairos-User: <user_id>  and  X-Kairos-Org: <org_id>.
Errors: HTTP status from errors.ERROR_HTTP_STATUS, body = ErrorInfo JSON.
WebSocket: GET /ws/events?task_id=<id>&types=<glob,glob>  → stream of Event JSON objects, one per message.
Artifact bytes: GET /tasks/{task_id}/artifacts/{name} (name may contain "/") → the file, with artifact_headers(name).
"""
from __future__ import annotations

import mimetypes
from typing import Any

USER_HEADER = "X-Kairos-User"
ORG_HEADER = "X-Kairos-Org"
WS_EVENTS_PATH = "/ws/events"


def route_signatures(app: Any) -> set[tuple[str, str]]:
    """{("GET", "/tasks/{task_id}"), ...} for a FastAPI/Starlette app — used by P1's conformance test."""
    sigs: set[tuple[str, str]] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        if path is None or path.startswith(("/docs", "/redoc", "/openapi")):
            continue
        for m in getattr(r, "methods", None) or {"WS"}:
            if m not in ("HEAD", "OPTIONS"):
                sigs.add((m, path))
    return sigs


_MEDIA_TYPES = {".md": "text/markdown; charset=utf-8", ".json": "application/json", ".txt": "text/plain; charset=utf-8",
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".csv": "text/csv; charset=utf-8"}


def artifact_media_type(name: str) -> str:
    """Content type for an artifact, from its name (the ArtifactStore interface keeps no content type)."""
    dot = name.rfind(".")
    ext = name[dot:].lower() if dot >= 0 else ""
    return _MEDIA_TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def artifact_headers(name: str) -> dict[str, str]:
    """Artifacts are agent output: never let the browser sniff them or run them on the console's origin."""
    return {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox",
            "Content-Disposition": f'inline; filename="{name.rsplit("/", 1)[-1]}"'}
