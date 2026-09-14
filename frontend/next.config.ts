import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  experimental: {
    // Exam generation waits for a full LLM response and can exceed Next's 30-second proxy default.
    proxyTimeout: 300_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
};

export default nextConfig;
