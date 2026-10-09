"""Record the backup demo video: a real run driven through the console, with captions, at 1920x1080.

Boot → Home → Run the Apollo prompt → live run → approve in the drawer → Result → Audit → the vendor email in the
explorer → Memory, then the invalidation moment (a line appended to the cloud bill: memories go stale, then are re-derived)
→ System. The cloud bill is restored at the end.

  scripts\\win\\reset-demo.ps1 -SkipPreflight        # clean memories and mock Jira first
  uv run python scripts/record_demo.py [--base http://localhost:3000] [--gateway http://127.0.0.1:8089] [--out .data/video]

Writes <out>/kairos-demo-<time>.webm and, when ffmpeg is on PATH, an .mp4 next to it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
BILL = REPO / "data" / "okf" / "finance" / "cloud-bill-2026-09.md"
BILL_LINE = "\nCorrection (live demo): the September dual-run line was re-billed at the committed-use rate.\n"
VENDOR_EMAIL = "/org/inbox/vendor-email-2026-09-12"

# A lower-third caption that survives navigations (re-created by the init script, text kept in sessionStorage).
CAPTION_JS = """
(() => {
  const mount = () => {
    if (document.getElementById('__cap')) return;
    const el = document.createElement('div');
    el.id = '__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:36px;transform:translateX(-50%);z-index:2147483647;max-width:1400px;'
      + 'padding:14px 26px;border-radius:12px;background:rgba(8,10,14,.86);color:#f5f7fa;font:500 26px/1.35 system-ui,sans-serif;'
      + 'box-shadow:0 8px 30px rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.12);text-align:center;pointer-events:none;'
      + 'transition:opacity .25s';
    el.textContent = sessionStorage.getItem('__cap') || '';
    el.style.opacity = el.textContent ? '1' : '0';
    document.body.appendChild(el);
  };
  window.__cap = (t) => {
    sessionStorage.setItem('__cap', t);
    mount();
    const el = document.getElementById('__cap');
    el.textContent = t;
    el.style.opacity = t ? '1' : '0';
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
"""


def caption(pg: Page, text: str, hold: float = 0.0) -> None:
    pg.evaluate("t => window.__cap && window.__cap(t)", text)
    print(f"  [{time.strftime('%H:%M:%S')}] {text}", flush=True)
    if hold:
        pg.wait_for_timeout(hold * 1000)


def scroll(pg: Page, steps: int, dy: int = 220, pause: float = 0.6) -> None:
    for _ in range(steps):
        pg.mouse.wheel(0, dy)
        pg.wait_for_timeout(pause * 1000)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:3000", help="console URL")
    ap.add_argument("--gateway", default="http://127.0.0.1:8089", help="kairosd URL (health check only)")
    ap.add_argument("--out", default=str(REPO / ".data" / "video"))
    ap.add_argument("--theme", default="dark", choices=["dark", "light"])
    ap.add_argument("--channel", default="msedge", help="Playwright browser channel ('' for bundled Chromium)")
    ap.add_argument("--skip-invalidation", action="store_true")
    a = ap.parse_args()

    status = httpx.get(f"{a.gateway}/system/status", timeout=10).json()
    if not status.get("ready"):
        print("kairosd is not ready; run the preflight first", file=sys.stderr)
        return 1
    original_bill = BILL.read_bytes()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    t0 = time.monotonic()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=a.channel or None)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, color_scheme=a.theme,
                                  record_video_dir=str(out / "raw"), record_video_size={"width": 1920, "height": 1080})
        ctx.add_init_script(CAPTION_JS)
        pg = ctx.new_page()
        try:
            pg.goto(a.base + "/boot")
            caption(pg, "KAIROS boots on one laptop: kernel, knowledge, local models and sandboxes. Nothing leaves the box.", 5)
            pg.goto(a.base + "/")
            caption(pg, "Alt+Space: one prompt starts a governed, multi-agent investigation.", 2)
            pg.keyboard.press("Alt+Space")
            pg.wait_for_timeout(700)
            pg.get_by_role("button", name="Apollo demo prompt").click()
            pg.get_by_role("radio", name="High").click()
            pg.wait_for_timeout(1500)
            pg.get_by_role("button", name=re.compile("^Run")).click()
            pg.wait_for_url(re.compile(r".*/tasks/T-[0-9a-f]+"), timeout=30_000)
            tid = pg.url.rsplit("/", 1)[1]
            print(f"task {tid}", flush=True)

            caption(pg, "The task docks left and tells its story; the desktop shows every agent, document and action as it happens.", 9)
            caption(pg, "They search /org with hybrid retrieval. Every hit carries its provenance and trust level.", 8)
            caption(pg, "A vendor email tries to instruct the agents. The context firewall marks it untrusted: data, never instructions.", 9)
            caption(pg, "Research opens vendor docs in a browser sandbox on an internal network, with no internet access.")
            card = pg.get_by_test_id("approval-card")
            card.wait_for(timeout=600_000)
            caption(pg, "Writing to Jira is a syscall. Policy says a human must approve, so the kernel blocks the agent here.", 4)
            caption(pg, "The approver sees the exact arguments, the policy and the evidence behind the change.", 4)
            card.get_by_role("button", name="Approve").click()
            caption(pg, "Approved: executed in the sandbox, verified, then committed.", 3)
            pg.get_by_test_id("task-status").filter(has_text=re.compile("completed|failed|cancelled")).wait_for(timeout=600_000)
            caption(pg, "Done: the story on the left, the result on the stage. Alt+Enter opens the full view.", 5)
            pg.keyboard.press("Alt+Enter")
            pg.get_by_test_id("recovery-plan").wait_for(timeout=30_000)
            caption(pg, "The result: three root causes, each backed by cited documents, and a recovery plan.", 3)
            scroll(pg, 8)
            pg.wait_for_timeout(2000)

            pg.goto(f"{a.base}/audit/{tid}")
            caption(pg, "Every decision, syscall and approval is in a hash-chained audit journal, verified by the kernel.", 7)
            pg.goto(f"{a.base}/knowledge?path={VENDOR_EMAIL}")
            caption(pg, "The injected vendor email, as stored: flagged, quarantined as evidence, never obeyed.", 7)

            pg.goto(a.base + "/memory")
            caption(pg, "Memories remember the documents they came from.", 5)
            if not a.skip_invalidation:
                caption(pg, "Now the September cloud bill changes...")
                BILL.write_bytes(original_bill + BILL_LINE.encode())
                pg.get_by_text(re.compile("source changed", re.I)).first.wait_for(timeout=30_000)
                caption(pg, "...so the finance memories derived from it go stale instantly. Engineering's stay fresh.", 5)
                caption(pg, "The local model re-derives them from the new text.")
                pg.locator('[title^="Re-derived from the current sources"]').first.wait_for(timeout=90_000)
                pg.wait_for_timeout(1500)
                caption(pg, "Re-derived memories replace the stale ones, with their sources. Knowledge and memory stay coherent.", 6)

            pg.goto(a.base + "/system")
            caption(pg, "All of it on one RTX laptop GPU: a 7B model on Ollama, Postgres, Docker sandboxes. Private by construction.", 7)
            caption(pg, "KAIROS: an operating system for your organization's AI.  github.com/mishhkaaa/KAIROS", 5)
        finally:
            if BILL.read_bytes() != original_bill:
                BILL.write_bytes(original_bill)
                print("cloud bill restored", flush=True)
            video = pg.video
            ctx.close()  # finishes writing the video
            raw = Path(video.path()) if video else None
            browser.close()

    if raw is None:
        print("no video was recorded", file=sys.stderr)
        return 1
    webm = out / f"kairos-demo-{stamp}.webm"
    raw.replace(webm)
    print(f"recorded {webm} ({time.monotonic() - t0:.0f} s)")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp4 = webm.with_suffix(".mp4")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
        print(f"converted {mp4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
