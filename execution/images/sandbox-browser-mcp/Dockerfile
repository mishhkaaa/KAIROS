# Browser sandbox with the Playwright MCP server (B4, phase 2). Built on the browser sandbox image, so it reuses its
# Chromium (/ms-playwright/chromium-*): nothing is downloaded at run time, and it runs offline on the internal sandbox
# network, read-only, as uid 10001, like every sandbox. The MCP backend starts it with `docker run -i` and speaks MCP
# over stdio; the URL allowlist is both the network (kairos_sandbox reaches only vendor-docs) and --allowed-origins.
#   docker build -t kairos/sandbox-browser-mcp:latest execution/images/sandbox-browser-mcp
FROM kairos/sandbox-browser:latest
ARG MCP_VERSION=0.0.83
USER root
ENV HOME=/tmp PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 NPM_CONFIG_UPDATE_NOTIFIER=false
WORKDIR /opt/mcp
RUN npm init -y >/dev/null && npm install --omit=dev --no-audit --no-fund @playwright/mcp@${MCP_VERSION} && npm cache clean --force \
 && ln -s "$(ls -d /ms-playwright/chromium-*/chrome-linux64/chrome | head -1)" /opt/mcp/chrome
USER 10001:10001
ENTRYPOINT ["node", "/opt/mcp/node_modules/@playwright/mcp/cli.js", "--headless", "--isolated", "--no-sandbox", \
            "--browser", "chromium", "--executable-path", "/opt/mcp/chrome", "--output-dir", "/tmp/mcp"]
