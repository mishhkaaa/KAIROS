# Mock Jira for the demo (P1). Serves kairos_execution.connectors.jira_mock on :8090.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY . .
RUN uv sync --package kairos-execution --frozen --no-dev
EXPOSE 8090
CMD ["uv", "run", "--no-sync", "kairos-mock-jira"]
