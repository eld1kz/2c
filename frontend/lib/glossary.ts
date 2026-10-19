/** Plain-English "What is this?" definitions for financial terms (Today, Team, What-if, Paperwork). */
export const GLOSSARY = {
  cushion: { term: "Cushion", text: "The minimum cash you want to keep in the bank for surprises. Ledgerwise warns you about any week that would end below it." },
  forecast: { term: "13-week forecast", text: "A week-by-week estimate of your bank balance for the next 13 weeks, built from your bills, invoices and usual spending. It is an estimate, not a promise." },
  closing_cash: { term: "Closing cash", text: "The money in the bank at the end of a week, after everything that comes in and goes out that week." },
  cash_gap: { term: "Cash gap", text: "A stretch of weeks when your cash is forecast to fall below your cushion. The gap is how much more cash you would need to stay above it." },
  safe_to_spend: { term: "Safe to spend", text: "Your cash now, minus your cushion, minus the bills due in the next 7 days. It is what you could spend this week even if no money came in." },
  bill: { term: "Bill", text: "A payment you have to make, like rent, payroll, software or a supplier invoice." },
  what_if: { term: "What-if", text: "A simulation of your forecast with one change, like a customer paying early or a new cost. Nothing in your books changes." },
  assumption: { term: "Assumption", text: "Something you tell the simulation to imagine, like a new hire's pay. It is not taken from your records." },
  payroll: { term: "Payroll", text: "The wages you pay your staff, usually on a fixed schedule like every week." },
  receivable: { term: "Receivable", text: "Money a customer owes you for an invoice you sent and they haven't paid yet." },
  payable: { term: "Payable", text: "Money you owe a supplier for an invoice they sent you that you haven't paid yet." },
  aging: { term: "Aging", text: "Open invoices grouped by how late they are: not yet due, 1–30 days late, 31–60 days late, and so on." },
  payment_terms: { term: "Payment terms", text: "How long you have to pay an invoice. \"Net 30\" means payment is due 30 days after the invoice date." },
  factoring: { term: "Invoice factoring", text: "Selling your unpaid invoices to a finance company for cash now, minus a fee. The company then collects from your customer." },
  apr: { term: "APR", text: "Annual percentage rate: the yearly cost of borrowing as a percentage of the amount. 12% APR on $1,000 for a full year costs about $120." },
  profit_and_loss: { term: "Profit and loss", text: "A report of the money you earned and the money you spent over a period, and what was left over." },
  cash_basis: { term: "Cash basis", text: "Income and costs are counted when the money actually moves in or out of the bank, not when an invoice is sent." },
  revenue: { term: "Income (revenue)", text: "Money that came in from selling your products or services." },
  cogs: { term: "Cost of goods sold", text: "What you spent on the things you sell, like green coffee beans and packaging." },
  operating_expenses: { term: "Operating expenses", text: "The everyday costs of running the business that aren't the products themselves, like rent, payroll and software." },
  net_profit: { term: "Net profit", text: "What is left after all costs are taken from your income. If it is negative, it is a loss." },
  cash_flow_statement: { term: "Cash-flow statement", text: "Shows where cash came from and where it went over a period, from the opening bank balance to the closing one." },
  bank_reconciliation: { term: "Bank reconciliation", text: "Checking that the balance in your books matches the balance on the bank statement. A difference of $0.00 means they agree." },
  fixed_obligations: { term: "Fixed obligations", text: "Regular payments you are committed to, like rent and equipment leases, that a lender will want to know about." },
} as const satisfies Record<string, { term: string; text: string }>;

export type TermId = keyof typeof GLOSSARY;
