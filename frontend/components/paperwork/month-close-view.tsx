"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useMonthClose } from "@/lib/api/hooks";
import { cashFlowRows, pnlRows } from "@/lib/statements";

import { AgingTable } from "./aging-table";
import { Disclaimer } from "./disclaimer";
import { Panel } from "./panel";
import { ReconciliationTable } from "./reconciliation-table";
import { StatementTable } from "./statement-table";

/** "Close my month": the last full month's reconciliation, P&L, cash flow and AR/AP aging. */
export function MonthCloseView() {
  const { data, isError } = useMonthClose();
  if (isError) return <p className="text-sm text-risk-ink">The month-end reports couldn&apos;t be loaded. Refresh the page to try again.</p>;
  if (!data) return <Skeleton className="h-96" />;
  const { currency, period } = data;
  return (
    <div className="space-y-5">
      <Disclaimer disclaimer={data.disclaimer} basis={data.basis} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel id="rec-title" title="Bank reconciliation" subtitle={`${period.label}: your books against the bank statement`}>
          <ReconciliationTable rec={data.reconciliation} currency={currency} />
        </Panel>
        <Panel id="cf-title" title="Cash-flow statement" subtitle={`${period.label}: where the cash came from and went`}>
          <StatementTable columns={[period.label]} rows={cashFlowRows([data.cash_flow])} currency={currency} label="Cash-flow statement" />
        </Panel>
      </div>
      <Panel id="pnl-title" title="Profit and loss" subtitle={`${period.label}, cash basis, ${data.profit_and_loss.transaction_count} transactions`}>
        <StatementTable columns={[period.label]} rows={pnlRows([data.profit_and_loss])} currency={currency} label="Profit and loss" />
      </Panel>
      <Panel id="ar-title" title="Money customers owe you" subtitle="Receivables aging: open invoices by how late they are">
        <AgingTable aging={data.receivables} currency={currency} label="Receivables" />
      </Panel>
      <Panel id="ap-title" title="Bills you owe" subtitle="Payables aging: open supplier bills by how late they are">
        <AgingTable aging={data.payables} currency={currency} label="Payables" />
      </Panel>
    </div>
  );
}
