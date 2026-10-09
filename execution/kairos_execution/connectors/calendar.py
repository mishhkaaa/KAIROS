"""`calendar` tool backend: Google Calendar read/write through the Google Calendar REST API.

Tokens are stored in the token vault (vault.py) per-org, never logged or sent to agents.
calendar_token="inprocess" runs the mock in dev mode.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Risk,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolResultStatus,
    ToolSpec,
    ToolTransport,
    VerificationCheck,
    VerificationResult,
)

from ..tools.base import err, ok, require, status_check, token

SPEC = ToolSpec(
    name="calendar",
    description="Google Calendar: read free/busy and events, create events with Meet links. "
                "calendar.read is read-only; calendar.write creates events and requires approval.",
    transport=ToolTransport.HTTP,
    operations=[
        ToolOperation(
            name="list_events",
            capability="calendar.read",
            description="List upcoming calendar events",
            input_schema={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string", "default": "primary"},
                    "time_min": {"type": "string", "description": "ISO 8601 datetime"},
                    "time_max": {"type": "string", "description": "ISO 8601 datetime"},
                    "max_results": {"type": "integer", "default": 10},
                },
            },
        ),
        ToolOperation(
            name="get_freebusy",
            capability="calendar.read",
            description="Query free/busy for a list of attendees",
            input_schema={
                "type": "object",
                "required": ["attendees", "time_min", "time_max"],
                "properties": {
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "time_min": {"type": "string"},
                    "time_max": {"type": "string"},
                },
            },
        ),
        ToolOperation(
            name="create_event",
            capability="calendar.write",
            description="Create a calendar event, optionally with a Google Meet link",
            input_schema={
                "type": "object",
                "required": ["summary", "start", "end"],
                "properties": {
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "start": {"type": "string", "description": "ISO 8601 datetime"},
                    "end": {"type": "string", "description": "ISO 8601 datetime"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "add_meet_link": {"type": "boolean", "default": False},
                    "calendar_id": {"type": "string", "default": "primary"},
                },
            },
            risk=Risk.MEDIUM,
            reversible=True,
        ),
    ],
)

_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


class CalendarBackend:
    name = "calendar"

    def __init__(self, token_or_mode: str = "inprocess") -> None:
        self._undo: dict[str, dict[str, Any]] = {}
        self.client: httpx.AsyncClient
        self.configure(None if token_or_mode == "inprocess" else token_or_mode)

    @property
    def live(self) -> bool:
        return self._token is not None

    def configure(self, token: str | None) -> None:
        """Built-in mock without a token, the Google Calendar API with one (see GitHubBackend.configure)."""
        self._token = token
        self.client = httpx.AsyncClient(
            base_url=_CALENDAR_BASE,
            transport=None if token else _MockCalendarTransport(),
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=15,
        )

    def spec(self) -> ToolSpec:
        return SPEC

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation == "list_events":
                cal = a.get("calendar_id", "primary")
                now = datetime.now(UTC).isoformat()
                params: dict[str, Any] = {
                    "timeMin": a.get("time_min", now),
                    "singleEvents": True,
                    "orderBy": "startTime",
                    "maxResults": a.get("max_results", 10),
                }
                if a.get("time_max"):
                    params["timeMax"] = a["time_max"]
                r = await self.client.get(f"/calendars/{cal}/events", params=params)
                r.raise_for_status()
                events = [_flatten_event(e) for e in r.json().get("items", [])]
                return ok(inv, {"events": events})

            if inv.operation == "get_freebusy":
                require(a, "attendees", "time_min", "time_max")
                body = {
                    "timeMin": a["time_min"],
                    "timeMax": a["time_max"],
                    "items": [{"id": e} for e in a["attendees"]],
                }
                r = await self.client.post("/freeBusy", json=body)
                r.raise_for_status()
                return ok(inv, r.json())

            if inv.operation == "create_event":
                require(a, "summary", "start", "end")
                cal = a.get("calendar_id", "primary")
                event_body: dict[str, Any] = {
                    "summary": a["summary"],
                    "start": {"dateTime": a["start"], "timeZone": "UTC"},
                    "end": {"dateTime": a["end"], "timeZone": "UTC"},
                }
                if a.get("description"):
                    event_body["description"] = a["description"]
                if a.get("attendees"):
                    event_body["attendees"] = [{"email": e} for e in a["attendees"]]
                params = {}
                if a.get("add_meet_link"):
                    event_body["conferenceData"] = {"createRequest": {"requestId": token()[:8]}}
                    params["conferenceDataVersion"] = 1
                r = await self.client.post(f"/calendars/{cal}/events", json=event_body, params=params)
                r.raise_for_status()
                created = r.json()
                rb = token()
                self._undo[rb] = {"calendar_id": cal, "event_id": created["id"]}
                return ok(inv, _flatten_event(created), rollback_token=rb)

            return err(inv, "NOT_FOUND", f"unknown calendar operation {inv.operation}")
        except KairosError as e:
            return err(inv, e.code, e.message)
        except httpx.HTTPError as e:
            return err(inv, "TOOL_FAILED", f"calendar request failed: {e}")

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        if result.status != ToolResultStatus.SUCCESS or inv.operation != "create_event":
            return status_check(inv, result)
        undo = self._undo.get(result.rollback_token or "")
        if not undo:
            return status_check(inv, result)
        try:
            r = await self.client.get(f"/calendars/{undo['calendar_id']}/events/{undo['event_id']}")
            exists = r.status_code == 200
            return status_check(inv, result, [VerificationCheck(name="event_exists", passed=exists)])
        except httpx.HTTPError as e:
            return status_check(inv, result, [VerificationCheck(name="event_exists", passed=False, detail=str(e))])

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        undo = self._undo.pop(result.rollback_token or "", None)
        if undo is None:
            return False
        try:
            r = await self.client.delete(f"/calendars/{undo['calendar_id']}/events/{undo['event_id']}")
            return r.status_code in (204, 410)
        except httpx.HTTPError:
            return False


def _flatten_event(e: dict[str, Any]) -> dict[str, Any]:
    meet = None
    for ep in e.get("conferenceData", {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            meet = ep.get("uri")
            break
    return {
        "id": e["id"],
        "summary": e.get("summary"),
        "start": (e.get("start") or {}).get("dateTime"),
        "end": (e.get("end") or {}).get("dateTime"),
        "attendees": [at["email"] for at in e.get("attendees", [])],
        "meet_link": meet,
        "html_link": e.get("htmlLink"),
    }


class _MockCalendarTransport(httpx.AsyncBaseTransport):
    """In-process mock for dev/demo."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        import json as _json
        path = request.url.path
        now = datetime.now(UTC)

        if "freeBusy" in path:
            body = _json.loads(request.content)
            calendars = {item["id"]: {"busy": []} for item in body.get("items", [])}
            return httpx.Response(200, json={"kind": "calendar#freeBusy", "calendars": calendars})

        if "/events" in path and request.method == "POST":
            event = _json.loads(request.content)
            event_id = f"mock-{int(now.timestamp())}"
            return httpx.Response(200, json={
                "id": event_id,
                "summary": event.get("summary", "New event"),
                "start": event.get("start", {}),
                "end": event.get("end", {}),
                "attendees": event.get("attendees", []),
                "htmlLink": f"https://calendar.google.com/event?id={event_id}",
                "conferenceData": {"entryPoints": [{"entryPointType": "video",
                                                     "uri": f"https://meet.google.com/mock-{event_id[:6]}"}]
                                   } if event.get("conferenceData") else {},
            })

        if "/events/" in path and request.method == "DELETE":
            return httpx.Response(204)

        if "/events/" in path and request.method == "GET":
            event_id = path.split("/events/")[-1]
            return httpx.Response(200, json={"id": event_id, "summary": "Mock event",
                                             "start": {"dateTime": now.isoformat()},
                                             "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                                             "attendees": [], "htmlLink": ""})

        # list events
        return httpx.Response(200, json={"items": [
            {"id": "mock-001", "summary": "Team standup",
             "start": {"dateTime": (now + timedelta(hours=1)).isoformat()},
             "end": {"dateTime": (now + timedelta(hours=1, minutes=30)).isoformat()},
             "attendees": [{"email": "alice@example.com"}], "htmlLink": ""},
        ]})
