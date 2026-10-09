# P4 Platform, Data & Demo: what this split provides
Paths: `infra/`, `data/`, `scripts/`, `knowledge/kairos_knowledge/ingestion/`, `execution/kairos_execution/browser/`, `execution/images/sandbox-browser/`, `models/kairos_models/gpu/`

| Provides | Kind | Consumers | Fake until ready | Contract |
|---|---|---|---|---|
| `SourceConverter`s (markdown, jira-json, slack-export, csv, [document]) | interface | P2 ingest pipeline | `FakeMarkdownConverter` | `SourceConverterContract` |
| `BrowserDriver` (Playwright → sandbox) + `kairos/sandbox-browser` image | interface + image | P1 executor | `FakeBrowserDriver` | `BrowserDriverContract` |
| `ResourceProbe` (CPU/RAM/GPU) | interface | P1 `/system/resources`, ai-top | `FakeResourceProbe` | `ResourceProbeContract` |
| RTX appliance (Ubuntu, drivers, toolkit, compose, Ollama models, systemd, `/sovereign-data`) | platform | everyone | dev laptops | boot → `ready: true` |
| `data/okf` demo bundle (+ `QA.md`) | data | P2 QA, P3 answers | `shared/fixtures/okf` | validates cleanly |
| `vendor-docs` offline site | compose service | P3 research agent via browser | fake page | — |
| Demo script, QA checklist, backup recording | docs/video | team | — | — |

## Status (owner keeps this current)
| Item | Status |
|---|---|
| RTX box: drivers · Docker · toolkit · Ollama models | ☐ runbook + `infra/appliance/install.sh` ready; run on the node |
| Resource probe | ☑ `HostProbe` (psutil + nvidia-smi, stale-while-revalidate < 500 ms); contract green |
| Converters: markdown · jira-json · slack · csv · document | ☑ four; `document` not shipped on `integration/m3` (its 3 contract tests skip: "converter 'document' not shipped yet") |
| Browser image + driver + vendor-docs | ☑ Playwright 1.63.0 image (offline, uid 10001, read-only fs); contract green under P1's sandbox flags |
| data/okf ≥ 30 (M1) / ≥ 60 (M3) files + qa.yaml | ☑ / ☑ 73 files; `data/qa.yaml`; `scripts/check_okf.py` OK; 0 validation warnings (Slack folder indexes); retrieval QA 10/10 (ADR-042 wording) |
| systemd boot + LAN access | ☐ units + Tailscale/ufw in install.sh; verify with a cold boot on the node |
| Demo script · 3 rehearsals · backup video | ☐ script updated on `integration/m3` (models, URLs, fallbacks, cloud-bill invalidation as step 18, Docker Desktop known limit); 2 clean real runs on a Windows dev laptop; RTX rehearsals + video pending |
| Dev-laptop fixes | ☑ `KAIROS_HOST_PORT` for compose; `browser_smoke.py` on Docker Desktop; `.env.example` covers the merged stack |

Notes for consumers:
- **P2:** `build_converters` returns specific converters first and markdown (the catch-all for any .md file or directory) last; take the first `can_convert`. `request.options["frontmatter"]` overrides converter defaults (e.g. `{"privacy": "confidential"}`). QA questions live in `data/qa.yaml` (outside the bundle).
- **P1:** display sandboxes: `init=True`, network `kairos_sandbox`, `endpoints["playwright"] = ws://<container-ip>:3000/`, uid 10001 OK. Call `browser.close(sb)` before `sandbox.destroy`. The driver raises `BAD_REQUEST` for non-http(s) URLs, `TIMEOUT`, `SANDBOX_FAILED` (unreachable/disconnected), `TOOL_FAILED` (other navigation errors).
