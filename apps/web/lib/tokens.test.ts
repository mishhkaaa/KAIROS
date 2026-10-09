// WCAG AA for every text token on every surface, in both themes (projector readability).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const TEXT = ["text", "text-2", "text-muted", "brand", "st-running", "st-waiting", "st-paused", "st-failed", "st-completed",
  "risk-low", "risk-medium", "risk-high", "risk-critical", "untrusted-fg", "ev-knowledge", "ev-tool"];
const SURFACES = ["bg", "surface-1", "surface-2", "surface-3"];

describe.each([
  ["dark", block(':root,\n[data-theme="dark"]')],
  ["light", block('[data-theme="light"]')],
])("%s theme", (_, t) => {
  it.each(TEXT)("%s is AA (4.5:1) on every surface", (fg) => {
    for (const s of SURFACES) expect(contrast(t[fg], t[s]), `${fg} on ${s}`).toBeGreaterThanOrEqual(4.5);
  });
  it("filled chips keep AA", () => {
    expect(contrast(t["st-terminated-fg"], t["st-terminated"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["untrusted-fg"], t["untrusted-bg"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["on-brand"], t["brand"])).toBeGreaterThanOrEqual(4.5);
  });
});
