"use client";

import { PlusIcon } from "lucide-react";

import { Money } from "@/components/money";
import { cn } from "@/lib/cn";

import { Character, HIRE_LOOK, LOOKS, Silhouette } from "./character";

type Person = { name: string; role: string; weekly_pay_cents?: number | null };

export const illustrationLabel = (p: { name: string; role: string }) => `Illustration of ${p.name.split(" ")[0]}, ${p.role.toLowerCase()}`;

const SIZE = { lg: 84, sm: 46 } as const;

/**
 * The team standing side by side on one floor line, like a small team photo. On a narrow screen the row
 * scrolls inside its own box. `onSelect` makes each person a button (Team page); `hire` adds the dashed
 * spot at the end, which previews the chosen role's character.
 */
export function Lineup({ people, size, onSelect, hire }: {
  people: Person[];
  size: keyof typeof SIZE;
  onSelect?: (name: string) => void;
  hire?: { role: string; onClick: () => void } | null;
}) {
  const w = SIZE[size];
  const lg = size === "lg";
  const slots = people.length + (hire ? 1 : 0);
  const preview = hire && hire.role.trim() ? hire.role.trim() : null; // any typed role becomes a character

  const figure = (node: React.ReactNode) => (
    <span className="block motion-safe:group-hover:animate-[lw-bob_1.4s_ease-in-out_infinite]">{node}</span>
  );

  return (
    <div className="-mx-1 overflow-x-auto px-1 pb-1" data-testid={`lineup-${size}`}>
      <div className="mx-auto grid w-max items-end" style={{ gridTemplateColumns: `repeat(${slots}, ${w + (lg ? 20 : 8)}px)` }}>
        {/* the shared floor (explicit columns below let the people stand on it in the same row) */}
        <div className="col-span-full row-start-1 h-0 self-end border-b-2 border-line-strong" aria-hidden />
        {people.map((p, i) => {
          const look = LOOKS[i % LOOKS.length];
          const art = figure(<Character look={look} role={p.role} label={illustrationLabel(p)} width={w} />);
          const caption = lg && (
            <span className="mt-2 block text-center leading-tight">
              <span className="block text-[13px] font-medium text-ink">{p.name.split(" ")[0]}</span>
              <span className="block text-xs text-ink-3">{p.role}</span>
              {p.weekly_pay_cents !== null && p.weekly_pay_cents !== undefined && (
                <span className="block text-xs text-ink-2"><Money cents={p.weekly_pay_cents} />/wk</span>
              )}
            </span>
          );
          return onSelect ? (
            <button key={p.name} type="button" onClick={() => onSelect(p.name)} style={{ gridColumn: i + 1 }}
              className="group row-span-2 row-start-1 grid grid-rows-subgrid justify-items-center rounded-xl pt-2 hover:bg-sunken/60">
              <span className="self-end">{art}</span>
              {caption}
            </button>
          ) : (
            <div key={p.name} style={{ gridColumn: i + 1 }} className="group row-span-2 row-start-1 grid grid-rows-subgrid justify-items-center">
              <span className="self-end">{art}</span>
              {caption}
            </div>
          );
        })}
        {hire && (
          <button type="button" onClick={hire.onClick} style={{ gridColumn: slots }}
            className="group row-span-2 row-start-1 grid grid-rows-subgrid justify-items-center rounded-xl pt-2 hover:bg-sunken/60">
            <span className={cn("self-end", preview && "opacity-80")}>
              {preview
                ? figure(<Character look={HIRE_LOOK} role={preview} label={`Preview: illustration of a new ${preview.toLowerCase()}`} width={w} />)
                : <Silhouette width={w} />}
            </span>
            <span className="mt-2 flex items-center gap-1 text-[13px] font-medium text-brand-ink">
              <PlusIcon className="size-3.5" aria-hidden /> Hire someone
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
