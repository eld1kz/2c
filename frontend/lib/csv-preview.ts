// First rows of a CSV for the upload preview. Display only: the server parses and validates the file
// itself (backend/app/ingestion/csv_parser.py); nothing here is trusted or sent.

export type CsvPreview = { header: string[]; rows: string[][]; totalRows: number };

export function previewCsv(text: string, maxRows = 10): CsvPreview {
  const records: string[][] = [];
  let field = "";
  let record: string[] = [];
  let quoted = false;
  const input = text.replace(/^﻿/, "");
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (quoted) {
      if (c === '"' && input[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      record.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && input[i + 1] === "\n") i++;
      record.push(field);
      if (record.some((f) => f.trim() !== "")) records.push(record);
      record = [];
      field = "";
    } else field += c;
  }
  record.push(field);
  if (record.some((f) => f.trim() !== "")) records.push(record);
  const [header = [], ...rows] = records;
  return { header, rows: rows.slice(0, maxRows), totalRows: rows.length };
}
