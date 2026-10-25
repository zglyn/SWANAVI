"use client";

import type { Autonomy, TimeOfDayWindow, TripRequest, UserProfile } from "@contracts/api";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { SwanShell, planningPath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { formatDateRange, formatMoney, nightsBetween } from "@/lib/format";
import { DESTINATIONS, lookupPlace, matchCity } from "@/lib/places";

const WINDOWS: TimeOfDayWindow[] = ["early_morning", "morning", "afternoon", "evening", "red_eye", "any"];
const WINDOW_LABEL: Record<TimeOfDayWindow, string> = {
  early_morning: "Early morning",
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
  red_eye: "Red-eye",
  any: "Any time",
};
const DRAFT = "swan.trip-draft";
const STEPS = 6;

function Planner() {
  const router = useRouter();
  const params = useSearchParams();
  const step = Math.min(STEPS, Math.max(1, Number(params.get("step") || "1")));
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [draft, setDraft] = useState<TripRequest | null>(null);
  const [query, setQuery] = useState("Kyoto");
  const [originQuery, setOriginQuery] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const saved = sessionStorage.getItem(DRAFT);
    client.getProfile().then((found) => {
      setProfile(found);
      if (saved) {
        setDraft(JSON.parse(saved) as TripRequest);
        return;
      }
      const autonomy = found?.autonomy ?? { attractions: "swan_decides", hotels: "swan_decides", flights: "swan_decides" };
      setDraft({
        destination: "Kyoto, Japan",
        origin: { from_home: true, place: null, airport_codes: found?.home.airport_codes ?? [] },
        start_date: "2026-11-14",
        end_date: "2026-11-16",
        outbound_window: "morning",
        return_window: "evening",
        travellers: 1,
        budget: "2500",
        autonomy,
        notes: null,
      });
    }).catch(() => setProfile(null));
  }, [client]);

  useEffect(() => {
    if (draft) sessionStorage.setItem(DRAFT, JSON.stringify(draft));
  }, [draft]);

  function go(next: number) {
    router.push(`/plan/new?step=${next}`);
  }

  async function confirm() {
    if (!draft || busy) return;
    setBusy(true);
    try {
      const created = await client.requestTrip(draft);
      sessionStorage.removeItem(DRAFT);
      router.push(planningPath(created.plan_id, created.phase));
    } finally {
      setBusy(false);
    }
  }

  if (!draft) return <SwanShell><p>Loading your profile…</p></SwanShell>;
  const windows = WINDOWS.filter((item) => item !== "red_eye" || !profile?.flights.avoid_red_eye);
  const matches = DESTINATIONS.filter((city) => city.label.toLowerCase().includes(query.toLowerCase()));
  const originLabel = draft.origin.from_home
    ? `Home · ${(profile?.home.airport_codes ?? draft.origin.airport_codes).join(" · ")}`
    : `${draft.origin.place ?? ""} · ${draft.origin.airport_codes.join(" · ")}`;
  const nights = nightsBetween(draft.start_date, draft.end_date);

  const summary = (
    <div>
      <p className="swan-eyebrow">Your trip so far</p>
      <dl className="mt-3 space-y-3 text-sm">
        <Row label="Where" value={draft.destination} />
        <Row label="From" value={originLabel} />
        <Row label="When" value={`${formatDateRange(draft.start_date, draft.end_date)} · ${nights} night${nights === 1 ? "" : "s"}`} />
        <Row label="Who" value={`${draft.travellers} traveller${draft.travellers === 1 ? "" : "s"}`} />
        <Row label="Fly" value={`${WINDOW_LABEL[draft.outbound_window]} out · ${WINDOW_LABEL[draft.return_window]} back`} />
        <Row label="Budget" value={draft.budget ? formatMoney(draft.budget, "USD") : "Open"} />
      </dl>
      <p className="swan-muted mt-4 text-sm">The map appears once Swanavi has a plan to show.</p>
    </div>
  );

  return (
    <SwanShell step={step} steps={STEPS} aside={summary}>
      {step === 1 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">Where to?</h1>
          <input
            className="swan-line mt-6 w-full rounded-2xl border px-4 py-3 text-lg"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Destination"
            placeholder="City"
          />
          <ul className="mt-4 flex flex-wrap gap-2" aria-label="Suggestions">
            {matches.map((city) => {
              const value = ["London", "Paris", "New York", "Los Angeles"].includes(city.label) ? city.label : `${city.label}, Japan`;
              return (
                <li key={city.label}>
                  <button type="button" className="swan-filter" aria-pressed={draft.destination === value} onClick={() => { setDraft({ ...draft, destination: value }); setQuery(city.label); }}>
                    {city.label}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="swan-muted mt-4">Going to {draft.destination}</p>
        </section>
      )}
      {step === 2 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">From where?</h1>
          <div className="swan-seg mt-6" role="radiogroup" aria-label="Origin">
            <button type="button" role="radio" aria-checked={draft.origin.from_home} onClick={() => setDraft({ ...draft, origin: { from_home: true, place: null, airport_codes: profile?.home.airport_codes ?? [] } })}>
              From home
            </button>
            <button type="button" role="radio" aria-checked={!draft.origin.from_home} onClick={() => setDraft({ ...draft, origin: { from_home: false, place: draft.origin.place, airport_codes: draft.origin.from_home ? [] : draft.origin.airport_codes } })}>
              Somewhere else
            </button>
          </div>
          {draft.origin.from_home ? (
            <p className="swan-muted mt-4">Flying from {(profile?.home.airport_codes ?? []).join(", ") || "your home airports"}.</p>
          ) : (
            <label className="mt-4 block">
              <span className="font-medium">City or address</span>
              <input
                className="swan-line mt-2 w-full rounded-2xl border px-4 py-3"
                aria-label="Other origin"
                value={originQuery}
                onChange={(event) => setOriginQuery(event.target.value)}
                onBlur={async () => {
                  const hit = await lookupPlace(originQuery);
                  if (!hit) return;
                  setDraft({ ...draft, origin: { from_home: false, place: hit.label, airport_codes: hit.airports } });
                }}
              />
              {draft.origin.place ? <p className="swan-muted mt-2 text-sm">{draft.origin.place} · {draft.origin.airport_codes.join(" · ")}</p> : null}
            </label>
          )}
        </section>
      )}
      {step === 3 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">When?</h1>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="font-medium">Arrive</span>
              <input type="date" className="swan-line mt-2 w-full rounded-2xl border px-4 py-3" value={draft.start_date} onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} />
            </label>
            <label className="block">
              <span className="font-medium">Leave</span>
              <input type="date" className="swan-line mt-2 w-full rounded-2xl border px-4 py-3" value={draft.end_date} onChange={(event) => setDraft({ ...draft, end_date: event.target.value })} />
            </label>
          </div>
          <label className="mt-3 block sm:max-w-[50%]">
            <span className="font-medium">Travellers</span>
            <input type="number" min={1} className="swan-line mt-2 w-full rounded-2xl border px-4 py-3" value={draft.travellers} onChange={(event) => setDraft({ ...draft, travellers: Math.max(1, Number(event.target.value)) })} />
          </label>
        </section>
      )}
      {step === 4 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">What time do you want to fly?</h1>
          <p className="mt-6 font-medium">Outbound</p>
          <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Outbound window">
            {windows.map((item) => (
              <button key={item} type="button" role="radio" className="swan-filter" aria-checked={draft.outbound_window === item} onClick={() => setDraft({ ...draft, outbound_window: item })}>{WINDOW_LABEL[item]}</button>
            ))}
          </div>
          <p className="mt-5 font-medium">Return</p>
          <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Return window">
            {windows.map((item) => (
              <button key={item} type="button" role="radio" className="swan-filter" aria-checked={draft.return_window === item} onClick={() => setDraft({ ...draft, return_window: item })}>{WINDOW_LABEL[item]}</button>
            ))}
          </div>
        </section>
      )}
      {step === 5 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">How much should Swanavi handle?</h1>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <div key={key} className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <p className="font-medium capitalize">{key}</p>
              <div className="swan-seg" role="radiogroup" aria-label={key}>
                {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                  <button key={item} type="button" role="radio" aria-checked={draft.autonomy[key] === item} onClick={() => setDraft({ ...draft, autonomy: { ...draft.autonomy, [key]: item } })}>
                    {item === "swan_decides" ? "Swanavi decides" : "I choose"}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <label className="mt-6 block sm:max-w-[50%]">
            <span className="font-medium">Budget for the whole trip</span>
            <input inputMode="decimal" className="swan-line mt-2 w-full rounded-2xl border px-4 py-3" value={draft.budget ?? ""} onChange={(event) => setDraft({ ...draft, budget: event.target.value })} />
          </label>
        </section>
      )}
      {step === 6 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">Ready to plan?</h1>
          <p className="mt-4 text-xl font-semibold">{draft.destination}</p>
          <p className="swan-muted">{formatDateRange(draft.start_date, draft.end_date)} · {draft.travellers} traveller{draft.travellers === 1 ? "" : "s"}</p>
          <p className="swan-muted mt-2">Fly {WINDOW_LABEL[draft.outbound_window].toLowerCase()} out, {WINDOW_LABEL[draft.return_window].toLowerCase()} back. From {originLabel}.</p>
          <button type="button" className="swan-btn mt-6" onClick={confirm} disabled={busy}>{busy ? "Starting…" : "Plan it"}</button>
        </section>
      )}
      <div className="mt-8 flex gap-3">
        {step > 1 && <button type="button" className="swan-btn-ghost" onClick={() => go(step - 1)}>Back</button>}
        {step < STEPS && <button type="button" className="swan-btn" onClick={() => go(step + 1)}>Continue</button>}
      </div>
    </SwanShell>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="swan-muted shrink-0">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

export default function PlanNewPage() {
  return <Suspense fallback={<SwanShell><p>Loading…</p></SwanShell>}><Planner /></Suspense>;
}
