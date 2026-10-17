import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { backendUrl, isSameOrigin, sessionCookie } from "@/lib/session";

// Exchanges email + password for a backend JWT and keeps it in an httpOnly cookie.
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request.headers.get("origin"), request.headers.get("host"))) {
    return Response.json({ detail: "cross-site request refused" }, { status: 403 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl()}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "The server can't be reached. Check that the backend is running." }, { status: 502 });
  }
  const body = await upstream.json().catch(() => ({ detail: "unexpected response from the server" }));
  if (!upstream.ok) {
    const headers = new Headers();
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) headers.set("Retry-After", retryAfter);
    return Response.json({ detail: body.detail ?? "sign-in failed" }, { status: upstream.status, headers });
  }
  (await cookies()).set(sessionCookie(body.access_token, body.expires_at));
  return Response.json({ role: body.role, expires_at: body.expires_at });
}
