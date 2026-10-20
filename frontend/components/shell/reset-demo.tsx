"use client";

import { RotateCcwIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { AlertDialog } from "radix-ui";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useMe, useResetDemo } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";

/** Owner only: puts the demo back to its starting data. The audit log is kept and records the reset. */
export function ResetDemo({ className, onDone }: { className?: string; onDone?: () => void }) {
  const me = useMe().data;
  const reset = useResetDemo();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  if (me?.user.role !== "owner") return null;
  const run = () =>
    reset.mutate(undefined, {
      onSuccess: () => {
        setOpen(false);
        onDone?.();
        toast.success("Demo data reset. The audit log kept every earlier event.");
        router.push("/today");
      },
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "The reset didn't finish. Try again."),
    });
  return (
    <AlertDialog.Root open={open} onOpenChange={setOpen}>
      <AlertDialog.Trigger asChild>
        <button className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink-2 hover:bg-sunken", className)}>
          <RotateCcwIcon className="size-[18px]" />
          Reset demo data
        </button>
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-ink/30" />
        <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-panel)] bg-surface p-5 shadow-xl">
          <AlertDialog.Title className="text-base font-semibold">Reset the demo data?</AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-sm leading-relaxed text-ink-2">
            Transactions, invoices, findings, the forecast, approvals, sandbox emails and payments, and chat conversations go back to how the demo
            started. The audit log is kept as it is and records this reset.
          </AlertDialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Button variant="secondary" disabled={reset.isPending}>
                Cancel
              </Button>
            </AlertDialog.Cancel>
            <Button variant="risk" onClick={run} disabled={reset.isPending}>
              {reset.isPending ? "Resetting…" : "Reset demo data"}
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
