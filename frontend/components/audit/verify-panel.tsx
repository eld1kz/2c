"use client";

import { ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useVerifyChain } from "@/lib/api/hooks";

/** Recomputes the whole hash chain on the server and says whether every event still matches. */
export function VerifyPanel() {
  const verify = useVerifyChain();
  const r = verify.data;
  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-surface p-4 md:p-5" aria-labelledby="verify-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="max-w-prose">
          <h2 id="verify-title" className="text-[15px] font-semibold">
            Tamper check
          </h2>
          <p className="mt-0.5 text-sm text-ink-3">
            Each event stores a hash of itself and of the event before it, so editing or deleting any event breaks every hash after it.
          </p>
        </div>
        <Button onClick={() => verify.mutate()} disabled={verify.isPending}>
          {verify.isPending ? "Verifying…" : "Verify chain"}
        </Button>
      </div>
      {r?.ok && (
        <p role="status" className="mt-4 flex gap-2 rounded-lg bg-good-soft px-3 py-2.5 text-sm text-good-ink">
          <ShieldCheckIcon className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-semibold">Chain intact.</span> <span className="num">{r.checked.toLocaleString("en-US")}</span> events checked; every hash
            matches. This covers every event in this deployment, not only this business&apos;s.
          </span>
        </p>
      )}
      {r && !r.ok && (
        <p role="alert" className="mt-4 flex gap-2 rounded-lg bg-risk-soft px-3 py-2.5 text-sm text-risk-ink">
          <ShieldAlertIcon className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-semibold">Chain broken at event #{r.broken_at_seq}.</span> {r.reason ?? "A hash doesn't match."} Events from #
            {r.broken_at_seq} on can&apos;t be trusted; {r.checked.toLocaleString("en-US")} events were checked.
          </span>
        </p>
      )}
      {verify.isError && <p className="mt-4 text-sm text-risk-ink">The check couldn&apos;t run. Try again.</p>}
    </section>
  );
}
