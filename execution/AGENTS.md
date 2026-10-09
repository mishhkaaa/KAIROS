# execution/ — owner P1, EXCEPT `kairos_execution/browser/`, `images/sandbox-browser/`, `tests/test_browser_contract.py` (owner P4)
- P1: ToolExecutor (jira/fs/browser/sandbox backends), DockerSandboxManager, FsArtifactStore, mock Jira service, MCP adapter (stretch). Brief: shared/services/P1-kernel-execution.md
- P4: BrowserDriver (Playwright client connecting to sandbox.endpoints["playwright"]) + the browser image. Brief: shared/services/P4-platform-data-demo.md
- Tool errors come back as ToolResult(status=error), never exceptions. Every capability must exist in shared/catalogs/capabilities.yaml.
- Sandboxes: non-root, read-only root fs, cap_drop ALL, no-new-privileges, network none unless allowlisted, and a guaranteed destroy.
