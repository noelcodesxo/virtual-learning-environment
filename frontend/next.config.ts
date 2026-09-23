import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  experimental: {
    // Exam generation waits for two full LLM responses and can exceed Next's 30-second proxy default.
    proxyTimeout: 500_000,
    // Match the library's 50 MB upload limit so rewritten upload requests are not truncated.
    middlewareClientMaxBodySize: "50mb",
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
};

export default nextConfig;
