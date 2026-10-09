import { describe, expect, it } from "vitest";
import { resolveGatewayUrl } from "./gateway-url";

const lan = { protocol: "http:", hostname: "192.168.137.1" };

describe("gateway URL", () => {
  it("follows the page's host when the build points at localhost (a phone on the laptop's hotspot)", () => {
    expect(resolveGatewayUrl("http://localhost:8089", lan)).toBe("http://192.168.137.1:8089");
    expect(resolveGatewayUrl("http://127.0.0.1:8089/", lan)).toBe("http://192.168.137.1:8089");
  });
  it("keeps the configured URL on the laptop itself, on the server, and for a real host name", () => {
    expect(resolveGatewayUrl("http://localhost:8089", { protocol: "http:", hostname: "localhost" })).toBe("http://localhost:8089");
    expect(resolveGatewayUrl("http://localhost:8089")).toBe("http://localhost:8089");
    expect(resolveGatewayUrl("http://node.tailnet.ts.net:8080", lan)).toBe("http://node.tailnet.ts.net:8080");
  });
});
