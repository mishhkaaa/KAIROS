"""Contract 0.11.0 (dynamic agents): manifest and spawn fields, UserPermissions, the approval-required set."""
import asyncio
from pathlib import Path

import pytest
import yaml
from kairos_contracts.interfaces import AgentContext, PermissionsProvider
from kairos_contracts.schema import AgentManifest, ManifestRuntime, SpawnRequest, UserPermissions
from kairos_contracts.testing.fakes import FakeAgentContext, FakePermissionsProvider, default_test_manifest, fake_bundle
from kairos_contracts.util import APPROVAL_REQUIRED
from pydantic import ValidationError

CATALOG = Path(__file__).resolve().parents[2] / "catalogs" / "capabilities.yaml"


def test_approval_required_matches_the_capability_catalog():
    rows = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    assert APPROVAL_REQUIRED == {cap for cap, row in rows.items() if row.get("approval") == "required"}


def test_manifest_fields_default_to_a_template():
    m = AgentManifest(name="writer", description="d", runtime=ManifestRuntime(entrypoint="x:Y"))
    assert (m.template, m.generated, m.task_id, m.system_prompt) == (None, False, None, None)
    g = m.model_copy(update={"name": "writer@T-1", "template": "writer", "generated": True, "task_id": "T-1"})
    assert AgentManifest.model_validate(g.model_dump(mode="json")) == g


def test_spawn_requests_narrow_with_scope_and_say_why():
    r = SpawnRequest(agent="finance-agent", goal="g", task_id="T-1", scope=["/org/finance/**"], why="budget")
    assert r.scope == ["/org/finance/**"]
    with pytest.raises(ValidationError):
        SpawnRequest(agent="a", goal="g", task_id="T-1", scope=["finance"])  # not an /org or /workspace glob
    with pytest.raises(ValidationError):
        SpawnRequest(agent="a", goal="g", task_id="T-1", why="x" * 241)


def test_fake_context_records_what_a_spawn_asked_for():
    m = default_test_manifest()
    ctx = FakeAgentContext(manifest=m)
    assert isinstance(ctx, AgentContext)
    pid = asyncio.run(ctx.spawn("research-agent", "vendor", capabilities=["knowledge.search"], scope=["/org/vendors/**"], why="w"))
    req = ctx.spawn_requests[pid]
    assert (req.capabilities, req.scope, req.why) == (["knowledge.search"], ["/org/vendors/**"], "w")


def test_fake_permissions_provider():
    p = FakePermissionsProvider({"bob": UserPermissions(user_id="bob", org_id="acme", roles=["viewer"],
                                                        capabilities=["knowledge.read"], data_scopes=["/org/projects/**"])})
    assert isinstance(p, PermissionsProvider)
    assert asyncio.run(p.resolve("bob", "acme")).capabilities == ["knowledge.read"]
    alice = asyncio.run(p.resolve("alice", "acme"))
    assert "jira.*" in alice.capabilities and alice.data_scopes == ["/org/**"]
    assert isinstance(fake_bundle().permissions, FakePermissionsProvider)
