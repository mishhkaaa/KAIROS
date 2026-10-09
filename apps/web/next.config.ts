import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @kairos/contracts is TypeScript source in shared/ts, linked with file:, so Next compiles it, and Turbopack's
  // root must include both apps/web and shared/ts (the repo root) to resolve the link.
  transpilePackages: ["@kairos/contracts"],
  // A second build can live beside the kiosk's (NEXT_DIST_DIR=.next-preview) without replacing the one it serves.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  turbopack: { root: path.join(__dirname, "..", "..") },
};

export default nextConfig;
