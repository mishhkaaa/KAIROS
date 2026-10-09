"""Service interfaces (typing.Protocol). Who provides what (see PROJECT.md):

    P1 Kernel & Execution         : EventBus, PolicyEngine, AuditLog, AgentContext,
                                    ToolExecutor, SandboxManager, ArtifactStore
    P2 Knowledge, Memory & Console: KnowledgeService, ContextFirewall, MemoryService
    P3 Agents & Models            : ModelProvider, ModelRouter, AgentRegistry, AgentRuntime
    P4 Platform, Data & Demo      : SourceConverter, BrowserDriver, ResourceProbe

Every interface has a working fake in kairos_contracts.testing.fakes and a contract test
in kairos_contracts.testing.contracts that the real implementation must also pass.
"""
from .agents import AgentRegistry, AgentRuntime
from .execution import ArtifactStore, BrowserDriver, SandboxManager, ToolExecutor
from .inference import ModelProvider, ModelRouter
from .ingestion import SourceConverter
from .kernel import AgentContext, AuditLog, EventBus, EventHandler, PermissionsProvider, PolicyEngine, Subscription
from .knowledge import ContextFirewall, KnowledgeService, MemoryService
from .system import ResourceProbe

__all__ = [
    "AgentContext", "AgentRegistry", "AgentRuntime", "ArtifactStore", "AuditLog", "BrowserDriver", "ContextFirewall",
    "EventBus", "EventHandler", "KnowledgeService", "MemoryService", "ModelProvider", "ModelRouter",
    "PermissionsProvider", "PolicyEngine", "ResourceProbe", "SandboxManager", "SourceConverter", "Subscription", "ToolExecutor",
]
