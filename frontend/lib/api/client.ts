import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/** Error with the backend's status, `detail` and Retry-After (seconds), for UI states. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly retryAfter: number | null = null,
  ) {
    super(message);
  }
}

const redirectOn401: Middleware = {
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload drops cached data
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  },
};

export const api = createClient<paths>({ baseUrl: "/api/backend" });
api.use(redirectOn401);

export function detailOf(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "The request was not valid.";
  return "Something went wrong. Try again.";
}

/** Unwraps an openapi-fetch result: returns data or throws ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined && result.response.ok) return result.data;
  const retry = result.response.headers.get("retry-after");
  throw new ApiError(result.response.status, detailOf(result.error), retry ? Number(retry) : null);
}
