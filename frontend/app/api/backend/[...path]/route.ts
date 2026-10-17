import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { isAllowed } from "@/lib/backend-routes";
import { backendUrl, isSameOrigin, SESSION_COOKIE } from "@/lib/session";

// Same-origin gateway to the FastAPI backend: attaches the bearer token from the httpOnly cookie
// and streams the response back untouched (the chat endpoint is server-sent events).
const PASS_HEADERS = ["content-type", "retry-after", "cache-control"];

async function forward(request: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const path = (await ctx.params).path.join("/");
  if (!isAllowed(request.method, path)) {
    return Response.json({ detail: "not available" }, { status: 404 });
  }
  if (request.method !== "GET" && !isSameOrigin(request.headers.get("origin"), request.headers.get("host"))) {
    return Response.json({ detail: "cross-site request refused" }, { status: 403 });
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return Response.json({ detail: "not authenticated" }, { status: 401 });

  const headers = new Headers({ Authorization: `Bearer ${token}` });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl()}/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : request.body,
      // @ts-expect-error: `duplex` is required by Node's fetch to stream a request body
      duplex: "half",
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return Response.json({ detail: "The server can't be reached. Check that the backend is running." }, { status: 502 });
  }
  const out = new Headers();
  for (const name of PASS_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
