import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { GLOSSARY } from "@/lib/glossary";

// Every "What is this?" term the UI uses must exist in the glossary, every entry must be used, and each
// definition is one or two plain sentences.
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
  });
}

const sources = [...files("components"), ...files("app"), join("lib", "statements.ts")]
  .map((p) => readFileSync(p, "utf8"));
// <Help term="x" />, <Panel term="x">, { term: "x" }, and the financing option → term map
const used = new Set(sources.flatMap((s) => [...s.matchAll(/term(?:=|: )"([a-z_]+)"/g)].map((m) => m[1])));
const optionMap = sources.join("\n").match(/const OPTION_TERM[^}]*}/)?.[0] ?? "";
for (const m of optionMap.matchAll(/: "([a-z_]+)"/g)) used.add(m[1]);

describe("glossary", () => {
  it("has about 20 terms and every term used in the UI exists", () => {
    expect(Object.keys(GLOSSARY).length).toBeGreaterThanOrEqual(20);
    expect(used.size).toBeGreaterThanOrEqual(20);
    expect([...used].filter((t) => !(t in GLOSSARY))).toEqual([]);
  });

  it("uses every entry somewhere", () => {
    expect(Object.keys(GLOSSARY).filter((t) => !used.has(t))).toEqual([]);
  });

  it("explains each term in one or two sentences", () => {
    for (const { term, text } of Object.values(GLOSSARY)) {
      const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean);
      expect(sentences.length, term).toBeGreaterThanOrEqual(1);
      expect(sentences.length, term).toBeLessThanOrEqual(2);
      expect(text.endsWith("."), term).toBe(true);
    }
  });
});
