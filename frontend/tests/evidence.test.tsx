import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ToolTrail } from "@/components/chat/tool-trail";
import { fallbackLabel } from "@/components/evidence/evidence-chip";

afterEach(cleanup);

describe("fallbackLabel", () => {
  it.each([
    ["whatif:1", "What-if 1"],
    ["forecast_week:6", "Week 6"],
    ["financing:overdraft", "Financing option"],
    ["invoice:30", "invoice:30"],
  ])("%s → %s", (ref, label) => expect(fallbackLabel(ref)).toBe(label));
});

describe("ToolTrail", () => {
  it("shows a proposal once, not again as a tool step", () => {
    render(
      <ToolTrail
        working={false}
        items={[
          { kind: "tool", name: "draft_reminder", tier: "SUGGEST", ok: true },
          { kind: "action", action: { action_id: 2, tool: "send_reminder", status: "proposed" } },
          { kind: "tool", name: "send_reminder", tier: "EXECUTE", ok: true },
        ]}
      />,
    );
    expect(screen.getAllByText(/Proposed a reminder/)).toHaveLength(1);
    expect(screen.getByText("Drafted a reminder")).toBeTruthy();
  });
});
