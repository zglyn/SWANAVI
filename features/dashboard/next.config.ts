import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // contracts/ lives outside this folder; allow importing it.
  experimental: { externalDir: true },
  outputFileTracingRoot: path.join(__dirname, "../.."),
  async redirects() {
    return [{ source: "/dashboard", destination: "/demo", permanent: false }];
  },
};

export default nextConfig;
