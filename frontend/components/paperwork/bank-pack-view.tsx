"use client";

import { DownloadIcon } from "lucide-react";

import { ForecastTable } from "@/components/dashboard/forecast-table";
import { useEvidence } from "@/components/evidence/evidence-provider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useBankPack } from "@/lib/api/hooks";
import { formatCents, formatDate } from "@/lib/money";
import { cashFlowRows, NOT_INCLUDED, pnlRows } from "@/lib/statements";

import { AgingTable } from "./aging-table";
import { Disclaimer } from "./disclaimer";
import { ObligationsTable } from "./obligations-table";
import { Panel } from "./panel";
import { StatementTable } from "./statement-table";

/** "Get bank-ready": statements, forecast, obligations and receivables in one printable pack. */
export function BankPackView() {
  const { data, isError } = useBankPack();
  const evidence = useEvidence();
  if (isError) return <p className="text-sm text-risk-ink">The bank-ready pack couldn&apos;t be loaded. Refresh the page to try again.</p>;
  if (!data) return <Skeleton className="h-96" />;
  const { currency } = data;
  const columns = data.profit_and_loss.map((p, i) => (i < data.months.length ? p.period.label.split(" ")[0] : "Total"));
  return (
    <div className="space-y-5" data-testid="bank-pack">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">{data.business_name}</p>
          <p className="text-sm text-ink-3">Financial summary as of {formatDate(data.as_of)}</p>
        </div>
        <Button variant="secondary" onClick={() => window.print()} className="print:hidden">
          <DownloadIcon />
          Download PDF
        </Button>
      </div>
      <Disclaimer disclaimer={data.disclaimer} basis={data.basis} />
      <Panel id="pack-pnl" title="Profit and loss" subtitle={`Last ${data.months.length} months, cash basis`}>
        <StatementTable columns={columns} rows={pnlRows(data.profit_and_loss)} currency={currency} label="Profit and loss, by month" />
      </Panel>
      <Panel id="pack-cf" title="Cash-flow statement" subtitle={`Last ${data.months.length} months`}>
        <StatementTable columns={columns} rows={cashFlowRows(data.cash_flow)} currency={currency} label="Cash flow, by month" />
      </Panel>
      <Panel id="pack-fc" title="13-week cash forecast" subtitle={`Weekly closing cash; minimum buffer ${formatCents(data.min_cash_buffer_cents, currency)}`}>
        <ForecastTable weeks={data.forecast} currency={currency} onSelectWeek={(w) => evidence?.open(`forecast_week:${w}`)} />
      </Panel>
      <Panel
        id="pack-ob"
        title="Fixed obligations"
        subtitle="Rent and lease payments from your recurring payments. Not a loan statement: no principal or interest data."
      >
        <ObligationsTable obligations={data.obligations} currency={currency} />
      </Panel>
      <Panel id="pack-ar" title="Receivables aging" subtitle="Open customer invoices by how late they are">
        <AgingTable aging={data.receivables} currency={currency} label="Receivables" />
      </Panel>
      <Panel id="pack-ni" title="Not included" subtitle="This pack is built only from your bank and invoice records. A lender may also ask for:">
        <ul className="space-y-2 text-sm" data-testid="not-included">
          {NOT_INCLUDED.map((item) => (
            <li key={item.title}>
              <span className="font-medium">{item.title}.</span> <span className="text-ink-2">{item.why}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
