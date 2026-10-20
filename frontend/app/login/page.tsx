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

export default function LoginPage() {
  return (
    <div className="grid min-h-dvh md:grid-cols-[1fr_1.1fr]">
      <section className="flex flex-col justify-between bg-ink px-6 py-8 text-white md:px-14 md:py-14">
        <span className="text-[15px] font-semibold tracking-tight">Ledgerwise</span>
        <div className="my-10 max-w-md md:my-0">
          <h1 className="font-display text-[30px] leading-[1.15] font-medium tracking-[-0.01em] md:text-[44px]">
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
