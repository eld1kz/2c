import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render as rtlRender, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TurnView } from "@/components/chat/turn-view";
import type { Turn } from "@/lib/chat/reducer";

function render(ui: React.ReactElement) {
  return rtlRender(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

const base: Turn = { id: "t", question: "Did you pay QuickShip?", status: "streaming", provisional: "", trail: [], answer: null, error: null, actionIds: [] };

afterEach(cleanup);

describe("TurnView", () => {
  it("marks streamed text as a draft", () => {
    render(<TurnView turn={{ ...base, provisional: "I've sent $9,999 to QuickShip." }} />);
    expect(screen.getByText(/Drafting/)).toBeTruthy();
    expect(screen.getByTestId("provisional").textContent).toContain("$9,999");
  });

  it("shows only done.message once final, with unverified citations marked", () => {
    const turn: Turn = {
      ...base,
      status: "done",
      provisional: "I've sent $9,999 to QuickShip.", // must never render once the turn is done
      answer: {
        message: "Nothing was paid. QS-2291 has **$465.00** outstanding [[invoice:7]]; see [this](https://evil.example).",
        citations: [{ ref: "invoice:7", valid: false, label: "invoice:7", reason: "not_seen" }],
        warnings: [],
      },
    };
    const { container } = render(<TurnView turn={turn} />);
    expect(container.textContent).not.toContain("9,999");
    expect(screen.queryByText(/Drafting/)).toBeNull();
    expect(screen.getByText("unverified")).toBeTruthy();
    expect(container.querySelector("a[href]")).toBeNull(); // no links from model output
    expect(container.textContent).toContain("this");
  });

  it("shows an error instead of the draft", () => {
    const { container } = render(<TurnView turn={{ ...base, status: "error", provisional: "I've sent $9,999", error: "The assistant is unavailable right now." }} />);
    expect(container.textContent).not.toContain("9,999");
    expect(screen.getByRole("alert").textContent).toContain("unavailable");
  });
});
