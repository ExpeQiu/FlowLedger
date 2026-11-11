import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const apiOrigin = (process.env.API_INTERNAL_URL || "http://127.0.0.1:9011").replace(/\/$/, "");

async function proxy(req: NextRequest, path: string[]) {
  const search = req.nextUrl.search || "";
  const target = `${apiOrigin}/api/${path.join("/")}${search}`;
  const headers = new Headers();
  const accept = req.headers.get("accept");
  const contentType = req.headers.get("content-type");
  if (accept) headers.set("accept", accept);
  if (contentType) headers.set("content-type", contentType);
  const token =
    (process.env.INTERNAL_TOKEN || "").trim() ||
    (process.env.DATA_INTERNAL_TOKEN || "").trim();
  if (token) {
    headers.set("X-Internal-Token", token);
  }
  // 透传客户端已带令牌（AgentCenter → 8900）
  const clientTok =
    req.headers.get("x-internal-token") ||
    req.headers.get("x-api-token") ||
    (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  if (clientTok && !headers.has("X-Internal-Token")) {
    headers.set("X-Internal-Token", clientTok);
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const outHeaders = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) outHeaders.set("content-type", ct);
  outHeaders.set("cache-control", "no-store");
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: outHeaders,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
