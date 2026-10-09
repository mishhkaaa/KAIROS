"""A2A (Agent-to-Agent) IPC helpers.

Owner: P3 — Agents & Models

These helpers wrap ctx.send/receive to implement common patterns.
They do NOT build a second IPC system — they use P1's mailbox mechanics via ctx.
"""
from __future__ import annotations

import logging
from typing import Any

from kairos_contracts.schema import EvidenceSet, MessageType
from kairos_contracts.schema.common import new_id
from kairos_contracts.schema.ipc import A2AMessage

log = logging.getLogger("kairos.agents.ipc")


async def share_evidence(ctx: Any, to_pid: int, evidence: EvidenceSet, summary: str) -> None:
    """Send evidence hits to another agent (typically the planner parent)."""
    ev_paths = [h.path for h in evidence.hits]
    msg = A2AMessage(
        message_id=new_id("MSG"),
        task_id=ctx.task_id,
        sender_pid=ctx.pid,
        receiver_pid=to_pid,
        sender=ctx.manifest.name,
        receiver="",  # kernel fills this in
        type=MessageType.EVIDENCE,
        content=summary[:500],
        provenance=ev_paths,
    )
    await ctx.send(msg)


async def ask(ctx: Any, to_pid: int, question: str, timeout: float = 60.0) -> A2AMessage | None:
    """Send a REQUEST to another agent and wait for the reply (matching in_reply_to).

    Returns None on timeout.
    """
    request_id = new_id("MSG")
    req_msg = A2AMessage(
        message_id=request_id,
        task_id=ctx.task_id,
        sender_pid=ctx.pid,
        receiver_pid=to_pid,
        sender=ctx.manifest.name,
        receiver="",
        type=MessageType.REQUEST,
        content=question[:2000],
    )
    await ctx.send(req_msg)

    # Wait for the reply matching our request_id
    while True:
        msg = await ctx.receive(timeout=timeout)
        if msg is None:
            return None  # timeout
        if msg.in_reply_to == request_id:
            return msg


async def reply(ctx: Any, original_msg: A2AMessage, content: str, payload: dict | None = None) -> None:
    """Reply to an incoming REQUEST message."""
    resp = A2AMessage(
        message_id=new_id("MSG"),
        task_id=ctx.task_id,
        sender_pid=ctx.pid,
        receiver_pid=original_msg.sender_pid,
        sender=ctx.manifest.name,
        receiver=original_msg.sender,
        type=MessageType.RESPONSE,
        content=content[:2000],
        payload=payload,
        in_reply_to=original_msg.message_id,
    )
    await ctx.send(resp)


__all__ = ["share_evidence", "ask", "reply"]
