/** 45 → "45 seconds"; 3600 → "1 hour"; 18720 → "5 hours 12 minutes". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} second${s === 1 ? "" : "s"}`;
  const hours = Math.floor(s / 3600);
  const minutes = Math.ceil((s % 3600) / 60);
  const parts = [];
  if (hours) parts.push(`${hours} hour${hours === 1 ? "" : "s"}`);
  if (minutes && minutes < 60) parts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`);
  return parts.join(" ") || "1 hour";
}
