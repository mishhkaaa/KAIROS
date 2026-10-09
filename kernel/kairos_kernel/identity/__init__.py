"""Who is asking, and what they may do: users, orgs, members, roles, sessions, and the connector token vault.

Owner: P1 — Kernel & Execution (roles in policies/rbac/roles.yaml; the vault's key handling)

Two modes (Settings.auth, KAIROS_AUTH):
  dev     the X-Kairos-User / X-Kairos-Org headers keep working (tests, the mock, the demo fallback); a header user is
          an owner unless the org lists them with another role. Signing in by email issues a real session, so roles can
          be tried without Google.
  google  a Google ID token (Google Identity Services) is verified against KAIROS_GOOGLE_CLIENT_ID and exchanged for a
          session; every other route needs it (Authorization: Bearer, or ?token= on the WebSocket).

State lives in $KAIROS_DATA_DIR/identity.db (SQLite). Session tokens are stored hashed. Connector tokens are encrypted
with KAIROS_VAULT_KEY (Fernet); without a key the vault still works but only obfuscates, and says so in the log.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    AuthConfig,
    AuthMode,
    DevLogin,
    GoogleLogin,
    Me,
    Member,
    MemberInvite,
    MemberStatus,
    MemberUpdate,
    Org,
    OrgCreate,
    OrgRole,
    PairCode,
    PairRedeem,
    Principal,
    PrincipalKind,
    PrivacyLevel,
    Session,
    UserInfo,
)
from kairos_contracts.schema.common import utcnow
from kairos_contracts.wiring import Settings

from ..persistence.db import Database

log = logging.getLogger("kairos.kernel.identity")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, avatar_url TEXT,
                                 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orgs(org_id TEXT PRIMARY KEY, name TEXT NOT NULL, domain TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members(org_id TEXT NOT NULL, email TEXT NOT NULL, user_id TEXT, role TEXT NOT NULL,
                                   status TEXT NOT NULL, joined_at TEXT, invited_by TEXT, PRIMARY KEY(org_id, email));
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, org_id TEXT,
                                    expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pairings(code_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, org_id TEXT, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vault(org_id TEXT NOT NULL, key TEXT NOT NULL, blob TEXT NOT NULL, meta TEXT NOT NULL,
                                 PRIMARY KEY(org_id, key));
"""

# Used when policies/rbac/roles.yaml is missing: the same table, so a checkout without it still enforces something sane.
DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "owner": ("Everything, including configuration.", ["task.create", "task.cancel", "approval.resolve", "knowledge.read",
                                                       "knowledge.ingest", "connectors.manage", "config.read",
                                                       "config.manage", "members.manage"]),
    "admin": ("Full operational access.", ["task.create", "task.cancel", "approval.resolve", "knowledge.read",
                                            "knowledge.ingest", "connectors.manage", "config.read", "members.manage"]),
    "approver": ("Can resolve approvals.", ["task.create", "knowledge.read", "approval.resolve"]),
    "member": ("Can submit tasks and read knowledge.", ["task.create", "knowledge.read"]),
    "viewer": ("Read-only.", ["knowledge.read"]),
}
ROLE_ORDER = ["viewer", "member", "approver", "admin", "owner"]


def load_roles(path: Path) -> list[OrgRole]:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        table = raw.get("roles") or {}
        roles = [OrgRole(role=name, description=(v or {}).get("description", ""), permissions=list((v or {}).get("permissions", [])))
                 for name, v in table.items()]
        if roles:
            return sorted(roles, key=lambda r: ROLE_ORDER.index(r.role) if r.role in ROLE_ORDER else 99, reverse=True)
    except (OSError, yaml.YAMLError) as e:
        log.warning("cannot read %s (%s); using the built-in role table", path, e)
    return [OrgRole(role=k, description=d, permissions=p) for k, (d, p) in DEFAULT_ROLES.items()]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32] or "org"


