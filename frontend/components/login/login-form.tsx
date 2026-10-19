"use client";

import { useSearchParams } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { safeNext } from "@/lib/safe-next";

const DEMO_USERS = [
  { role: "Owner", email: "owner@emberoak.demo", can: "Approves payments and reminders" },
  { role: "Accountant", email: "accountant@emberoak.demo", can: "Reviews books, approves reminders" },
  { role: "Viewer", email: "viewer@emberoak.demo", can: "Read-only" },
];

const noop = () => () => {};

/** False in the server HTML and until React hydrates, then true: nothing can submit before the JS handler exists. */
const useHydrated = () => useSyncExternalStore(noop, () => true, () => false);

export function LoginForm({ demoPassword }: { demoPassword: string | null }) {
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = useHydrated();

  async function signIn(e: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: e, password: p }),
      });
      if (r.ok) {
        window.location.assign(next);
        return;
      }
      const body = await r.json().catch(() => ({}));
      if (r.status === 401) setError("That email and password don't match. Check them and try again.");
      else if (r.status === 429) setError("Too many failed attempts for this email. Wait 15 minutes, then try again.");
      else setError(body.detail ?? "Sign-in failed. Try again.");
    } catch {
      setError("The server can't be reached. Check your connection and try again.");
    }
    setBusy(false);
  }

  return (
    <div className="w-full max-w-sm">
      {/* method="post" and unnamed inputs: even a native submission never puts the email or password in the URL */}
      <form
        method="post"
        action="/login"
        onSubmit={(ev) => {
          ev.preventDefault();
          void signIn(email, password);
        }}
        className="space-y-4"
      >
        <label className="block">
          <span className="text-sm font-medium text-ink">Email</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            className="mt-1.5 h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-ink">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            className="mt-1.5 h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </label>
        {error && (
          <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !ready}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      {demoPassword && (
        <div className="mt-8">
          <p className="text-sm font-medium text-ink">Demo accounts</p>
          <p className="mt-0.5 text-sm text-ink-3">Each role sees what it&apos;s allowed to do.</p>
          <div className="mt-3 divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
            {DEMO_USERS.map((u) => (
              <button
                key={u.email}
                type="button"
                disabled={busy || !ready}
                onClick={() => void signIn(u.email, demoPassword)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-sunken disabled:opacity-50"
              >
                <span>
                  <span className="block text-sm font-medium text-ink">Sign in as {u.role.toLowerCase()}</span>
                  <span className="block text-xs text-ink-3">{u.can}</span>
                </span>
                <span className="text-xs text-ink-3">{u.email.split("@")[0]}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
