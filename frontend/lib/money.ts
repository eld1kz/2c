// Money arrives from the API as integer minor units (cents) + ISO currency.
// Formatting uses integer arithmetic only: no `/ 100` floats anywhere.

const SYMBOLS: Record<string, string> = { USD: "$" };
export const MINUS = "−"; // typographic minus

function groupThousands(whole: number): string {
  return String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function symbol(currency: string): string {
  return SYMBOLS[currency] ?? `${currency} `;
}

/** 865000 → "$8,650.00"; -199767 → "−$1,997.67"; signed: 365000 → "+$3,650.00"; dropZeroCents: 500000 → "$5,000". */
export function formatCents(cents: number, currency = "USD", opts: { signed?: boolean; dropZeroCents?: boolean } = {}): string {
  if (!Number.isSafeInteger(cents)) throw new Error(`money must be integer cents, got ${cents}`);
  const abs = Math.abs(cents);
  const whole = Math.trunc(abs / 100);
  const minor = abs % 100;
  const cents2 = opts.dropZeroCents && minor === 0 ? "" : `.${String(minor).padStart(2, "0")}`;
  const body = `${symbol(currency)}${groupThousands(whole)}${cents2}`;
  if (cents < 0) return `${MINUS}${body}`;
  return opts.signed && cents > 0 ? `+${body}` : body;
}

/** Axis labels: 1208090 → "$12.1k", -218199 → "−$2.2k", 500000 → "$5k", 0 → "$0". */
export function formatCentsCompact(cents: number, currency = "USD"): string {
  if (!Number.isSafeInteger(cents)) throw new Error(`money must be integer cents, got ${cents}`);
  const abs = Math.abs(cents);
  const sign = cents < 0 ? MINUS : "";
  if (abs < 100_000) return `${sign}${symbol(currency)}${groupThousands(Math.trunc((abs + 50) / 100))}`;
  const tenths = Math.trunc((abs + 5_000) / 10_000); // thousands × 10, rounded half up
  const k = tenths % 10 === 0 ? `${tenths / 10}` : `${Math.trunc(tenths / 10)}.${tenths % 10}`;
  return `${sign}${symbol(currency)}${k}k`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-05" → "Nov 5" (no Date objects, so no time-zone drift). */
export function formatDay(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}`;
}

/** "2026-10-01" → "Oct 1, 2026". */
export function formatDate(iso: string): string {
  return `${formatDay(iso)}, ${iso.slice(0, 4)}`;
}
