import { describe, expect, it } from "vitest";

import { previewCsv } from "@/lib/csv-preview";

describe("previewCsv", () => {
  it("reads the header and the first rows", () => {
    const p = previewCsv("Date,Description,Amount\n2026-09-01,POS SETTLEMENT,412.50\n2026-09-02,RENT,-3200\n", 1);
    expect(p.header).toEqual(["Date", "Description", "Amount"]);
    expect(p.rows).toEqual([["2026-09-01", "POS SETTLEMENT", "412.50"]]);
    expect(p.totalRows).toBe(2);
  });

  it("handles quotes, embedded commas and newlines, CRLF and a BOM", () => {
    const p = previewCsv('﻿a,b\r\n"x, ""y""","line\nbreak"\r\n');
    expect(p.header).toEqual(["a", "b"]);
    expect(p.rows).toEqual([['x, "y"', "line\nbreak"]]);
  });

  it("skips blank lines", () => {
    expect(previewCsv("a\n\n1\n\n").totalRows).toBe(1);
  });
});
