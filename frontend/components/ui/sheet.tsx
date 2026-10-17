"use client";

import { ArrowLeftIcon, XIcon } from "lucide-react";
import { Dialog } from "radix-ui";

import { cn } from "@/lib/cn";

// Side panel on desktop, bottom sheet on phones.
export const Sheet = Dialog.Root;
export const SheetTrigger = Dialog.Trigger;
export const SheetClose = Dialog.Close;

export function SheetContent({
  title,
  description,
  children,
  className,
  onBack,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  onBack?: () => void;
}) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
      <Dialog.Content
        className={cn(
          "fixed z-50 flex flex-col bg-surface shadow-[0_-8px_40px_rgba(24,33,58,0.18)] outline-none",
          "inset-x-0 bottom-0 max-h-[88dvh] rounded-t-[var(--radius-panel)]",
          "md:inset-y-0 md:right-0 md:left-auto md:max-h-none md:w-[440px] md:rounded-none md:rounded-l-[var(--radius-panel)]",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          {onBack && (
            <button onClick={onBack} className="-ml-1 rounded-md p-1 text-ink-3 hover:bg-sunken hover:text-ink" aria-label="Back">
              <ArrowLeftIcon className="size-5" />
            </button>
          )}
          <div className="min-w-0 flex-1">
            <Dialog.Title className="text-base font-semibold text-ink">{title}</Dialog.Title>
            {description ? (
              <Dialog.Description className="mt-0.5 text-sm text-ink-3">{description}</Dialog.Description>
            ) : (
              <Dialog.Description className="sr-only">Details</Dialog.Description>
            )}
          </div>
          <Dialog.Close className="-mr-1 rounded-md p-1 text-ink-3 hover:bg-sunken hover:text-ink" aria-label="Close">
            <XIcon className="size-5" />
          </Dialog.Close>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </Dialog.Content>
    </Dialog.Portal>
  );
}
