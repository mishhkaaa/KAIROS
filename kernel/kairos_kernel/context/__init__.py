"""KernelAgentContext — the real implementation of kairos_contracts.interfaces.AgentContext.

Owner: P1 — Kernel & Execution

TODO:
  - [x] route llm -> ModelRouter (fill task_id/pid, enforce manifest model_policy, charge tokens, publish model.invoked)
  - [x] route search/read/list -> KnowledgeService with the agent Principal (scopes = manifest mounts ∩ task data_scope)
  - [x] screen search hits through ContextFirewall; publish knowledge.retrieved; audit knowledge refs
  - [x] recall/remember -> MemoryService; send/receive -> ipc mailboxes (publish ipc.message)
  - [x] syscall -> syscalls.SyscallGateway; put/get_artifact -> ArtifactStore; log -> agent.log event
"""
