import { describe, expect, it } from "vitest";
import { columns, commonPrefix, resolvePath, splitArgs } from "./shell";

describe("terminal shell", () => {
  it("splits arguments with quotes", () => {
    expect(splitArgs(`ai-run "why is Apollo late?" now`)).toEqual(["ai-run", "why is Apollo late?", "now"]);
    expect(splitArgs("  ls   /org/finance ")).toEqual(["ls", "/org/finance"]);
  });

  it("resolves paths inside /org", () => {
    expect(resolvePath("/org", "finance")).toBe("/org/finance");
    expect(resolvePath("/org/finance", "../inbox/vendor-email-2026-09-12")).toBe("/org/inbox/vendor-email-2026-09-12");
    expect(resolvePath("/org/finance", "/org/jira")).toBe("/org/jira");
    expect(resolvePath("/org/finance", "../../..")).toBe("/org");
    expect(resolvePath("/org/finance", "/etc/passwd")).toBe("/org");
    expect(resolvePath("/org/finance")).toBe("/org");
  });

  it("lines up columns and completes common prefixes", () => {
    expect(columns([["PID", "AGENT"], [101, "planner-agent"]])).toEqual(["PID  AGENT", "101  planner-agent"]);
    expect(commonPrefix(["cloud-bill-2026-08", "cloud-bill-2026-09"])).toBe("cloud-bill-2026-0");
    expect(commonPrefix([])).toBe("");
  });
});
