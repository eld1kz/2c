import { InfoIcon } from "lucide-react";

/** The fixed label on every paperwork page (and every printed page). Text comes from the API. */
export function Disclaimer({ disclaimer, basis }: { disclaimer: string; basis: string }) {
  return (
    <div role="note" className="flex gap-2 rounded-lg bg-sunken px-3 py-2.5 text-sm text-ink-2 print:bg-transparent print:px-0">
      <InfoIcon className="mt-0.5 size-4 shrink-0" />
      <p>
        <span className="font-medium text-ink" data-testid="disclaimer">
          {disclaimer}
        </span>{" "}
        {basis}
      </p>
    </div>
  );
}
