"use client";

import { FlaskConicalIcon, LandmarkIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { Schemas } from "@/lib/api/client";
import { useForecast, useMe } from "@/lib/api/hooks";
import { collect, whatIfHref } from "@/lib/scenarios";

const MAX_LINKS = 2;

/** "What if Harbor Lane Café pays INV-1042?" for each receivable the forecast counts as at risk.
 *  Hidden for viewers: simulations need an owner or accountant. */
export function WhatIfLinks({ forecast }: { forecast?: Schemas["ForecastOut"] }) {
  const me = useMe();
  const fetched = useForecast();
  const fc = forecast ?? fetched.data;
  if (!fc?.gap || !me.data || me.data.user.role === "viewer") return null;
  return (
    <>
      {fc.at_risk_receivables.slice(0, MAX_LINKS).map((r) => (
        <Button key={r.invoice.ref} asChild variant="secondary" size="sm">
          <Link href={whatIfHref([collect(r.invoice.ref)])}>
            <FlaskConicalIcon />
            What if {r.counterparty_name} pays {r.number}?
          </Link>
        </Button>
      ))}
    </>
  );
}

/** Opens the financing comparison for today's gap. Hidden for viewers, like the what-if links. */
export function CompareFinancingLink() {
  const me = useMe();
  if (!me.data || me.data.user.role === "viewer") return null;
  return (
    <Button asChild variant="secondary" size="sm">
      <Link href={whatIfHref([], "financing")}>
        <LandmarkIcon />
        Compare financing
      </Link>
    </Button>
  );
}
