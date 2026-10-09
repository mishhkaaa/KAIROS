// Fails (exit 1) if a text colour the app uses is below WCAG AA (4.5:1) on the surface it sits on. Adapted from
// Manjunath's check on d/settings to this app's tokens (src/theme.ts). Run: node scripts/contrast.mjs
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/theme.ts", import.meta.url), "utf8");
const block = /export const C = \{([\s\S]*?)\n\};/.exec(src)[1];
const C = Object.fromEntries([...block.matchAll(/(\w+): "(#[0-9a-f]{6})"/gi)].map((m) => [m[1], m[2]]));
const STATUS = [...src.matchAll(/(\w+): \{ label: "[^"]+", color: C\.(\w+), soft: (?:C\.(\w+)|"(#[0-9a-f]{6})") \}/gi)].map((m) => ({
  name: m[1],
  color: C[m[2]],
  soft: m[3] ? C[m[3]] : m[4],
}));

function lum(h) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

const pairs = [];
// Body text, secondary text and meta text on every surface.
for (const fg of ["text", "text2", "text3", "brand"]) for (const bg of ["card", "ground", "sunk"]) pairs.push([`${fg} on ${bg}`, C[fg], C[bg]]);
// Status pills: the status colour on its soft fill.
for (const s of STATUS) pairs.push([`${s.name} pill`, s.color, s.soft]);
// Text on tinted notices and the brand chip.
pairs.push(["brand on brandSoft", C.brand, C.brandSoft], ["failed on failedSoft", C.failed, C.failedSoft], ["waiting on waitingSoft", C.waiting, C.waitingSoft]);
// White labels on filled buttons and badges.
for (const fill of ["brand", "done", "failed"]) pairs.push([`white on ${fill}`, "#ffffff", C[fill]]);

let bad = 0;
for (const [name, fg, bg] of pairs) {
  const r = ratio(fg, bg);
  if (r < 4.5) {
    bad += 1;
    console.log(`FAIL ${r.toFixed(2)}:1  ${name} (${fg} on ${bg})`);
  }
}
console.log(bad ? `${bad} of ${pairs.length} pairs below 4.5:1` : `all ${pairs.length} pairs meet WCAG AA (4.5:1)`);
process.exit(bad ? 1 : 0);
