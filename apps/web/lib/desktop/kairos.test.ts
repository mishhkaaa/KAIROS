import { describe, expect, it } from "vitest";
import { folderOf, layoutKairos, tileAt } from "./kairos";

const docs = [
  ...["apollo-budget", "cloud-bill-2026-08", "cloud-bill-2026-09", "q3-forecast"].map((n) => ({ path: `/org/finance/${n}` })),
  ...["vendor-email-2026-09-12", "email-cto-escalation"].map((n) => ({ path: `/org/inbox/${n}` })),
  ...["apollo-12", "apollo-14", "apollo-18"].map((n) => ({ path: `/org/jira/${n}` })),
  { path: "/org/slack/apollo-eng/2026-09-10" },
];

describe("wallpaper kairos", () => {
  const m = layoutKairos(docs, 1600, 900);

  it("gives every document exactly one tessera, and no two share a cell", () => {
    expect(m.tiles.map((t) => t.path).sort()).toEqual(docs.map((d) => d.path).sort());
    expect(new Set(m.tiles.map((t) => `${t.col},${t.row}`)).size).toBe(docs.length);
  });

  it("keeps the top bar row and the dock rows clear", () => {
    expect(m.tiles.every((t) => t.row >= 1 && t.row < m.rows - 3)).toBe(true);
  });

  it("clusters each folder around its own seed and labels it", () => {
    const finance = m.tiles.filter((t) => t.folder === "finance");
    const spread = Math.max(...finance.map((t) => t.col)) - Math.min(...finance.map((t) => t.col));
    expect(spread).toBeLessThanOrEqual(2);
    expect(m.labels.map((l) => l.folder).sort()).toEqual(["finance", "inbox", "jira", "slack"]);
    expect(folderOf("/org/slack/apollo-eng/2026-09-10")).toBe("slack");
  });

  it("is deterministic and finds a tile under a point", () => {
    expect(layoutKairos(docs, 1600, 900)).toEqual(m);
    const t = m.tiles[0];
    expect(tileAt(m, t.col * m.cell + 3, t.row * m.cell + 3)?.path).toBe(t.path);
    expect(tileAt(m, 1, 1)).toBeUndefined();
  });

  it("keeps the box the desktop draws over clear", () => {
    const a = layoutKairos(docs, 1600, 900, 26, { cx: 0.42, rx: 0.31, avoid: [0.25, 0.05, 0.6, 0.45] });
    expect(a.tiles).toHaveLength(docs.length);
    expect(a.tiles.every((t) => !(t.col >= 0.25 * a.cols && t.col <= 0.6 * a.cols && t.row >= 0.05 * a.rows && t.row <= 0.45 * a.rows))).toBe(true);
  });

  it("keeps several boxes clear (the centred Ask bar and the widget column)", () => {
    const hero: [number, number, number, number] = [0.27, 0.1, 0.73, 0.5];
    const widgets: [number, number, number, number] = [0.78, 0, 1, 1];
    const a = layoutKairos(docs, 1600, 900, 28, { cx: 0.5, rx: 0.34, cy: 0.5, ry: 0.36, avoid: [hero, widgets] });
    expect(a.tiles).toHaveLength(docs.length);
    const inside = (t: { col: number; row: number }, [x0, y0, x1, y1]: number[]) =>
      t.col >= x0 * a.cols && t.col <= x1 * a.cols && t.row >= y0 * a.rows && t.row <= y1 * a.rows;
    expect(a.tiles.some((t) => inside(t, hero) || inside(t, widgets))).toBe(false);
  });

  it("can lay the patches out as a border round a frame, with names clear of the top bar", () => {
    const a = layoutKairos(docs, 1600, 900, 30, { frame: [0.06, 0.1, 0.72, 0.8], avoid: [[0.26, 0.17, 0.74, 0.5], [0.78, 0, 1, 1]] });
    expect(a.tiles).toHaveLength(docs.length);
    expect(a.labels.every((l) => l.y > 30)).toBe(true);
    const cols = new Set(a.labels.map((l) => Math.round(l.x / 100)));
    expect(cols.size).toBeGreaterThan(1);
  });
});
