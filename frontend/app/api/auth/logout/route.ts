import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { isSameOrigin, SESSION_COOKIE } from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request.headers.get("origin"), request.headers.get("host"))) {
    return Response.json({ detail: "cross-site request refused" }, { status: 403 });
  }
  (await cookies()).delete(SESSION_COOKIE);
  return new Response(null, { status: 204 });
}
