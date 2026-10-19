"use client";

import { CheckIcon, MinusIcon, ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";
import Link from "next/link";

import { Money } from "@/components/money";
import { Skeleton } from "@/components/ui/skeleton";
import { useTrust } from "@/lib/api/hooks";
import { formatDate } from "@/lib/money";

const ROLES = ["owner", "accountant", "viewer"] as const;

const TIER_TEXT: Record<string, string> = {
  READ: "Reads your books",
  SUGGEST: "Drafts and simulates; never sends",
  EXECUTE: "Only proposes; a person approves",
};

const ACTIVITY: { key: string; label: string; tone?: "risk" }[] = [
  { key: "agent_tool_called", label: "Tool calls by the assistant" },
  { key: "action_proposed", label: "Actions proposed" },
  { key: "action_approved", label: "Approved by a person" },
  { key: "action_executed", label: "Executed in the sandbox" },
  { key: "action_rejected", label: "Rejected by a person" },
  { key: "action_denied", label: "Refused by the policy gate", tone: "risk" },
  { key: "role_refused", label: "Refused for the role", tone: "risk" },
  { key: "agent_citation_failed", label: "Answers with unverified figures", tone: "risk" },
];

function label(tool: string): string {
  return tool.replaceAll("_", " ");
}

function Tick({ on, what }: { on: boolean; what: string }) {
  return on ? (
    <CheckIcon className="mx-auto size-4 text-good-ink" aria-label={`yes: ${what}`} />
  ) : (
    <MinusIcon className="mx-auto size-4 text-ink-3" aria-label={`no: ${what}`} />
  );
}

/**
 * What the AI may and may not do, the limits the payment gate enforces, and what the audit log shows the
 * guardrails did. Everything comes from GET /trust, which reads the same tables the gate and RBAC use.
 */
export function TrustView() {
  const { data, isError } = useTrust();
  if (isError) return <p className="text-sm text-risk-ink">The trust report couldn&apos;t be loaded. Refresh the page to try again.</p>;
  if (!data) return <Skeleton className="h-96" />;
  const l = data.limits;
  const tiers = ["READ", "SUGGEST", "EXECUTE"].map((tier) => ({ tier, tools: data.boundaries.filter((b) => b.tier === tier) }));

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header className="pt-2 md:pt-4">
        <h1 className="font-display text-[30px] leading-[1.15] font-medium tracking-[-0.01em] text-ink md:text-[38px]">Trust &amp; guardrails</h1>
        <p className="mt-2 text-[17px] text-ink-2">
          The assistant can read, draft and propose. It can never approve, pay or send anything by itself.
        </p>
        <p className={`mt-3 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${data.chain.ok ? "bg-good-soft text-good-ink" : "bg-risk-soft text-risk-ink"}`} data-testid="trust-chain">
          {data.chain.ok ? <ShieldCheckIcon className="size-4" /> : <ShieldAlertIcon className="size-4" />}
          {data.chain.ok
            ? `Audit log intact: ${data.chain.checked.toLocaleString("en-US")} events verified`
            : `Audit log broken at event #${data.chain.broken_at_seq}: ${data.chain.reason}`}
          <Link href="/audit" className="font-medium underline underline-offset-2">Audit log</Link>
        </p>
      </header>

      <section aria-labelledby="trust-limits">
        <h2 id="trust-limits" className="text-lg font-semibold text-ink">Hard limits, enforced in code</h2>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          {[
            ["Largest single payment", <Money key="m" cents={l.max_single_payment} currency={l.currency} />],
            ["All payments on one day", <Money key="d" cents={l.max_daily_payments} currency={l.currency} />],
            ["Payees", "Only known suppliers, to their stored bank details"],
            ["Reminders per invoice", `At most 1 every ${l.reminder_cooldown_days} days`],
            ["Proposals per question", `At most ${l.max_proposals_per_turn}`],
            ["Assistant steps per question", `At most ${l.max_model_calls_per_turn}`],
            ["AI spend per day", <Money key="b" cents={l.daily_ai_budget_cents} currency="USD" />],
            ["Approvals", "People only: owner, or accountant for reminders"],
          ].map(([k, v]) => (
            <div key={k as string} className="rounded-lg border border-line bg-surface px-4 py-3">
              <dt className="text-xs text-ink-3">{k}</dt>
              <dd className="num mt-0.5 text-sm font-medium text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="trust-activity">
        <h2 id="trust-activity" className="text-lg font-semibold text-ink">Guardrails at work</h2>
        <p className="mt-1 text-sm text-ink-3">Counted from this business&apos;s audit log.</p>
        <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          {ACTIVITY.map((a) => (
            <div key={a.key} className="rounded-lg border border-line bg-surface px-3 py-3" data-testid={`trust-${a.key}`}>
              <dd className={`num text-2xl font-semibold ${a.tone && (data.activity[a.key] ?? 0) > 0 ? "text-risk-ink" : "text-ink"}`}>
                {(data.activity[a.key] ?? 0).toLocaleString("en-US")}
              </dd>
              <dt className="mt-0.5 text-xs text-ink-3">{a.label}</dt>
            </div>
          ))}
        </dl>
        {data.recent_denials.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium text-ink-2">Latest refusals by the policy gate</p>
            <ul className="mt-1.5 divide-y divide-line rounded-lg border border-line bg-surface">
              {data.recent_denials.map((d) => (
                <li key={d.seq} className="px-3 py-2 text-sm">
                  <span className="font-medium text-ink">{d.tool ? label(d.tool) : "action"}</span>
                  <span className="text-ink-3"> · event #{d.seq} · {formatDate(d.ts.slice(0, 10))}</span>
                  <p className="text-ink-2">{d.reason}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section aria-labelledby="trust-boundaries">
        <h2 id="trust-boundaries" className="text-lg font-semibold text-ink">What the assistant can do</h2>
        <p className="mt-1 text-sm text-ink-3">Built from the same permission tables the policy gate checks. There is no approve tool for the assistant.</p>
        <div className="mt-3 overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-sm" aria-label="Assistant tools and who may use them">
            <thead className="bg-sunken/60 text-xs text-ink-3">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Tool</th>
                {ROLES.map((r) => (
                  <th key={r} className="px-2 py-2 text-center font-medium capitalize">{r}</th>
                ))}
              </tr>
            </thead>
            {tiers.map(({ tier, tools }) => (
              <tbody key={tier} className="border-t border-line">
                <tr>
                  <th colSpan={4} className="px-3 pt-3 pb-1 text-left text-xs font-semibold text-ink-2">
                    {tier} · {TIER_TEXT[tier]}
                  </th>
                </tr>
                {tools.map((b) => (
                  <tr key={b.tool}>
                    <td className="px-3 py-1.5 text-ink">
                      {label(b.tool)}
                      {tier === "EXECUTE" && <span className="block text-xs text-ink-3">Approved by: {b.approve.join(", ") || "nobody"}</span>}
                    </td>
                    {ROLES.map((r) => (
                      <td key={r} className="px-2 py-1.5">
                        <Tick on={b.propose.includes(r)} what={`${r} may use ${label(b.tool)}`} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      </section>
    </div>
  );
}
