import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // contracts/ lives outside this folder; allow importing it.
  experimental: { externalDir: true },
  outputFileTracingRoot: path.join(__dirname, "../.."),
};

export default nextConfig;
