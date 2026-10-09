"""Browser / computer-use inside a sandbox (blueprint §8, Mode B).

Owner: P4 — Platform, Data & Demo (BrowserDriver). P1 plugs it into the ToolExecutor
Interface: kairos_contracts.interfaces.BrowserDriver  ·  Returns: BrowserPage
The browser runs INSIDE the sandbox container (image execution/images/sandbox-browser, started by
P1's SandboxManager with spec.display=True). This module only connects to it — never launch a host browser.

TODO:
  - [x] images/sandbox-browser/Dockerfile: Playwright + Chromium, `playwright run-server --port 3000`, non-root
  - [x] driver.py: PlaywrightDriver connecting with `chromium.connect(sandbox.endpoints["playwright"])`
  - [x] one browser context per sandbox_id (cache), open/click/type -> BrowserPage (text truncated to 20k chars)
  - [x] screenshot -> PNG bytes (P1 stores it as an artifact and emits sandbox.screenshot)
  - [x] errors: unreachable endpoint -> SANDBOX_FAILED, navigation timeout (15s) -> TIMEOUT
  - [x] factory.build_browser_driver(); BrowserDriverContract green (tests skip without docker)
"""
