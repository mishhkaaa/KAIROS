"""The gateway's view of who is calling: one dependency resolves the caller, `need(permission)` guards a route.

dev mode    Authorization: Bearer <session> if present, else the X-Kairos-User / X-Kairos-Org headers (defaults
            alice / acme); a header user has the org's role for them, or owner.
google mode Authorization: Bearer <session> (or ?token= for the WebSocket) is required; no session, 401.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, Query, Request
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import AuthMode, Me, Principal

from ..identity import Identity


@dataclass
class Caller:
    principal: Principal
    role: str | None
    permissions: list[str]
    token: str | None = None

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def org_id(self) -> str:
        return self.principal.org_id


def resolve(identity: Identity, authorization: str | None, user: str, org: str, roles: str, token: str | None) -> Caller:
    bearer = token or (authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None)
    if bearer:
        found = identity.resolve_token(bearer)
        if found is None:
            raise KairosError("UNAUTHENTICATED", "the session has expired; sign in again")
        user_id, org_id = found
        role = identity.role_of(org_id, user_id) if org_id else None
        return Caller(identity.principal(user_id, org_id or "", role), role, identity.permissions(role), bearer)
    if identity.mode == AuthMode.GOOGLE:
        raise KairosError("UNAUTHENTICATED", "sign in with Google first")
    role = identity.header_role(org, user)
    extra = [r for r in roles.split(",") if r]
    return Caller(identity.principal(user, org, role, extra), role, identity.permissions(role))


def caller_dependency(identity: Identity):
    async def caller(
        request: Request,
        authorization: str | None = Header(None),
        user: str = Header("alice", alias="X-Kairos-User"),
        org: str = Header("acme", alias="X-Kairos-Org"),
        roles: str = Header("", alias="X-Kairos-Roles"),
        token: str | None = Query(None, include_in_schema=False),
    ) -> Caller:
        c = resolve(identity, authorization, user, org, roles, token)
        request.state.caller = c
        return c

    return caller


def need_factory(identity: Identity):
    base = caller_dependency(identity)

    def need(permission: str | None = None, *, org: bool = True):
        """A route dependency: the caller must be signed in, belong to an org (unless org=False), and hold `permission`."""
        from fastapi import Depends

        async def check(c: Caller = Depends(base)) -> Caller:
            if org and not c.org_id:
                raise KairosError("PERMISSION_DENIED", "create or join an organization first")
            if permission and permission not in c.permissions:
                raise KairosError("PERMISSION_DENIED", f"your role ({c.role or 'none'}) does not allow {permission}")
            return c

        return check

    return need


def me_of(identity: Identity, c: Caller) -> Me:
    me = identity.me(c.user_id, c.org_id or None)
    if c.token is None:  # a dev header caller: the header role, even without a membership row
        me = me.model_copy(update={"role": c.role, "permissions": c.permissions})
    return me