PAIR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I: read off one screen, typed on another
PAIR_MINUTES = 5


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Vault:
    """Connector tokens at rest. Fernet with KAIROS_VAULT_KEY (32 bytes, base64 or hex); without a key, base64 only."""

    def __init__(self, db: Database, key: str | None) -> None:
        self.db = db
        self._fernet = None
        if key:
            from cryptography.fernet import Fernet

            try:
                raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
            except ValueError:
                raw = bytes.fromhex(key)
            if len(raw) != 32:
                raise ValueError("KAIROS_VAULT_KEY must be 32 bytes (base64 or hex)")
            self._fernet = Fernet(base64.urlsafe_b64encode(raw))
        else:
            log.warning("connector vault has no KAIROS_VAULT_KEY: tokens are only obfuscated at rest (fine for a demo box)")

    @property
    def encrypted(self) -> bool:
        return self._fernet is not None

    def put(self, org_id: str, key: str, secret: dict[str, Any], meta: dict[str, Any]) -> None:
        payload = json.dumps(secret).encode()
        blob = self._fernet.encrypt(payload).decode() if self._fernet else base64.b64encode(payload).decode()
        self.db.execute("INSERT OR REPLACE INTO vault VALUES (?,?,?,?)", (org_id, key, blob, json.dumps(meta, default=str)))

    def get(self, org_id: str, key: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT blob FROM vault WHERE org_id=? AND key=?", (org_id, key))
        if not row:
            return None
        try:
            payload = self._fernet.decrypt(row["blob"].encode()) if self._fernet else base64.b64decode(row["blob"])
            return json.loads(payload)
        except Exception:  # noqa: BLE001 — a key change makes old blobs unreadable; treat them as absent
            log.warning("vault entry %s/%s cannot be decrypted with the current key", org_id, key)
            return None

    def meta(self, org_id: str, key: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT meta FROM vault WHERE org_id=? AND key=?", (org_id, key))
        return json.loads(row["meta"]) if row else None

    def delete(self, org_id: str, key: str) -> None:
        self.db.execute("DELETE FROM vault WHERE org_id=? AND key=?", (org_id, key))


class Identity:
    def __init__(self, settings: Settings, db_path: Path | str | None = None) -> None:
        self.settings = settings
        self.mode = AuthMode(settings.auth)
        self.db = Database(db_path if db_path is not None else Path(settings.data_dir) / "identity.db")
        self.db.script(SCHEMA)
        self.roles = load_roles(Path(settings.policies_dir) / "rbac" / "roles.yaml")
        self._perms = {r.role: r.permissions for r in self.roles}
        self.vault = Vault(self.db, settings.vault_key)
        if self.mode == AuthMode.DEV and not self.db.one("SELECT 1 FROM orgs"):
            self._seed_demo_org()

    # ------------------------------------------------------------------ config
    def config(self) -> AuthConfig:
        return AuthConfig(mode=self.mode, google_client_id=self.settings.google_client_id if self.mode == AuthMode.GOOGLE else None)

    def permissions(self, role: str | None) -> list[str]:
        return list(self._perms.get(role or "", []))

    def role_exists(self, role: str) -> bool:
        return role in self._perms

    # ------------------------------------------------------------------ users
    def _user(self, user_id: str) -> UserInfo | None:
        row = self.db.one("SELECT * FROM users WHERE user_id=?", (user_id,))
        return UserInfo(user_id=row["user_id"], email=row["email"], name=row["name"] or "", avatar_url=row["avatar_url"]) if row else None

    def _upsert_user(self, email: str, name: str = "", avatar_url: str | None = None) -> UserInfo:
        email = email.strip().lower()
        row = self.db.one("SELECT user_id FROM users WHERE email=?", (email,))
        if row:
            if name or avatar_url:
                self.db.execute("UPDATE users SET name=COALESCE(NULLIF(?,''), name), avatar_url=COALESCE(?, avatar_url) WHERE user_id=?",
                                (name, avatar_url, row["user_id"]))
            return self._user(row["user_id"])  # type: ignore[return-value]
        base = _slug(email.split("@")[0]) or "user"
        user_id = base
        while self.db.one("SELECT 1 FROM users WHERE user_id=?", (user_id,)):
            user_id = f"{base}-{secrets.token_hex(2)}"
        self.db.execute("INSERT INTO users VALUES (?,?,?,?,?)", (user_id, email, name or base, avatar_url, utcnow().isoformat()))
        # Pending invitations for this address become memberships.
        self.db.execute("UPDATE members SET user_id=?, status=?, joined_at=? WHERE email=? AND user_id IS NULL",
                        (user_id, MemberStatus.ACTIVE.value, utcnow().isoformat(), email))
        return self._user(user_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------ orgs and members
    def _seed_demo_org(self) -> None:
        now = utcnow().isoformat()
        self.db.execute("INSERT INTO orgs VALUES (?,?,?,?)", ("acme", "Acme Corp", "acme.example", now))
        alice = self._upsert_user("alice@acme.example", "Alice")
        self.db.execute("INSERT OR IGNORE INTO members VALUES (?,?,?,?,?,?,?)",
                        ("acme", alice.email, alice.user_id, "owner", MemberStatus.ACTIVE.value, now, None))
        # Two teammates invited ahead, so the demo can sign in as someone with less power and see roles at work.
        for email, role in (("priya@acme.example", "approver"), ("sam@acme.example", "viewer")):
            self.db.execute("INSERT OR IGNORE INTO members VALUES (?,?,?,?,?,?,?)",
                            ("acme", email, None, role, MemberStatus.INVITED.value, None, alice.user_id))
        log.info("seeded the demo org acme: alice (owner), priya (approver) and sam (viewer) invited (dev mode)")

    def org(self, org_id: str) -> Org | None:
        row = self.db.one("SELECT * FROM orgs WHERE org_id=?", (org_id,))
        if not row:
            return None
        count = self.db.one("SELECT COUNT(*) AS n FROM members WHERE org_id=?", (org_id,))["n"]
        return Org(org_id=row["org_id"], name=row["name"], domain=row["domain"], created_at=row["created_at"], member_count=count)

    def _membership(self, org_id: str, user_id: str) -> Any:
        return self.db.one("SELECT * FROM members WHERE org_id=? AND user_id=?", (org_id, user_id))

    def role_of(self, org_id: str, user_id: str) -> str | None:
        row = self._membership(org_id, user_id)
        return row["role"] if row and row["status"] == MemberStatus.ACTIVE.value else None

    def home_org(self, user_id: str) -> str | None:
        row = self.db.one("SELECT org_id FROM members WHERE user_id=? AND status=? ORDER BY joined_at LIMIT 1",
                          (user_id, MemberStatus.ACTIVE.value))
        return row["org_id"] if row else None

    def create_org(self, user_id: str, body: OrgCreate) -> Org:
        user = self._user(user_id)
        if user is None:
            raise KairosError("UNAUTHENTICATED", "sign in first")
        base = _slug(body.name)
        org_id = base
        while self.db.one("SELECT 1 FROM orgs WHERE org_id=?", (org_id,)):
            org_id = f"{base}-{secrets.token_hex(2)}"
        now = utcnow().isoformat()
        self.db.execute("INSERT INTO orgs VALUES (?,?,?,?)", (org_id, body.name.strip(), (body.domain or "").strip().lower() or None, now))
        self.db.execute("INSERT INTO members VALUES (?,?,?,?,?,?,?)",
                        (org_id, user.email, user.user_id, "owner", MemberStatus.ACTIVE.value, now, None))
        return self.org(org_id)  # type: ignore[return-value]

    def members(self, org_id: str) -> list[Member]:
        out = []
        for m in self.db.all("SELECT * FROM members WHERE org_id=? ORDER BY joined_at IS NULL, joined_at, email", (org_id,)):
            u = self._user(m["user_id"]) if m["user_id"] else None
            out.append(Member(user_id=m["user_id"] or m["email"], email=m["email"], name=(u.name if u else ""),
                              avatar_url=u.avatar_url if u else None, role=m["role"], status=m["status"], joined_at=m["joined_at"]))
        return out

    def _owners(self, org_id: str) -> int:
        return self.db.one("SELECT COUNT(*) AS n FROM members WHERE org_id=? AND role='owner' AND status=?",
                           (org_id, MemberStatus.ACTIVE.value))["n"]

    def _check_grant(self, actor_role: str | None, role: str) -> None:
        if not self.role_exists(role):
            raise KairosError("BAD_REQUEST", f"unknown role {role}")
        if role == "owner" and actor_role != "owner":
            raise KairosError("PERMISSION_DENIED", "only an owner can make someone an owner")

    def invite(self, org_id: str, body: MemberInvite, by: str, actor_role: str | None) -> Member:
        self._check_grant(actor_role, body.role)
        email = body.email.strip().lower()
        if self.db.one("SELECT 1 FROM members WHERE org_id=? AND email=?", (org_id, email)):
            raise KairosError("CONFLICT", f"{email} is already in this org")
        existing = self.db.one("SELECT user_id FROM users WHERE email=?", (email,))
        status, joined = (MemberStatus.ACTIVE.value, utcnow().isoformat()) if existing else (MemberStatus.INVITED.value, None)
        self.db.execute("INSERT INTO members VALUES (?,?,?,?,?,?,?)",
                        (org_id, email, existing["user_id"] if existing else None, body.role, status, joined, by))
        return next(m for m in self.members(org_id) if m.email == email)

    def _member_row(self, org_id: str, member: str) -> Any:
        row = self.db.one("SELECT * FROM members WHERE org_id=? AND (user_id=? OR email=?)", (org_id, member, member.lower()))
        if not row:
            raise KairosError("NOT_FOUND", f"member {member}")
        return row

    def update_member(self, org_id: str, member: str, body: MemberUpdate, actor_role: str | None) -> Member:
        row = self._member_row(org_id, member)
        self._check_grant(actor_role, body.role)
        if row["role"] == "owner" and body.role != "owner" and self._owners(org_id) <= 1:
            raise KairosError("CONFLICT", "an org needs at least one owner")
        self.db.execute("UPDATE members SET role=? WHERE org_id=? AND email=?", (body.role, org_id, row["email"]))
        return next(m for m in self.members(org_id) if m.email == row["email"])

    def remove_member(self, org_id: str, member: str) -> None:
        row = self._member_row(org_id, member)
        if row["role"] == "owner" and self._owners(org_id) <= 1:
            raise KairosError("CONFLICT", "an org needs at least one owner")
        self.db.execute("DELETE FROM members WHERE org_id=? AND email=?", (org_id, row["email"]))

    # ------------------------------------------------------------------ sessions and sign-in
    def issue(self, user: UserInfo, org_id: str | None = None) -> Session:
        token = secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(hours=self.settings.session_hours)
        org_id = org_id or self.home_org(user.user_id)
        self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (_hash(token), user.user_id, org_id, expires.isoformat()))
        return Session(token=token, expires_at=expires, me=self.me(user.user_id, org_id))

    def resolve_token(self, token: str) -> tuple[str, str | None] | None:
        row = self.db.one("SELECT * FROM sessions WHERE token_hash=?", (_hash(token),))
        if not row or row["expires_at"] < utcnow().isoformat():
            return None
        # An org created or joined after sign-in becomes the session's org.
        org_id = row["org_id"] or self.home_org(row["user_id"])
        return row["user_id"], org_id

    def revoke(self, token: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))

    # ------------------------------------------------------------------ pairing another device (the phone)
    def pair(self, user_id: str, org_id: str | None) -> PairCode:
        """A one-time code for this person's next device; it signs them in there with a session of its own."""
        if not self._user(user_id):
            raise KairosError("BAD_REQUEST", "sign in first; a header caller has no account to pair")
        raw = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(8))
        expires = utcnow() + timedelta(minutes=PAIR_MINUTES)
        self.db.execute("DELETE FROM pairings WHERE expires_at < ?", (utcnow().isoformat(),))
        self.db.execute("INSERT INTO pairings VALUES (?,?,?,?)", (_hash(raw), user_id, org_id, expires.isoformat()))
        return PairCode(code=f"{raw[:4]}-{raw[4:]}", expires_at=expires)

    def redeem(self, body: PairRedeem) -> Session:
        raw = re.sub(r"[^A-Z0-9]", "", body.code.upper())
        row = self.db.one("SELECT * FROM pairings WHERE code_hash=?", (_hash(raw),))
        if not row or row["expires_at"] < utcnow().isoformat():
            raise KairosError("UNAUTHENTICATED", "that code is wrong or has expired; make a new one in the console")
        self.db.execute("DELETE FROM pairings WHERE code_hash=?", (_hash(raw),))
        user = self._user(row["user_id"])
        if user is None:
            raise KairosError("UNAUTHENTICATED", "that account no longer exists")
        return self.issue(user, row["org_id"])

    def dev_login(self, body: DevLogin) -> Session:
        if self.mode != AuthMode.DEV:
            raise KairosError("PERMISSION_DENIED", "email sign-in is only available when KAIROS_AUTH=dev")
        return self.issue(self._join_by_domain(self._upsert_user(body.email, body.name)))

    def google_login(self, body: GoogleLogin) -> Session:
        client_id = self.settings.google_client_id
        if not client_id:
            raise KairosError("BAD_REQUEST", "Google sign-in is not configured: set KAIROS_GOOGLE_CLIENT_ID")
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        try:
            claims = id_token.verify_oauth2_token(body.id_token, google_requests.Request(), client_id)
        except ValueError as e:
            raise KairosError("UNAUTHENTICATED", f"Google sign-in failed: {e}") from e
        if not claims.get("email") or not claims.get("email_verified", False):
            raise KairosError("UNAUTHENTICATED", "the Google account has no verified email")
        user = self._upsert_user(claims["email"], claims.get("name", ""), claims.get("picture"))
        return self.issue(self._join_by_domain(user))

    def _join_by_domain(self, user: UserInfo) -> UserInfo:
        """Anyone from an org's own email domain joins it as a member the first time they sign in (an invitation wins)."""
        if not self.home_org(user.user_id):
            row = self.db.one("SELECT org_id FROM orgs WHERE domain=?", (user.email.split("@")[-1].lower(),))
            if row:
                self.db.execute("INSERT OR IGNORE INTO members VALUES (?,?,?,?,?,?,?)",
                                (row["org_id"], user.email, user.user_id, "member", MemberStatus.ACTIVE.value, utcnow().isoformat(), "domain"))
        return user

    # ------------------------------------------------------------------ principals
    def me(self, user_id: str, org_id: str | None) -> Me:
        user = self._user(user_id) or UserInfo(user_id=user_id, email=f"{user_id}@local", name=user_id)
        org = self.org(org_id) if org_id else None
        role = self.role_of(org_id, user_id) if org_id else None
        return Me(user=user, org=org, role=role, permissions=self.permissions(role), mode=self.mode)

    def header_role(self, org_id: str, user_id: str) -> str:
        """Dev mode's header principal: the org's role for them, or owner (headers are the trusted dev path)."""
        return self.role_of(org_id, user_id) or "owner"

    def principal(self, user_id: str, org_id: str, role: str | None, extra_roles: list[str] | None = None) -> Principal:
        roles = [r for r in [role, *(extra_roles or [])] if r]
        return Principal(kind=PrincipalKind.USER, org_id=org_id, user_id=user_id, roles=roles, capabilities=["*"],
                         data_scopes=["/org/**"], max_privacy=PrivacyLevel.INTERNAL)


__all__ = ["Identity", "Vault", "load_roles", "DEFAULT_ROLES"]
