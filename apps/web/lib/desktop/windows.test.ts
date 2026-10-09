import { describe, expect, it } from "vitest";
import { parseRoute } from "./routes";
import { COMPACT_WIDTH, dockWidth, EMPTY, focused, reduce, type WinState } from "./windows";

const area = { w: 1600, h: 900 };
const open = (s: WinState, url: string, a = area) => reduce(s, { type: "open", url, area: a });

describe("desktop routes", () => {
  it("maps console URLs to apps and window keys", () => {
    expect(parseRoute("/tasks")).toEqual({ app: "tasks", key: "tasks", url: "/tasks" });
    expect(parseRoute("/tasks/T-1")).toEqual({ app: "task", key: "task:T-1", id: "T-1", url: "/tasks/T-1" });
    expect(parseRoute("/audit/T-1")).toMatchObject({ app: "journal", key: "journal:T-1" });
    expect(parseRoute("/knowledge?path=/org/inbox")).toEqual({ app: "files", key: "files", url: "/knowledge?path=/org/inbox" });
    expect(parseRoute("/memory/")).toMatchObject({ app: "memory", url: "/memory" });
    expect(parseRoute("/settings?section=models")).toEqual({ app: "settings", key: "settings", url: "/settings?section=models" });
  });

  it("opens no window for the desktop, boot or unknown paths", () => {
    expect(parseRoute("/")).toBeNull();
    expect(parseRoute("/boot")).toBeNull();
    expect(parseRoute("/nope")).toBeNull();
  });
});

describe("window manager", () => {
  it("opens one window per app, and one per task", () => {
    let s = open(EMPTY, "/tasks");
    s = open(s, "/tasks/T-1");
    s = open(s, "/tasks/T-2");
    s = open(s, "/tasks");
    expect(s.wins.map((w) => w.key)).toEqual(["tasks", "task:T-1", "task:T-2"]);
    expect(focused(s)?.key).toBe("tasks");
  });

  it("navigates an open window in place and brings it to the front", () => {
    let s = open(EMPTY, "/knowledge?path=/org/finance");
    s = open(s, "/memory");
    s = open(s, "/knowledge?path=/org/inbox");
    const files = s.wins.find((w) => w.key === "files")!;
    expect(files.url).toBe("/knowledge?path=/org/inbox");
    expect(focused(s)?.key).toBe("files");
  });

  it("does nothing when the focused window already shows the URL (URL sync cannot loop)", () => {
    const s = open(EMPTY, "/memory");
    expect(open(s, "/memory")).toBe(s);
    expect(reduce(s, { type: "focus", key: "memory" })).toBe(s);
  });

  it("docks a live task to the left, and maximises every window on a phone", () => {
    const task = open(EMPTY, "/tasks/T-1").wins[0];
    expect([task.docked, task.maximized, task.x, task.y, task.w, task.h]).toEqual([true, false, 0, 0, dockWidth(area), area.h]);
    expect(open(EMPTY, "/tasks/T-1", { w: COMPACT_WIDTH - 1, h: 800 }).wins[0]).toMatchObject({ docked: false, maximized: true });
    expect(open(EMPTY, "/memory").wins[0].maximized).toBe(false);
    expect(open(EMPTY, "/memory", { w: COMPACT_WIDTH - 1, h: 800 }).wins[0].maximized).toBe(true);
  });

  it("focus falls to the next window when the top one is minimised or closed", () => {
    let s = open(open(EMPTY, "/tasks"), "/memory");
    s = reduce(s, { type: "minimize", key: "memory" });
    expect(focused(s)?.key).toBe("tasks");
    s = reduce(s, { type: "close", key: "tasks" });
    expect(focused(s)).toBeUndefined();
    s = reduce(s, { type: "focus", key: "memory" });
    expect(focused(s)?.key).toBe("memory");
  });

  it("keeps a moved window's title bar on screen and respects the minimum size", () => {
    let s = open(EMPTY, "/memory");
    s = reduce(s, { type: "move", key: "memory", x: 5000, y: -300, area });
    const w = s.wins[0];
    expect(w.x).toBe(area.w - 80);
    expect(w.y).toBe(0);
    s = reduce(s, { type: "resize", key: "memory", w: 10, h: 10, area });
    let t = open(EMPTY, "/tasks/T-1");
    t = reduce(t, { type: "move", key: "task:T-1", x: 200, y: 40, area });
    expect(t.wins[0].docked).toBe(false);
    expect([s.wins[0].w, s.wins[0].h]).toEqual([360, 240]);
  });
});
