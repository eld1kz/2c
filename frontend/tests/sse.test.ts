import { describe, expect, it } from "vitest";

import { linkCitations, plainCitations } from "@/lib/chat/citations";
import type { ChatEvent } from "@/lib/chat/events";
import { createSseParser } from "@/lib/chat/sse";

function parse(chunks: string[]): ChatEvent[] {
  const out: ChatEvent[] = [];
  const feed = createSseParser((e) => out.push(e));
  chunks.forEach(feed);
  return out;
}

describe("SSE parser", () => {
  it("parses events split across chunks", () => {
    const events = parse(['event: text\ndata: {"del', 'ta": "Hi"}\n', "\nevent: done\ndata: ", '{"message":"ok","citations":[],"warnings":[],"action_ids":[],"iterations":1}\n\n']);
    expect(events.map((e) => e.event)).toEqual(["text", "done"]);
    expect(events[0].data).toEqual({ delta: "Hi" });
  });

  it("accepts CRLF line endings", () => {
    expect(parse(['event: reset\r\ndata: {"reason":"citation_check","problems":[]}\r\n\r\n'])).toHaveLength(1);
  });

  it("ignores unknown events and malformed data", () => {
    expect(parse(["event: ping\ndata: {}\n\n", "event: text\ndata: not json\n\n", ": comment\n\n"])).toEqual([]);
  });
});

describe("citations", () => {
  it("turns [[type:id]] into cite: links", () => {
    expect(linkCitations("Due $4,800.00 [[invoice:12]].")).toBe("Due $4,800.00 [invoice:12](cite:invoice:12).");
  });

  it("leaves malformed citations as text", () => {
    expect(linkCitations("[[not a ref]] [[invoice:]]")).toBe("[[not a ref]] [[invoice:]]");
  });

  it("keeps drafts readable", () => {
    expect(plainCitations("Week 6 [[forecast_week:6]]")).toBe("Week 6 [forecast_week:6]");
  });
});
