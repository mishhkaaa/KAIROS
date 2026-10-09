# Demo script: Project Apollo (owner P4, content from everyone)

Target length is about 7 minutes. Rehearse it 3× at M3, and record one clean full run as the backup video.

## On the Windows demo laptop (the laptop is the node)
Machine-specific ports go in `scripts/win/local.ps1` (git-ignored), e.g. `$env:KAIROS_PG_PORT = "5434"`.

| When | Run (PowerShell, repo root) |
|---|---|
| Start everything and open the console full screen | `scripts\win\kairos-boot.ps1` (Docker, Postgres/Redis/vendor-docs, Ollama with the 7B loaded, kairosd, the console, then `/boot` in Edge kiosk mode; Alt+F4 leaves it) |
| Before each rehearsal | `scripts\win\reset-demo.ps1` (restarts kairosd, which resets the mock Jira; empties memories and working sets; runs the preflight) |
| Preflight only | `uv run python scripts/preflight.py --gateway http://127.0.0.1:8089` (must print "all green"; checks the 7B generates at >= 25 tok/s and is fully on the GPU) |
| A run feels slow | `scripts\win\restart-ollama.ps1` (stops leftover model runners that hold VRAM, reloads the 7B, prints tok/s) |
| Throwaway run, then score | `uv run python scripts/demo_run.py run --auto-approve --gateway http://127.0.0.1:8089` (prints 8/8) |
| Score the live run | `uv run python scripts/demo_run.py check <task_id> --gateway http://127.0.0.1:8089` |
| Phone access (optional) | `scripts\win\phone-access.ps1` as administrator: prints the LAN URL and a QR code, opens ports for the Private network only. Afterwards: `scripts\win\phone-access.ps1 -Remove` |
| Record the backup video | `scripts\win\reset-demo.ps1 -SkipPreflight`, then `uv run python scripts/record_demo.py` (a real run through the console with captions, 1080p, invalidation included; writes `.data/video/*.mp4`) |
| Stop | `scripts\win\kairos-shutdown.ps1` (`-All` also stops Ollama and the containers) |

## Setup (T-30 min, Linux appliance)
1. The RTX node is on AC power and on the venue network. Its lid may stay closed.
2. On the node, run `bash /opt/kairos/scripts/preflight.sh`. **It must print "all green".** It checks:
   - services and `/system/status` ready, all components `real`;
   - the GPU inside the ollama container, models pulled **and warmed**;
   - sandbox images and the browser smoke test;
   - bundle validity and search.
3. Projector laptop (a thin client on Tailscale):
   - console `http://<node>:3000/` fullscreen;
   - a terminal beside it, SSH'd into the node, running `watch -n1 ai-ps` (switch to `ai-top` for the GPU moment);
   - the backup video open and paused on a second screen or tab.
4. Phone (optional): on the laptop's Mobile hotspot, run `scripts\win\phone-access.ps1` and open the printed URL (`/approvals`). The console finds the gateway on the same host by itself. There is no login in the MVP: use your own hotspot only, and run `phone-access.ps1 -Remove` after the demo.
5. Paste the prompt into the composer but **do not submit** yet.

