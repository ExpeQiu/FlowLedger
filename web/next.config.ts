import type { NextConfig } from "next";

const apiOrigin = process.env.API_INTERNAL_URL || "http://127.0.0.1:9011";

const nextConfig: NextConfig = {
  async rewrites() {
    // /api/* 由 app/api/[...path]/route.ts 注入 INTERNAL_TOKEN 后转发
    return [
      { source: "/health", destination: `${apiOrigin}/health` },
      { source: "/docs", destination: `${apiOrigin}/docs` },
      { source: "/docs/:path*", destination: `${apiOrigin}/docs/:path*` },
      { source: "/openapi.json", destination: `${apiOrigin}/openapi.json` },
    ];
  },
  // 禁用所有页面缓存：财务数据必须实时
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Cache-Control", value: "no-store, no-cache, must-revalidate, max-age=0" },
          { key: "Pragma", value: "no-cache" },
          { key: "Expires", value: "0" },
          { key: "X-Accel-Expires", value: "0" },
        ],
      },
    ];
  },
  // 关闭 Next.js 静态预渲染（财务页面需要动态数据）
  experimental: {
    // 确保不使用 ISR 缓存
  },
  // dev 模式：避免预渲染
  productionBrowserSourceMaps: false,
};

export default nextConfig;
