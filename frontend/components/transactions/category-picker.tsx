"use client";

import { toast } from "sonner";

import { ApiError, type Schemas } from "@/lib/api/client";
import { useRecategorize } from "@/lib/api/hooks";
import { CATEGORIES, CATEGORY } from "@/lib/labels";

/** Set a transaction's category. Saving also adds a rule so the same payee is categorized this way next time. */
export function CategoryPicker({ transaction }: { transaction: Schemas["TransactionOut"] }) {
  const save = useRecategorize();
  return (
    <select
      aria-label={`Category for ${transaction.description.untrusted_text}`}
      value={transaction.category ?? ""}
      disabled={save.isPending}
      onChange={(e) =>
        save.mutate(
          { id: transaction.id, category: e.target.value as Schemas["Category"] },
          {
            onSuccess: (t) => toast.success(`Saved as ${CATEGORY[t.category ?? "other"]}. Similar transactions will follow this rule.`),
            onError: (err) => toast.error(err instanceof ApiError ? err.message : "The category couldn't be saved. Try again."),
          },
        )
      }
      className="h-9 w-full max-w-52 rounded-lg border border-line-strong bg-surface px-2 text-sm text-ink disabled:opacity-60"
    >
      {transaction.category === null && <option value="">Choose a category</option>}
      {CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {CATEGORY[c]}
        </option>
      ))}
    </select>
  );
}
