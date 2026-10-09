import { describe, expect, it } from "vitest";
import { artifactUrl } from "./kairos-client";

describe("artifactUrl", () => {
  it("maps an artifact ref to the gateway route, keeping sub-folders", () => {
    expect(artifactUrl("http://gw", "artifact://T-1/recovery-plan.md")).toBe("http://gw/tasks/T-1/artifacts/recovery-plan.md");
    expect(artifactUrl("http://gw", "artifact://T-1/screenshots/001.png")).toBe("http://gw/tasks/T-1/artifacts/screenshots/001.png");
  });

  it("encodes each segment and rejects non-artifact refs", () => {
    expect(artifactUrl("http://gw", "artifact://T-1/a b#c.md")).toBe("http://gw/tasks/T-1/artifacts/a%20b%23c.md");
    expect(artifactUrl("http://gw", "/org/finance/apollo-budget")).toBeNull();
  });
});
