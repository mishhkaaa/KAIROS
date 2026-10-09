"""All cross-module data contracts. Import from here: `from kairos_contracts.schema import Task`."""
from .agents import *  # noqa: F401,F403
from .audit import *  # noqa: F401,F403
from .common import *  # noqa: F401,F403
from .events import *  # noqa: F401,F403
from .identity import *  # noqa: F401,F403
from .inference import *  # noqa: F401,F403
from .ipc import *  # noqa: F401,F403
from .knowledge import *  # noqa: F401,F403
from .memory import *  # noqa: F401,F403
from .policy import *  # noqa: F401,F403
from .process import *  # noqa: F401,F403
from .syscall import *  # noqa: F401,F403
from .system import *  # noqa: F401,F403
from .task import *  # noqa: F401,F403
from .tools import *  # noqa: F401,F403

# Models exported as JSON Schema / TypeScript (shared/schemas, shared/ts). Keep sorted by domain.
EXPORTED_MODELS = [
    # common
    Principal, UserPermissions, ResourceQuota, ResourceUsage, Provenance, ErrorInfo,  # noqa: F405
    # task
    TaskCreate, Task, TaskResult,  # noqa: F405
    # process
    AgentProcess, ProcessTreeNode, SpawnRequest, Checkpoint,  # noqa: F405
    # syscall / approval
    SyscallRequest, PolicyDecision, SyscallResult, Approval, ApprovalResolution,  # noqa: F405
    # tools / sandbox
    ToolSpec, ToolInvocation, ToolResult, VerificationResult, SandboxSpec, SandboxInfo, ExecRequest, ExecResult, BrowserPage,  # noqa: F405
    # knowledge
    OKFFrontmatter, KnowledgeObject, KnowledgeListing, SearchQuery, SearchHit, EvidenceSet,  # noqa: F405
    OKFDraft, GraphResult, IngestRequest, IngestResult, ValidationReport, KnowledgeChange,  # noqa: F405
    # memory
    MemoryRecord, MemoryQuery, WorkingSet, InvalidationReport,  # noqa: F405
    # inference
    ModelRequest, ModelResponse, StreamChunk, EmbedRequest, EmbedResponse, ModelInfo, RoutingDecision,  # noqa: F405
    # agents
    AgentManifest, Plan, AgentResult,  # noqa: F405
    # ipc / events / audit / policy / system
    A2AMessage, Event, AuditEntry, RunTimeline, PolicyDocument,  # noqa: F405
    TaskUnderstood, AgentPlanned, AgentCreated, AgentThought, ToolQuery, TaskData,  # noqa: F405
    ComponentHealth, ResourceSnapshot, SystemStatus,  # noqa: F405
    StackComponent, RuntimeVersions, ModelRoute, ModelsConfig, PolicySummary, FirewallConfig, EndpointInfo, SystemConfig,  # noqa: F405
    # identity / connectors / mounts
    OrgRole, UserInfo, Org, Member, OrgCreate, MemberInvite, MemberUpdate, AuthConfig, GoogleLogin, DevLogin, Me, Session, PairCode, PairRedeem,  # noqa: F405
    Connector, ConnectorConnect, ConnectorSyncResult, KnowledgeMount, KnowledgeMountCreate,  # noqa: F405
]
