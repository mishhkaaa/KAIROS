"""YAML policy engine over policies/*.yaml (PolicyDocument). Deny by default; most specific document wins."""
from __future__ import annotations

import logging
from fnmatch import fnmatch
from pathlib import Path

import yaml
from kairos_contracts.schema import (
    ApprovalMode,
    Decision,
    Event,
    EventType,
    PolicyDecision,
    PolicyDocument,
    Principal,
    Risk,
    SyscallRequest,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.util import capability_matches

log = logging.getLogger("kairos.kernel.policy")

RISK_ORDER = [Risk.LOW, Risk.MEDIUM, Risk.HIGH, Risk.CRITICAL]


def load_policy_documents(directory: Path) -> list[PolicyDocument]:
    docs = []
    for f in sorted(Path(directory).glob("*.yaml")):
        docs.append(PolicyDocument.model_validate(yaml.safe_load(f.read_text(encoding="utf-8"))))
    return sorted(docs, key=lambda d: (d.priority, d.policy))


def template_of(agent: str) -> str:
    """The role template of a generated agent name ("finance-agent@T-1#2" -> "finance-agent"); other names unchanged."""
    return agent.split("@", 1)[0]


def max_risk(a: Risk, b: Risk) -> Risk:
    return a if RISK_ORDER.index(a) >= RISK_ORDER.index(b) else b


class YamlPolicyEngine:
    def __init__(self, policies_dir: Path, event_bus=None) -> None:
        self.policies_dir = Path(policies_dir)
        self.bus = event_bus
        self.docs: list[PolicyDocument] = load_policy_documents(self.policies_dir)
        # Generated per-agent policies (dynamic agents): an overlay that can only narrow, keyed by the generated name.
        self.generated: dict[str, PolicyDocument] = {}

    def documents(self) -> list[PolicyDocument]:
        return list(self.docs) + list(self.generated.values())

    def register_generated(self, agent: str, doc: PolicyDocument) -> None:
        self.generated[agent] = doc

    def drop_generated(self, agents: list[str]) -> None:
        for a in agents:
            self.generated.pop(a, None)

    def matching(self, principal: Principal) -> list[PolicyDocument]:
        """Org documents for this agent; a generated agent is matched through its role template's name."""
        names = {principal.agent or "", template_of(principal.agent or "")}
        roles = principal.roles or []
        out = []
        for d in self.docs:
            if not any(fnmatch(n, a) for n in names for a in d.applies_to.agents):
                continue
            if "*" not in d.applies_to.roles and not set(roles) & set(d.applies_to.roles):
                continue
            out.append(d)
        return out

    @staticmethod
    def _approval_mode(doc: PolicyDocument, capability: str) -> ApprovalMode | None:
        if capability in doc.approval:
            return doc.approval[capability]
        for key, mode in doc.approval.items():
            if "*" in key and capability_matches(capability, key):
                return mode
        return None

    async def evaluate(self, request: SyscallRequest, principal: Principal) -> PolicyDecision:
        cap = request.capability
        if not any(capability_matches(cap, g) for g in principal.capabilities):
            return PolicyDecision(decision=Decision.DENY, policy="kernel", matched_rules=["capability-check"],
                                  reason=f"capability {cap} not granted to {principal.agent or principal.user_id}")
        overlay = self.generated.get(principal.agent or "")
        if overlay is not None and not any(capability_matches(cap, g) for g in overlay.tools.allow):
            return PolicyDecision(decision=Decision.DENY, policy=overlay.policy, matched_rules=["generated:outside-bounds"],
                                  reason=f"{cap} is outside the bounds generated for {principal.agent}")
        decision = self._org_decision(request, principal)
        if (overlay is not None and decision.decision == Decision.ALLOW
                and overlay.approval.get(cap) == ApprovalMode.REQUIRED):  # the overlay only tightens: writes need a person
            decision = PolicyDecision(decision=Decision.REQUIRES_APPROVAL, policy=overlay.policy, approval_id=new_id("APR"),
                                      reason=f"{cap} requires human approval (generated agent)",
                                      matched_rules=[f"generated:approval.{cap}=required"], constraints=decision.constraints)
        return decision

    def permits(self, capability: str, principal: Principal) -> str | None:
        """Why org policy would refuse `capability` to this agent (None: some org document allows it). Used when
        generating an agent: capabilities no org document allows are dropped rather than granted and then denied."""
        probe = SyscallRequest(syscall_id="SC-probe", task_id="T-probe", pid=1, capability=capability, tool="probe",
                               operation="probe", risk=Risk.LOW, justification="bounds check")
        d = self._org_decision(probe, principal)
        return d.reason if d.decision == Decision.DENY else None

    def _org_decision(self, request: SyscallRequest, principal: Principal) -> PolicyDecision:
        cap = request.capability
        for doc in self.matching(principal):
            if any(capability_matches(cap, g) for g in doc.tools.deny):
                return PolicyDecision(decision=Decision.DENY, policy=doc.policy, reason=f"{cap} denied by {doc.policy}",
                                      matched_rules=[f"tools.deny:{cap}"])
            mode = self._approval_mode(doc, cap)
            allowed = any(capability_matches(cap, g) for g in doc.tools.allow)
            if not allowed and mode is None:
                continue
            constraints = {"network_allow": list(doc.network.allow)}
            if mode == ApprovalMode.NEVER:
                return PolicyDecision(decision=Decision.DENY, policy=doc.policy, reason=f"{cap} is never allowed",
                                      matched_rules=[f"approval.{cap}=never"])
            if mode == ApprovalMode.REQUIRED or request.risk in (Risk.HIGH, Risk.CRITICAL):
                rule = f"approval.{cap}=required" if mode == ApprovalMode.REQUIRED else f"risk={request.risk.value}"
                return PolicyDecision(decision=Decision.REQUIRES_APPROVAL, policy=doc.policy, approval_id=new_id("APR"),
                                      reason=f"{cap} requires human approval ({rule})", matched_rules=[rule],
                                      constraints=constraints)
            return PolicyDecision(decision=Decision.ALLOW, policy=doc.policy, reason=f"{cap} allowed by {doc.policy}",
                                  matched_rules=[f"tools.allow:{cap}" if allowed else f"approval.{cap}=auto"],
                                  constraints=constraints)
        return PolicyDecision(decision=Decision.DENY, policy="default-deny", reason=f"no policy allows {cap}",
                              matched_rules=["default-deny"])

    def knowledge_allow(self, principal: Principal) -> list[str]:
        """Knowledge globs from the most specific matching policy that sets any (empty = no restriction)."""
        for doc in self.matching(principal):
            if doc.knowledge.allow:
                return list(doc.knowledge.allow)
        return []

    async def reload(self) -> None:
        self.docs = load_policy_documents(self.policies_dir)
        log.info("reloaded %d policies", len(self.docs))
        if self.bus is not None:
            await self.bus.publish(Event(type=EventType.POLICY_UPDATED, source="kernel.policy",
                                         payload={"policies": [d.policy for d in self.docs]}))
