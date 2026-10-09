# Browser sandbox image (P4). P1's SandboxManager starts it when SandboxSpec.display=True and publishes
# the Playwright endpoint as SandboxInfo.endpoints["playwright"] = "ws://<container-ip>:3000/" (ip mode, Linux)
# or "ws://<host>:<published-port>/" (port mode, Docker Desktop).
# PW_VERSION MUST equal the `playwright` Python version in uv.lock (execution/tests/test_browser_contract.py checks it).
# Runs offline (internal sandbox network), with a read-only root fs and as uid 10001 (P1's sandbox flags):
# playwright is installed at build time, HOME points at the /tmp tmpfs, browsers come from the base image.
ARG PW_VERSION=1.63.0
FROM mcr.microsoft.com/playwright:v${PW_VERSION}-noble
ARG PW_VERSION
ENV HOME=/tmp PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 NPM_CONFIG_UPDATE_NOTIFIER=false
WORKDIR /opt/pw
RUN npm init -y >/dev/null && npm install --omit=dev --no-audit --no-fund playwright@${PW_VERSION} && npm cache clean --force
USER 10001:10001
EXPOSE 3000
CMD ["/opt/pw/node_modules/.bin/playwright", "run-server", "--port", "3000", "--host", "0.0.0.0"]
