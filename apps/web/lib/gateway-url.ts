// The gateway URL is baked in at build time (NEXT_PUBLIC_KAIROS_URL), usually http://localhost:8089. A phone that
// opens the console at http://<laptop-LAN-IP>:3000 can't reach "localhost", so when the configured gateway is a
// loopback address and the page came from somewhere else, use the page's host with the configured port.

const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

export function resolveGatewayUrl(configured: string, page?: { protocol: string; hostname: string }): string {
  if (!page || LOOPBACK.has(page.hostname)) return configured;
  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    return configured;
  }
  if (!LOOPBACK.has(url.hostname)) return configured;
  url.hostname = page.hostname;
  url.protocol = page.protocol;
  return url.toString().replace(/\/$/, "");
}
