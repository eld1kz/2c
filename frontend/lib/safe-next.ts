/** Only same-site paths are valid post-login destinations (no open redirect). */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\") || next.startsWith("/login")) {
    return "/today";
  }
  return next;
}
