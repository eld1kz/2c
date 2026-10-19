import { Help } from "@/components/glossary/help";
import type { TermId } from "@/lib/glossary";

/** One statement on the paperwork pages: a titled panel that starts on a fresh page when printed. */
export function Panel({ id, title, subtitle, term, children }: { id: string; title: string; subtitle?: string; term?: TermId; children: React.ReactNode }) {
  return (
    <section
      aria-labelledby={id}
      className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5 print:break-inside-avoid print:rounded-none print:border-0 print:p-0"
    >
      <div className="flex items-center gap-1">
        <h2 id={id} className="text-[15px] font-semibold">
          {title}
        </h2>
        {term && <Help term={term} />}
      </div>
      {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}
