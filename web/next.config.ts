import type { NextConfig } from "next";

const apiOrigin = process.env.API_INTERNAL_URL || "http://127.0.0.1:9011";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/health", destination: `${apiOrigin}/health` },
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
      { source: "/docs", destination: `${apiOrigin}/docs` },
      { source: "/docs/:path*", destination: `${apiOrigin}/docs/:path*` },
      { source: "/openapi.json", destination: `${apiOrigin}/openapi.json` },
    ];
  },
};

export default nextConfig;