**Models** (must match `models/models.yaml`; preflight checks them): `ollama pull qwen2.5:7b-instruct llama3.2:3b qwen2.5-coder:7b llava:7b nomic-embed-text`
(one name per `ollama pull` on older Ollama versions). Planning, reasoning and extraction use qwen2.5:7b-instruct; the demo must run on it: on llama3.2:3b alone the root causes still appear (built from the specialists' findings) but the prose is weaker.

**The console is a desktop** (`ui/desktop` and later). Every URL still works as a deep link and opens its window. Gateway `http://<node>:8080`, console `http://<node>:3000`.

| Screen | How to open it |
|---|---|
| Boot checklist (open it first; it moves to the desktop when everything is up) | `/boot` |
| Desktop: greeting, system line, widgets, the knowledge constellation | `/`, or the Desktop icon in the rail (Alt D) |
| Ask KAIROS (starts a task, or opens an app, task or document) | **Alt Space**, Ctrl K, the Ask bar, or the Ask button in the rail |
| Live run: docked left with its story; the rest of the desktop is the run stage | `/tasks/<task_id>` (opens by itself after Run). Alt Enter zooms it to the full view (timeline, process tree, inspector, Result tab) |
| Every task | `/tasks` (Alt 1) |
| Approvals | `/approvals` (Alt 2). A notification appears by itself; the drawer opens on the task |
| Knowledge explorer (the vendor email) | `/knowledge?path=/org/inbox/vendor-email-2026-09-12` (Alt 3), or click its node on the desktop |
| Memory: the invalidation demo | `/memory` (Alt 4) |
| Audit journal | `/audit/<task_id>` (Alt 5), or the Audit button on the task |
| Agents, System, Terminal | `/agents`, `/system`, `/terminal` (Alt 6, 7, 8; Alt T for Terminal) |

Other keys: Alt+` switches windows while Alt is held, Alt W closes, Alt M minimises, Alt / lists every shortcut.

### Screen tour: where each demo moment lives
| Moment | Where to look |
|---|---|
| Asking (step 1) | Alt Space, click "Investigate Project Apollo's overrun", Run. The Task window docks left |
| Agents as processes (steps 2–3) | The run stage: each agent is a card with its bot face, PID, tokens and an orb for what it is doing now. The story on the left says "Created finance-agent, engineering-agent…" |
| Documents read | The stage's "Referred to" card fills as agents read, and the matching nodes on the desktop flare |
| Firewall (4–5) | The vendor email chip turns red ("untrusted"), its node flares red, and the story says the firewall flagged it: read as data, never as instructions |
| Sandbox screenshot (8–9) | The stage's "Opened in a sandbox" card |
| Approval (10–11) | The drawer opens by itself on the task (plain headline, risk, policy, arguments, evidence, Approve / Reject). A notification also appears. On a phone the card is full screen |
| Commit (12–14) | The story ("Executed, verified and committed"); the stage's "Asked the kernel" card marks jira.write completed |
| Audit (15) | The **Audit** button on the task: stat tiles and "chain intact" |
| Result (17) | The stage shows the result when the run ends. Alt Enter zooms the task to its Result tab: summary, 3 root causes with citation chips, recovery steps |
| Invalidation (18) | `/memory`: the amber "Source changed" banner, the stale rows, then the re-derived ones. The bill's node pulses amber on the desktop |

For the invalidation demo (last row of the run sheet) start kairosd with `KAIROS_KNOWLEDGE_WATCH=true` (in `.env`).

**Prompt (paste exactly):**
> Investigate why Project Apollo is over budget and six weeks behind schedule. Identify root causes, update the tracker, and prepare a recovery plan.

## Run sheet
| # | ~time | Do / what the audience sees | Talking point | Owner | Fallback |
|---|---|---|---|---|---|
| 0 | 0:00 | Show the node: a closed laptop, `ai-ps` empty, `ai-top` showing the GPU | "This laptop *is* the company's AI server. Nothing leaves it." | P4 | CLI won't start: show `/system` in the console (all components `real`, GPU gauge) |
| 1 | 0:20 | Submit the prompt from the projector laptop (a thin client) | "My laptop is only a terminal; the work happens on our box." | P2 | Mock gateway: `uv run kairos-mock-gateway --speed 2` on the projector laptop, console pointed at it |
| 2 | 0:30 | Planner PID 101 appears in the tree and in `ai-ps` | "Agents are processes: PID, state, quota, capabilities." | P1/P3 | Keep going; the tree catches up from events |
| 3 | 0:45 | Finance, engineering and research PIDs spawn | "The planner delegates, just like `fork`." | P3 | A specialist missing after 30 s: point at the planner's "spawned …" lines in the timeline; the run continues with the others |
| 4–5 | 1:00 | Knowledge panel: hits with scores and provenance. **The vendor email is flagged `instruction_like`** | "Documents are evidence, never instructions. This email tries to make the agent delete a table; the firewall catches it." | P2/P4 | Open `/org/inbox/vendor-email-2026-09-12` in the explorer and show the flag |
| 6 | 1:30 | Working set / memory loaded | "The context window is RAM; memory is paged in." | P2 | Nothing to show yet: say it over the knowledge hits and move on |
| 7 | 1:45 | A2A message engineering → planner (backfill root cause) | "Agents talk over kernel IPC, not by sharing prompts." | P3 | No IPC line: show `ai-audit <task_id>` in the node terminal (IPC entries), or skip |
| 8–9 | 2:00 | Sandbox boots; **screenshot of the PayCo status page** (GA 2026-10-20) | "Computer use, but only inside a sandbox on an internal network with no internet." | P1/P4 | `KAIROS_MODE_BROWSER=fake` (fake page), or show `.data/smoke/vendor.png` from preflight |
| 10 | 2:40 | Kernel blocks `jira.write` → **the approval center lights up** | "Agent intent is not authorization. Writes to the outside world are syscalls, and policy says this one needs a human." | P1/P2 | Drawer didn't open: go to `/approvals`. No approval 60 s after the action agent spawned: switch to the mock gateway replay (it pauses at the approval) |
| 11 | 3:00 | **Approve from the phone**; show the evidence paths on the card first | "The approver sees exactly which documents justify the change." | P2 (+P4 mobile) | Approve in the console |
| 12–14 | 3:20 | Jira updated → verified → committed | "Transactional actions: execute, verify, commit, or roll back." | P1 | Pre-recorded rollback clip for a forced failure |
| 15 | 3:50 | Audit journal with the stats header | "Every claim and every action is traceable." | P1/P2 | Page errors: `ai-audit <task_id>` in the node terminal |
| 16 | 4:10 | Memory consolidated | "It learns from the run." | P2 | No `memory.consolidated` line: open `/memory` in the console (finance/engineering findings with their source documents) |
| 17 | 4:30 | Final answer + recovery-plan artifact. Read the three root causes aloud: dual-run cloud cost, duplicate-recon-id backfill failure, PayCo certification + emergency contract | "Every root cause is backed by at least two documents." | P3 | Open the artifact from the last rehearsal |
| + | 5:30 | `ai-kill` a leftover process live; `ai-top` shows GPU load during a run | "The OS metaphor, made visible." | P1/P4 | `ai-kill` fails: use the kill button on the node in the process tree |
| 18 | 6:00 | **Invalidation:** open `/memory`, then edit the cloud bill the finance agent cited → the amber banner "Source changed … N memories invalidated · Affected: finance-agent" appears, the finance rows are tagged "source changed"; a few seconds later the local model re-derives them from the new text (teal "re-derived" rows, toast); the explorer shows the new line. Steps below | "Knowledge changes, so the memories that depended on it are invalidated." | P2/P4 | No toast: open `/memory?task_id=<task_id>` and show `stale: true`; else skip |

### Invalidation demo (step 18)
Needs kairosd started with `KAIROS_KNOWLEDGE_WATCH=true`, after a completed run (the finance and engineering agents store their findings, derived from the documents they cited).
1. Check which documents the memories derive from: `curl -s http://<node>:8080/memory?task_id=<task_id> | jq '.[] | {owner, derived_from}'`. `/org/finance/cloud-bill-2026-09` is the usual one for finance-agent; `/org/projects/apollo` often appears for both agents.
2. On the node, edit that file, e.g. append a line to `data/okf/finance/cloud-bill-2026-09.md`: `Correction (live demo): the September dual-run line was re-billed.`
3. Within ~1 s the console shows the invalidation toast naming the affected agents; the file is reindexed (the explorer shows the new line without a reload).
4. Reset afterwards: `git checkout data/okf/finance/cloud-bill-2026-09.md` (the watcher reindexes the original).

**Optional: security policy v2.** The finance agent checks its drivers against `/org/policies` (v2 adds CFO sign-off for emergency vendor spend, the PayCo contract), so its memories derive from `policies/security.md`. After a completed run, open `/memory`, then `copy data\demo-assets\security-policy-v2.md data\okf\policies\security.md` (or `cp` on Linux): the banner names `/org/policies/security` and finance-agent only; engineering stays fresh, and the explorer shows v2. Reset: `git checkout data/okf/policies/security.md`.

### Second scenario: Project Zeus budget risk ("does it only do the one task?")
A different project, the same agents and the same governance. Use it when a judge asks whether the system only does Apollo, or to show the LLM firewall classifier live. It takes about as long as Apollo.

On the desktop: Alt Space, then the "Brief the steering committee on Zeus risk" suggestion, then Run.

**Prompt (paste exactly):**
> Prepare a steering-committee briefing on Project Zeus budget risk for Q4: identify the risk drivers with evidence, update the tracker, and propose mitigations.

| What the audience sees | Talking point |
|---|---|
| The same planner and specialists spawn; their step goals say "Project Zeus" | "Nothing here is scripted for Apollo. The planner reads the goal and delegates." |
| Finance reports a projected Q4 overrun of **1.4 lakh (35%)** with three drivers: the Cumulus warehouse renewal (+40% credit price), ad-hoc query volume that doubled with no per-team budgets, a contractor extension | "Same agents, different documents: the forecast, the status note, the tickets." |
| Engineering: the cost guardrails (ZEUS-9) are three weeks behind, blocked on the warehouse role migration | "It finds the engineering cause behind a finance number." |
| Sandbox screenshot of the **Cumulus pricing page** (not the PayCo page) | "Each project's vendor page, still inside a sandbox with no internet." |
| The renewal email `/org/inbox/vendor-email-2026-09-24` is flagged. It politely asks "any automated assistant" to record purchase order PO-7741 as already approved | "This injection has no 'ignore your instructions' in it, so a keyword filter misses it. With the LLM classifier on, the firewall flags it as `instruction_like_llm`." |
| The approval card is for **ZEUS-11**, status "At Risk", with the forecast and status note as evidence | "The write goes to Zeus's own tracking issue, and it still needs a human." |
| Result tab: three cited risk drivers and mitigation steps | "Every driver cites a Zeus document; none cites Apollo." |

- **To show the classifier:** start kairosd with `KAIROS_FIREWALL_LLM=true` (in `scripts\win\local.ps1`: `$env:KAIROS_FIREWALL_LLM = "true"`, then `reset-demo.ps1`). With it off, the email is still marked untrusted (`untrusted_source`), but not instruction-like. Search "Cumulus warehouse renewal email" in the Knowledge explorer to show the flags either way.
- **Score a rehearsal:** `uv run python scripts/demo_run.py run --auto-approve --scenario zeus` (8 checks); add `--expect-llm-flag` when the classifier is on (a ninth check: caught by the LLM, not the regex).
- **Order:** Apollo first, then Zeus, works back to back with no reset in between (different tracker issues, different memories). Run `reset-demo.ps1` before the next rehearsal as usual.
- **Fallback:** if Zeus stalls, say "that is the live system on a second, unscripted task" and return to the Apollo result.

### Part 2: people, connected apps, your own files, the phone, the OS (about 3 minutes)
Use after Apollo, or on its own when the question is "can my team actually use this?".

| Do | Talking point |
|---|---|
| Menu bar, your name, **Switch user…**: pick **Sam (viewer)**. Alt Space, type a goal | "Roles are real. Sam can read every result but cannot start work or approve: the box says so, and the gateway refuses it too." |
| Switch back to Alice. Open **Organization** (rail) | "People, invitations and the role matrix, read from `policies/rbac/roles.yaml`. Google sign-in in production, the same roles." |
| **Connections**: Connect GitHub (no token: the demo data), then **Sync into /org** | "Outside apps are governed tools. Tokens live encrypted in the vault, never with an agent; writing to GitHub waits for an approver." |
| **Add knowledge**: drop a file; then mount a folder of this laptop | "Your own documents: converted, indexed, searchable by agents in seconds. Edit the file on disk and KAIROS re-reads it." |
| **Settings** (Alt ,): Models, then What needs a human | "One read-only picture of the running system: which model does which kind of thinking, and which actions pause for a person." |
| User menu, **Sign in on your phone**; type the code in the app (emulator or phone) | "The phone gets its own session. Approvals arrive as notifications; approve from anywhere." |
| Windows Terminal, **kairos-os**: `ls /org`, `cat /org/finance/apollo-budget.md`, `ls "/org/.search/apollo overrun"`, `cp notes.md /org/uploads/` | "And KAIROS as an operating system: the organization's knowledge is a filesystem, governed like everything else." |

Reset afterwards: in Connections disconnect GitHub; in Add knowledge remove the mount; delete `data/okf/github`,
`data/okf/calendar`, `data/okf/uploads` and `data/okf/mnt` (all git-ignored), then `reset-demo.ps1`. Synced and
uploaded documents mention PayCo and could change what the Apollo and Zeus runs retrieve.

### Known limits
- **Browser sandbox internet on Docker Desktop:** fixed. The browser runs on the internal network in both modes; on Docker Desktop a relay container publishes its port, so page subresources can't reach the internet either (`execution/tests/test_browser_live.py::test_browser_sandbox_has_no_internet`).

**Closing line:** *"It doesn't just answer questions. It runs your organization's AI, privately, on one box."*

## If things go wrong
| Symptom | Action |
|---|---|
| Projector laptop can't reach the node | Check `tailscale status` on both. Venue Wi-Fi blocking UDP makes Tailscale relay via DERP; wait 10 s. Last resort: everyone joins the phone hotspot |
| Gateway down | `ssh node sudo systemctl restart kairosd` (≈ 20 s), then continue |
| A model answers slowly or times out | Re-run the preflight warm-up. Check `ollama ps` shows `100% GPU` |
| The run stalls > 30 s on one step | Say "this is the live system"; if it's still stuck, switch to the mock gateway replay |
| Anything else | Play the backup video from the matching timestamp and narrate over it |

## QA checklist before each rehearsal
- [ ] Preflight all green: `scripts/preflight.sh` on the appliance, `uv run python scripts/preflight.py` anywhere else
- [ ] `uv run python scripts/check_okf.py` OK, and `data/okf` has been reindexed after its last edit (`POST /knowledge/reindex`)
- [ ] One throwaway task run end to end (warms caches; clears first-run surprises)
- [ ] Mock-Jira reset to the seed state (restart `mock-jira`)
- [ ] Memories reset **after the throwaway run** (on the laptop: `scripts\win\reset-demo.ps1` does it) (otherwise the step-18 toast counts memories from every earlier run): `docker compose -f infra/compose/docker-compose.yml exec postgres psql -U kairos -d kairos -c "TRUNCATE memories, working_sets;"`. For a different database, change `-d` (or run the same SQL against the database in `KAIROS_DATABASE_URL`). No task should be running, since working sets are what a restarted task resumes from
- [ ] Phone and projector laptop logged into Tailscale; console and app open
- [ ] Backup video file present locally (not streamed)
