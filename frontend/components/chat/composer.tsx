"use client";

import { ArrowUpIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

const MAX = 4000;

export function Composer({ initial, disabled, onSend }: { initial: string; disabled: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState(initial);
  const trimmed = text.trim();
  const submit = () => {
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface p-2 shadow-[0_6px_24px_rgba(24,33,58,0.08)] focus-within:border-brand"
    >
      <label htmlFor="chat-input" className="sr-only">
        Ask the CFO
      </label>
      <textarea
        id="chat-input"
        rows={1}
        maxLength={MAX}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ask about cash, customers, suppliers or what to do next"
        className="field-sizing-content max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-ink-3"
      />
      <Button type="submit" size="icon" disabled={disabled || !trimmed} aria-label="Send" className="rounded-xl">
        <ArrowUpIcon />
      </Button>
    </form>
  );
}
