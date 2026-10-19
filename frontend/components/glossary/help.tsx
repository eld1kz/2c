"use client";

import { CircleHelpIcon } from "lucide-react";
import { Popover } from "radix-ui";

import { GLOSSARY, type TermId } from "@/lib/glossary";

/** A small "What is this?" button next to a financial term; opens a one- or two-sentence plain-English definition. */
export function Help({ term }: { term: TermId }) {
  const g = GLOSSARY[term];
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={`What is this? ${g.term}`}
        data-term={term}
        className="inline-flex size-5 shrink-0 items-center justify-center rounded-full align-middle text-ink-3 hover:bg-sunken hover:text-brand-ink print:hidden"
      >
        <CircleHelpIcon className="size-3.5" aria-hidden />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="center"
          sideOffset={6}
          collisionPadding={16}
          className="z-50 w-[min(18rem,calc(100vw-2rem))] rounded-xl bg-ink px-4 py-3 text-left text-[13px] leading-relaxed text-white shadow-lg"
        >
          <p className="font-semibold">{g.term}</p>
          <p className="mt-1 text-white/85">{g.text}</p>
          <Popover.Arrow className="fill-ink" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
