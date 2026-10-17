"use client";

import { TriangleAlertIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { EvidenceChip } from "@/components/evidence/evidence-chip";
import { canOpen } from "@/components/evidence/evidence-provider";
import { useRecordLabels } from "@/lib/api/hooks";
import { CITE_SCHEME, linkCitations } from "@/lib/chat/citations";
import type { Citation } from "@/lib/chat/events";

/** The checked, final answer. Citations become evidence chips; any other link or image is not rendered. */
export function Answer({ message, citations, warnings }: { message: string; citations: Citation[]; warnings: string[] }) {
  const byRef = new Map(citations.map((c) => [c.ref, c]));
  const stored = citations.filter((c) => c.valid && c.label === c.ref && canOpen(c.ref) && !c.ref.startsWith("forecast_week:")).map((c) => c.ref);
  const { data: rows } = useRecordLabels(stored.slice(0, 50));
  const names = new Map((rows ?? []).map((r) => [r.ref, r.label]));
  return (
    <div>
      <div className="answer">
        <ReactMarkdown
          skipHtml
          urlTransform={(url) => (url.startsWith(CITE_SCHEME) ? url : "")}
          components={{
            a: ({ href, children }) => {
              if (!href?.startsWith(CITE_SCHEME)) return <span>{children}</span>;
              const ref = href.slice(CITE_SCHEME.length);
              const cite = byRef.get(ref);
              const label = cite && cite.label !== ref ? cite.label : (names.get(ref) ?? null);
              return <EvidenceChip evidence={{ ref, label }} valid={cite?.valid ?? false} className="mx-0.5" />;
            },
            img: () => null,
          }}
        >
          {linkCitations(message)}
        </ReactMarkdown>
      </div>
      {warnings.length > 0 && (
        <div className="mt-3 flex gap-2 rounded-lg bg-attn-soft px-3 py-2 text-xs text-attn-ink">
          <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0" />
          <ul className="space-y-0.5">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
