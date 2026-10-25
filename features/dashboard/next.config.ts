import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // contracts/ lives outside this folder; allow importing it.
  experimental: { externalDir: true },
  outputFileTracingRoot: path.join(__dirname, "../.."),
  async redirects() {
    return [
      { source: "/dashboard", destination: "/demo", permanent: false },
      { source: "/plan", destination: "/", permanent: false },
      { source: "/plan/new", destination: "/", permanent: false },
      { source: "/plan/:id", destination: "/trip/:id", permanent: false },
      { source: "/plan/:id/:path*", destination: "/trip/:id", permanent: false },
    ];
  },
};

export default nextConfig;
