# Showing KAIROS on the phone: demo procedure

A step-by-step guide to demonstrating the KAIROS phone app live. It takes about 3 minutes and shows the
phone as a full way into the same kernel: sign in with a role, start work, watch it live, and approve a governed
action from your pocket.

## 1. Before the demo (10 minutes earlier)

1. **Start the stack on the laptop**: `scripts\win\kairos-boot.ps1` (or kairosd on `:8089` and the console on
   `:3000`). Then run `uv run python scripts/preflight.py --gateway http://127.0.0.1:8089`; it must print "all green".
2. **Reset between rehearsals**: `scripts\win\reset-demo.ps1`, and `uv run python scripts/seed_demo_data.py` if you
   will show the vendors question.
3. **Install the app** (once): `adb install -r apps\mobile\dist\kairos-1.1.0.apk`. On some phones (Realme, Xiaomi,
   Oppo) accept the "Install via USB" prompt on the phone itself.
4. **Connect the phone to the laptop**. Pick one:
   - **USB (most reliable)**: plug in with USB debugging on, run `adb reverse tcp:8089 tcp:8089`, and use the server
     address `http://localhost:8089` in the app. Re-run `adb reverse` after every reconnect.
   - **Wi-Fi or hotspot**: put the phone and laptop on the same network, run `scripts\win\phone-access.ps1` as
     administrator, and use the address it prints (`http://<laptop-ip>:8089`). Run it with `-Remove` afterwards.
5. **Open the app** and on the sign-in screen enter the server address, then tap **Check**. It must say
   **Connected**.
6. **Phone settings**: allow KAIROS notifications, turn on Do Not Disturb for other apps, set brightness high and
   screen timeout to 10 minutes, and close other apps. If you are mirroring to a projector, start mirroring now.
7. Keep the console open on the laptop at `http://localhost:3000`, signed in as Alice.

## 2. The demo, step by step

| # | On the phone | Say |
|---|---|---|
| 1 | The sign-in screen: show the demo org's people (Alice owner, Priya approver, Sam viewer). Tap **Priya**. | "The phone is a full way into KAIROS. I'm signing in as Priya, an approver. Same accounts and same roles as the desktop." |
| 2 | **Home**: point at "Acme Corp · approver · live" and the recent tasks. | "It's live over the event stream, and it knows my role." |
| 3 | **Ask** tab: tap the Apollo suggestion (or type the goal), then **Start**. | "I can start work from my pocket." |
| 4 | The **live run** opens: the agents appear as faces; scroll the story ("How it went"). | "Here KAIROS creates agents for this task: finance, engineering, research. This is their thought process, step by step, reported by the kernel." |
| 5 | Wait for the **"Needs your decision"** notification (about 30–60 s in). Tap it. | "An agent wants to update Jira. That's a write, so KAIROS stopped and is asking me." |
| 6 | The **approval card**: scroll through the policy, the exact payload and the evidence. | "I see exactly what will change, which policy stopped it, and the documents behind it." |
| 7 | Tap **Approve**. | "Approved from my phone. Now it's executed, verified, committed and written to the audit chain." |
| 8 | Back on the task: wait for the **result**, scroll to the evidence (24 documents). | "Thirty-one percent over budget, three root causes, each with its sources." |
| 9 | **Knowledge** tab: search `apollo budget variance`. | "The same company knowledge, searchable from the phone." |
| 10 | **Me** tab: show the role, what it allows, the notification switch. Tap **Sign out**. | "Permissions come from the role." |
| 11 | Sign in as **Sam** (viewer); open **Ask**. It says the role can read results but not start tasks. | "A viewer can read, but cannot start work or approve. Enforced by the server, not just hidden in the app." |
| 12 | Sign out. On the laptop console, click your name in the menu bar, then **Sign in on your phone**; on the phone, under **I have a code**, type the code and tap **Sign in**. | "And a one-time code signs me in as the same person as on the desktop; it works with Google accounts too." |

**Short version (60 seconds):** steps 1, 3, 5, 6, 7 and 11.

**Showing both screens:** start the task on the desktop (Alt+Space) and approve on the phone. This proves it is one
kernel, with the approval appearing on both at once.

## 3. If something goes wrong

| Problem | Fix |
|---|---|
| "Can't reach the server" | USB: run `adb reverse tcp:8089 tcp:8089` again and use `http://localhost:8089`. Wi-Fi: same network? Run `phone-access.ps1` again. Check `http://localhost:8089/health` on the laptop. |
| No notification arrives | Open the **Approvals** tab; the request is there. Notifications only arrive while the app is open or recently backgrounded. |
| The run is slow | Keep talking through the story. If preflight showed a low tok/s, run `scripts\win\restart-ollama.ps1` before the next attempt. |
| The approval was already taken by someone else | Expected: the first decision wins, and everyone sees it. Start another task. |
| The app shows an old state | Pull down to refresh, or switch tabs. |
| Nothing works | Fall back to the recorded phone video (`.data/video/kairos-phone-demo.mp4`) or the emulator (`Pixel_6a`, server `http://10.0.2.2:8089`). |

## 4. After the demo

- Run `scripts\win\phone-access.ps1 -Remove` if you opened the firewall.
- Run `scripts\win\reset-demo.ps1` before the next run.
