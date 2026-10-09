# execution/ — P1 (tools, sandboxes, artifacts, mock Jira) + P4 (browser driver) (`kairos_execution`)
- P1: `artifacts/`, `files/`, `connectors/jira_mock.py`, `tools/` (ToolExecutor), `sandbox/` (Docker), `mcp/` (stretch), `images/sandbox-base/`. Brief: [P1](../shared/services/P1-kernel-execution.md)
- P4: `browser/` (BrowserDriver), `images/sandbox-browser/`, `tests/test_browser_contract.py`. Brief: [P4](../shared/services/P4-platform-data-demo.md)

```bash
docker build -t kairos/sandbox-base:latest execution/images/sandbox-base
docker build -t kairos/sandbox-browser:latest execution/images/sandbox-browser
uv run pytest execution/tests -rs
```
