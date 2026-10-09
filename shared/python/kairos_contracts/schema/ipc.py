"""Agent-to-agent (A2A-style) messages — the IPC of KAIROS. Large payloads travel by reference."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import ArtifactRef, Contract, Pid, TaskId, TrustLevel, utcnow


class MessageType(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    EVIDENCE = "evidence"
    CLARIFICATION = "clarification"
    RESULT = "result"
    CANCEL = "cancel"


class A2AMessage(Contract):
    message_id: str = Field(description='"MSG-..."')
    task_id: TaskId
    sender_pid: Pid
    receiver_pid: Pid
    sender: str = Field(description="Agent name")
    receiver: str = Field(description="Agent name")
    type: MessageType
    content: str = Field("", description="Short human-readable text; keep under ~2k chars")
    payload: dict[str, Any] | None = None
    payload_ref: ArtifactRef | None = None
    provenance: list[str] = Field(default_factory=list)
    trust: TrustLevel = TrustLevel.UNVERIFIED
    in_reply_to: str | None = None
    sent_at: datetime = Field(default_factory=utcnow)
