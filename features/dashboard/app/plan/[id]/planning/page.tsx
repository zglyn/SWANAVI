"use client";

import type { SwanView } from "@contracts/api";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { SwanShell, phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { nightsBetween } from "@/lib/format";
import { matchCity } from "@/lib/places";

const STEP_MS = 900;

function stepsFor(view: SwanView | null): string[] {
  if (!view) return ["Reading your profile…", "Searching flights…", "Finding hotels…", "Building your days…"];
  const request = view.request;
  const destination = matchCity(request.destination);
  const from = request.origin.airport_codes[0] ?? "home";
  const to = destination?.airports[0] ?? request.destination.split(",")[0];
  const picks = view.package
    ? view.package.itinerary.days.reduce((sum, day) => sum + day.stops.filter((stop) => stop.kind === "attraction" || stop.kind === "merchant").length, 0)
    : 6;
  const days = Math.max(1, nightsBetween(request.start_date, request.end_date) + 1);
  const lines = ["Reading your profile…", `Searching flights ${from} → ${to}…`];
  if (view.phase === "waiting_attractions") {
    lines.push(`Collecting things to do in ${request.destination.split(",")[0]}…`);
    return lines;
  }
  lines.push(`Finding hotels near your ${picks} picks…`);
  if (view.phase === "waiting_flights" || view.phase === "waiting_hotels") return lines;
  for (let day = 1; day <= Math.min(days, 4); day += 1) lines.push(`Building day ${day}…`);
  if (days > 4) lines.push(`Building day ${days}…`);
  lines.push("Checking the budget…");
  return lines;
}

function Planning() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [view, setView] = useState<SwanView | null>(null);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.getSwan(params.id).then(setView).catch((err: Error) => setError(err.message));
  }, [client, params.id]);

  const steps = stepsFor(view);
  const next = search.get("next") || (view ? phasePath(params.id, view.phase) : null);

  useEffect(() => {
    if (!view) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const pace = reduced ? STEP_MS / 3 : STEP_MS;
    if (done >= steps.length) {
      if (next) router.replace(next);
      return;
    }
    const timer = window.setTimeout(() => setDone((value) => value + 1), pace);
    return () => window.clearTimeout(timer);
  }, [view, done, steps.length, next, router]);

  if (error) {
    return <SwanShell><p>{error}</p></SwanShell>;
  }

  return (
    <SwanShell>
      <section aria-live="polite" aria-busy={done < steps.length}>
        <p className="swan-eyebrow">Swanavi is planning</p>
        <h1 className="mt-2 text-4xl sm:text-5xl">{view?.request.destination ?? "Your trip"}</h1>
        <ol className="mt-8 space-y-3">
          {steps.map((line, index) => {
            const state = index < done ? "done" : index === done ? "active" : "todo";
            return (
              <li key={line} className={`flex items-center gap-3 text-lg ${state === "todo" ? "swan-muted opacity-50" : ""}`}>
                <span className="flex h-6 w-6 shrink-0 items-center justify-center" aria-hidden="true">
                  {state === "done" ? "✓" : state === "active" ? <span className="swan-dot" /> : <span className="h-2 w-2 rounded-full" style={{ background: "var(--swan-line)" }} />}
                </span>
                <span>{state === "done" ? line.replace(/…$/, "") : line}</span>
              </li>
            );
          })}
        </ol>
        <div className="swan-progress mt-8" aria-hidden="true"><span style={{ width: `${Math.min(100, (done / steps.length) * 100)}%` }} /></div>
      </section>
    </SwanShell>
  );
}

export default function PlanningPage() {
  return <Suspense fallback={<SwanShell><p>Planning…</p></SwanShell>}><Planning /></Suspense>;
}
