// Server-only session settings. The JWT lives in an httpOnly cookie: browser JavaScript never sees it.

export const SESSION_COOKIE = "lw_session";

export function backendUrl(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

export function sessionCookie(token: string, expiresAt: string) {
  return {
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict" as const,
    path: "/",
    expires: new Date(expiresAt),
  };
}

/** Same-origin check for state-changing requests (CSRF defence on top of SameSite=Strict). */
export function isSameOrigin(origin: string | null, host: string | null): boolean {
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
