import { connection } from "next/server";
import { Suspense } from "react";

import { LoginForm } from "@/components/login/login-form";

export const metadata = { title: "Sign in · Ledgerwise" };

// Reads the environment per request: a build-time prerender would bake in the build machine's env.
async function SignIn() {
  await connection();
  // Demo buttons only when the deployment opts in; the seeded password is public demo data.
  const demoPassword = process.env.DEMO_PASSWORD ?? null;
  // Set on the deployed demo, where a cron job restores the golden data (deploy/cron/ledgerwise).
  const resetHours = process.env.DEMO_RESET_EVERY_HOURS ?? null;
  return (
    <>
      <LoginForm demoPassword={demoPassword} />
      {resetHours && (
        <p className="mt-6 text-xs text-ink-3">
          Demo data resets every {resetHours} hours, so approvals and changes you make here won&apos;t last.
        </p>
      )}
    </>
  );
}

/** 13 weeks in miniature: two dips below the cushion, then the fixes lift them. Decorative only. */
function Glimpse() {
  const weeks = [62, 70, 84, 80, 72, 22, 40, 34, 18, 26, 66, 52, 60];
  return (
    <svg viewBox="0 0 130 64" className="h-16 w-40" aria-hidden>
      <line x1="0" y1="34" x2="130" y2="34" stroke="currentColor" strokeOpacity="0.35" strokeDasharray="3 3" />
      {weeks.map((h, i) => (
        <rect key={i} x={i * 10 + 2} y={64 - h * 0.64} width="6" height={h * 0.64} rx="1.5"
          fill={64 - h * 0.64 > 34 ? "var(--color-risk)" : "var(--color-good)"} />
      ))}
    </svg>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-dvh md:grid-cols-[1fr_1.1fr]">
      <section className="flex flex-col justify-between bg-ink px-6 py-8 text-white md:px-14 md:py-14">
        <span className="text-[15px] font-semibold tracking-tight">Ledgerwise</span>
        <div className="my-10 max-w-md md:my-0">
          <Glimpse />
          <h1 className="mt-8 font-display text-[30px] leading-[1.15] font-medium tracking-[-0.01em] md:text-[44px]">
            Know when cash runs short, weeks before it does.
          </h1>
          <p className="mt-5 text-[16px] leading-relaxed text-white/75">
            Every figure comes from your own records and links back to them. Nothing is paid or sent until a person approves it.
          </p>
        </div>
        <p className="hidden text-xs text-white/50 md:block">Demo data: Ember &amp; Oak Coffee Roasters, a fictional business.</p>
      </section>
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h2 className="mb-7 font-display text-[26px] font-medium tracking-[-0.01em]">Sign in</h2>
          <Suspense>
            <SignIn />
          </Suspense>
        </div>
      </section>
    </div>
  );
}
