"""People and what they may do (orgs, members, roles, sessions), connected apps, and folders of this computer mounted into
/org. Contract 0.10.0."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .common import Contract, utcnow

# --------------------------------------------------------------------------- identity

PERMISSIONS = [
    "task.create",
    "task.cancel",
    "approval.resolve",
    "knowledge.read",
    "knowledge.ingest",
    "connectors.manage",
    "config.read",
    "config.manage",
    "members.manage",
]


class AuthMode(StrEnum):
    DEV = "dev"  # X-Kairos-User / X-Kairos-Org headers, or a dev sign-in by email (tests, the mock, the demo fallback)
    GOOGLE = "google"  # a Google ID token exchanged for a session


class OrgRole(Contract):
    role: str = Field(description="owner | admin | approver | member | viewer (policies/rbac/roles.yaml)")
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class UserInfo(Contract):
    user_id: str
    email: str
    name: str = ""
    avatar_url: str | None = None


class Org(Contract):
    org_id: str
    name: str
    domain: str | None = Field(None, description="Email domain whose users may join, e.g. acme.com")
    created_at: datetime = Field(default_factory=utcnow)
    member_count: int = 0


class MemberStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"


class Member(Contract):
    user_id: str
    email: str
    name: str = ""
    avatar_url: str | None = None
    role: str
    status: MemberStatus = MemberStatus.ACTIVE
    joined_at: datetime | None = None


class OrgCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    domain: str | None = None


class MemberInvite(Contract):
    email: str = Field(min_length=3)
    role: str = "member"


class MemberUpdate(Contract):
    role: str


class AuthConfig(Contract):
    """What the sign-in screen needs: which mode the gateway runs in, and the Google client id for the button."""

    mode: AuthMode
    google_client_id: str | None = None


class GoogleLogin(Contract):
    id_token: str = Field(description="The credential from Google Identity Services")


class DevLogin(Contract):
    email: str = Field(min_length=3)
    name: str = ""


class Me(Contract):
    """The signed-in user, their org (none until onboarding creates or joins one), role and permissions."""

    user: UserInfo
    org: Org | None = None
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)
    mode: AuthMode = AuthMode.DEV


class Session(Contract):
    token: str = Field(description="Send as Authorization: Bearer <token>; ?token=<token> on the WebSocket")
    expires_at: datetime
    me: Me


class PairCode(Contract):
    """Signs the same person in on another device: shown in the console, typed into the phone. One use, minutes long."""

    code: str = Field(description="Eight characters, e.g. K7QM-4ZPD; case and the dash are ignored")
    expires_at: datetime


class PairRedeem(Contract):
    code: str = Field(min_length=6, max_length=16)


# --------------------------------------------------------------------------- connectors


class ConnectorStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class Connector(Contract):
    connector_id: str = Field(description="github | google_calendar")
    name: str
    status: ConnectorStatus = ConnectorStatus.DISCONNECTED
    mode: str = Field("mock", description="mock (built-in stand-in, no account needed) | live (a real token in the vault)")
    capabilities: list[str] = Field(default_factory=list, description="e.g. github.read, github.write")
    scopes: list[str] = Field(default_factory=list)
    connected_by: str | None = None
    connected_at: datetime | None = None
    last_sync: datetime | None = None
    recent_agents: list[str] = Field(default_factory=list, description="Agents that used it recently (from the audit log)")


class ConnectorConnect(Contract):
    """A personal access token or API key. Stored encrypted in the vault; never shown again, never sent to agents."""

    token: str | None = None
    account: str | None = Field(None, description="e.g. a GitHub owner/repo to sync, a calendar id")


class ConnectorSyncResult(Contract):
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- mounts


class KnowledgeMount(Contract):
    """A folder of this computer mirrored into /org/mnt/<name>: its documents are converted, indexed and watched."""

    name: str
    host_path: str
    org_path: str
    files: int = 0
    skipped: int = 0
    watching: bool = False
    synced_at: datetime | None = None
    errors: list[str] = Field(default_factory=list)


class KnowledgeMountCreate(Contract):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")
    host_path: str = Field(min_length=1)
