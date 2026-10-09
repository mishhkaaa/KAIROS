"""One exception type for the whole system. Codes are listed in shared/catalogs/errors.yaml.

The gateway maps KairosError to HTTP using ERROR_HTTP_STATUS, with an ErrorInfo body.
"""
from __future__ import annotations

from typing import Any

from .schema.common import ErrorInfo

ERROR_HTTP_STATUS: dict[str, int] = {
    "BAD_REQUEST": 400,
    "UNAUTHENTICATED": 401,
    "CAPABILITY_DENIED": 403,
    "KNOWLEDGE_FORBIDDEN": 403,
    "POLICY_DENIED": 403,
    "PERMISSION_DENIED": 403,
    "NOT_FOUND": 404,
    "TASK_NOT_FOUND": 404,
    "PROCESS_NOT_FOUND": 404,
    "AGENT_NOT_FOUND": 404,
    "KNOWLEDGE_NOT_FOUND": 404,
    "APPROVAL_NOT_FOUND": 404,
    "ARTIFACT_NOT_FOUND": 404,
    "INVALID_STATE_TRANSITION": 409,
    "APPROVAL_ALREADY_RESOLVED": 409,
    "CONFLICT": 409,
    "QUOTA_EXCEEDED": 429,
    "TOOL_FAILED": 502,
    "MODEL_UNAVAILABLE": 503,
    "SANDBOX_FAILED": 503,
    "TIMEOUT": 504,
    "INTERNAL": 500,
}

RETRIABLE = {"MODEL_UNAVAILABLE", "SANDBOX_FAILED", "TIMEOUT", "TOOL_FAILED"}


class KairosError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None, retriable: bool | None = None):
        if code not in ERROR_HTTP_STATUS:
            raise ValueError(f"Unknown error code {code!r}; add it to errors.py and catalogs/errors.yaml")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}
        self.retriable = code in RETRIABLE if retriable is None else retriable

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS[self.code]

    def to_info(self) -> ErrorInfo:
        return ErrorInfo(code=self.code, message=self.message, retriable=self.retriable, details=self.details)
