"use client";

import { FileSpreadsheetIcon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useMe, useUpload } from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import { previewCsv, type CsvPreview } from "@/lib/csv-preview";

const MAX_BYTES = 2 * 1024 * 1024; // the server's limit (backend/app/ingestion/csv_parser.py)

function problem(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) return "Only owners and accountants can import statements; this attempt was logged.";
  if (error instanceof ApiError && error.status === 422) return `The file was rejected: ${error.message}. Nothing was imported.`;
  if (error instanceof ApiError) return error.message;
  return "The upload didn't finish. Check your connection and try again.";
}

export function UploadView() {
  const role = useMe().data?.user.role;
  const allowed = role === "owner" || role === "accountant";
  const upload = useUpload();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  async function choose(f: File | undefined) {
    upload.reset();
    setFile(null);
    setPreview(null);
    setError(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".csv")) return setError("Choose a .csv file exported from your bank.");
    if (f.size > MAX_BYTES) return setError("This file is over 2 MB. Export a shorter date range and try again.");
    const p = previewCsv(await f.text());
    if (p.header.length === 0) return setError("This file is empty.");
    setFile(f);
    setPreview(p);
  }

  const r = upload.data;
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold tracking-tight">Import a bank statement</h1>
      <p className="mt-1 text-sm text-ink-3">
        CSV up to 2 MB. Column names can vary; rows already imported are skipped. Each row is categorized by your rules first, then by AI, and anything
        uncertain goes to the review queue.
      </p>

      {!allowed && role && (
        <p className="mt-5 rounded-lg bg-sunken px-4 py-3 text-sm text-ink-2">Viewers can look at transactions but can&apos;t import statements.</p>
      )}

      {allowed && (
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void choose(e.dataTransfer.files[0]);
          }}
          className={cn(
            "mt-5 flex cursor-pointer flex-col items-center gap-2 rounded-[var(--radius-panel)] border-2 border-dashed px-6 py-10 text-center",
            dragging ? "border-brand bg-brand-soft" : "border-line-strong bg-surface hover:bg-sunken/40",
          )}
        >
          <UploadIcon className="size-6 text-ink-3" />
          <span className="text-sm font-medium text-ink">{file ? file.name : "Drop a CSV here, or choose a file"}</span>
          <span className="text-xs text-ink-3">Nothing is imported until you confirm.</span>
          <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => void choose(e.target.files?.[0])} />
        </label>
      )}

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-risk-soft px-3 py-2.5 text-sm text-risk-ink">
          {error}
        </p>
      )}

      {preview && file && !r && (
        <section className="mt-5" aria-labelledby="preview-title">
          <h2 id="preview-title" className="flex items-center gap-2 text-[15px] font-semibold">
            <FileSpreadsheetIcon className="size-4 text-ink-3" /> Preview: first {preview.rows.length} of {preview.totalRows} rows
          </h2>
          <div className="mt-2 overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="num w-full text-left text-sm">
              <thead className="border-b border-line bg-sunken/60 text-xs text-ink-3">
                <tr>
                  {preview.header.map((h, i) => (
                    <th key={i} className="px-3 py-2 font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, i) => (
                  <tr key={i} className="border-b border-line last:border-0">
                    {preview.header.map((_, j) => (
                      <td key={j} className="max-w-64 truncate px-3 py-2 whitespace-nowrap text-ink-2">
                        {row[j] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={() => upload.mutate(file)} disabled={upload.isPending}>
              {upload.isPending ? "Importing…" : `Import ${preview.totalRows} row${preview.totalRows === 1 ? "" : "s"}`}
            </Button>
            <Button variant="ghost" onClick={() => void choose(undefined)} disabled={upload.isPending}>
              Choose another file
            </Button>
          </div>
        </section>
      )}

      {upload.isError && (
        <p role="alert" className="mt-4 rounded-lg bg-risk-soft px-3 py-2.5 text-sm text-risk-ink">
          {problem(upload.error)}
        </p>
      )}

      {r && (
        <section role="status" className="mt-5 rounded-[var(--radius-panel)] border border-line bg-surface p-5">
          <h2 className="text-[15px] font-semibold text-good-ink">
            Imported {r.inserted} of {r.rows} rows
          </h2>
          <dl className="num mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {(
              [
                ["Already imported, skipped", r.skipped_duplicates],
                ["Categorized by your rules", r.by_rule],
                ["Categorized by AI", r.by_llm],
                ["Linked to invoices", r.linked],
              ] as const
            ).map(([label, n]) => (
              <div key={label}>
                <dt className="text-xs text-ink-3">{label}</dt>
                <dd className="text-lg font-semibold">{n}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-sm text-ink-2">
            {r.needs_review > 0 ? (
              <>
                <span className="font-medium text-attn-ink">{r.needs_review} need a category.</span>{" "}
                <Link href="/transactions?tab=review" className="font-medium text-brand-ink underline-offset-2 hover:underline">
                  Open the review queue
                </Link>
              </>
            ) : (
              "Nothing needs review. The forecast and insights now include these rows."
            )}
          </p>
          <Button variant="secondary" className="mt-4" onClick={() => void choose(undefined)}>
            Import another file
          </Button>
        </section>
      )}
    </div>
  );
}
