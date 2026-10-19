/** "Sent" on a decision card. `fresh`: it was just approved here, so the check pops in and draws itself once. */
export function SentMark({ fresh }: { fresh: boolean }) {
  return (
    <p className="flex items-center gap-2 text-sm font-semibold text-good-ink" role="status" data-testid="sent-mark" data-fresh={fresh}>
      <span className={`flex size-6 items-center justify-center rounded-full bg-good text-white ${fresh ? "sent-pop" : ""}`}>
        <svg viewBox="0 0 16 16" className="size-3.5" fill="none" aria-hidden>
          <path d="M3.5 8.5l3 3 6-7" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" className={fresh ? "sent-check" : ""} />
        </svg>
      </span>
      Sent
    </p>
  );
}
