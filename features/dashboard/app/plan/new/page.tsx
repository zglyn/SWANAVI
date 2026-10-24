"use client";

import type { Autonomy, TimeOfDayWindow, TripRequest, UserProfile } from "@contracts/api";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { TripMap, type MapStop } from "@/components/map3d/TripMap";
import { SwanShell, phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { DESTINATIONS, lookupPlace, matchCity } from "@/lib/places";

const WINDOWS: TimeOfDayWindow[] = ["early_morning", "morning", "afternoon", "evening", "red_eye", "any"];
const DRAFT = "swan.trip-draft";

function Planner() {
  const router = useRouter();
  const params = useSearchParams();
  const step = Number(params.get("step") || "1");
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [draft, setDraft] = useState<TripRequest | null>(null);
  const [query, setQuery] = useState("Kyoto");

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
    if (!draft) return;
    const created = await client.requestTrip(draft);
    sessionStorage.removeItem(DRAFT);
    router.push(phasePath(created.plan_id, created.phase));
  }

  if (!draft) return <SwanShell><p>Loading your profile…</p></SwanShell>;
  const windows = WINDOWS.filter((item) => item !== "red_eye" || !profile?.flights.avoid_red_eye);
  const destination = matchCity(draft.destination);
  const originHit = draft.origin.from_home ? null : (draft.origin.place ? matchCity(draft.origin.place) : null);
  const originStop: MapStop | null = draft.origin.from_home && profile
    ? { id: "home", lat: profile.home.location.lat, lng: profile.home.location.lng, label: "Home", kind: "stop" }
    : originHit
      ? { id: "origin", lat: originHit.lat, lng: originHit.lng, label: originHit.label, kind: "stop" }
      : null;
  const destinationStop: MapStop | null = destination
    ? { id: "destination", lat: destination.lat, lng: destination.lng, label: destination.label, kind: "stop" }
    : null;
  const stops = [originStop, destinationStop].filter((stop): stop is MapStop => stop !== null);
  const arcs = originStop && destinationStop
    ? [{ from: [originStop.lng, originStop.lat] as [number, number], to: [destinationStop.lng, destinationStop.lat] as [number, number] }]
    : [];

  return (
    <SwanShell
      step={step}
      steps={6}
      map={<TripMap stops={stops} arcs={arcs} focus={Math.max(stops.length - 1, 0)} dayLabel={draft.destination} showToggle={false} />}
    >
      {step === 1 && (
        <section>
          <h1 className="text-5xl">Where to?</h1>
          <input className="swan-line mt-6 w-full rounded-2xl border px-3 py-3 text-lg" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Destination" />
          <ul className="mt-4 space-y-2">
            {DESTINATIONS.filter((city) => city.label.toLowerCase().includes(query.toLowerCase())).map((city) => (
              <li key={city.label}>
                <button type="button" className="swan-chip" onClick={() => { setDraft({ ...draft, destination: ["London", "Paris", "New York", "Los Angeles"].includes(city.label) ? city.label : `${city.label}, Japan` }); setQuery(city.label); }}>{city.label}</button>
              </li>
            ))}
          </ul>
          <p className="swan-muted mt-4">Going to {draft.destination}</p>
        </section>
      )}
      {step === 2 && (
        <section>
          <h1 className="text-5xl">From where?</h1>
          <button type="button" className="swan-chip mt-6" aria-pressed={draft.origin.from_home} onClick={() => setDraft({ ...draft, origin: { from_home: true, place: null, airport_codes: profile?.home.airport_codes ?? [] } })}>
            From home {profile?.home.airport_codes.join(" · ")}
          </button>
          <label className="mt-4 block">Somewhere else
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" aria-label="Other origin" onBlur={async (event) => {
              const hit = await lookupPlace(event.target.value);
              if (!hit) return;
              setDraft({ ...draft, origin: { from_home: false, place: hit.label, airport_codes: hit.airports } });
            }} />
          </label>
        </section>
      )}
      {step === 3 && (
        <section>
          <h1 className="text-5xl">When?</h1>
          <label className="mt-6 block">Arrive
            <input type="date" className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={draft.start_date} onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} />
          </label>
          <label className="mt-3 block">Leave
            <input type="date" className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={draft.end_date} onChange={(event) => setDraft({ ...draft, end_date: event.target.value })} />
          </label>
          <label className="mt-3 block">Travellers
            <input type="number" min={1} className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={draft.travellers} onChange={(event) => setDraft({ ...draft, travellers: Number(event.target.value) })} />
          </label>
        </section>
      )}
      {step === 4 && (
        <section>
          <h1 className="text-5xl">What time do you want to fly?</h1>
          <p className="mt-6 font-medium">Outbound</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {windows.map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={draft.outbound_window === item} onClick={() => setDraft({ ...draft, outbound_window: item })}>{item.replace("_", " ")}</button>
            ))}
          </div>
          <p className="mt-4 font-medium">Return</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {windows.map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={draft.return_window === item} onClick={() => setDraft({ ...draft, return_window: item })}>{item.replace("_", " ")}</button>
            ))}
          </div>
        </section>
      )}
      {step === 5 && (
        <section>
          <h1 className="text-5xl">How much should Swan handle?</h1>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <div key={key} className="mt-4">
              <p className="capitalize">{key}</p>
              <div className="mt-2 flex gap-2">
                {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                  <button key={item} type="button" className="swan-chip" aria-pressed={draft.autonomy[key] === item} onClick={() => setDraft({ ...draft, autonomy: { ...draft.autonomy, [key]: item } })}>
                    {item === "swan_decides" ? "Swan decides" : "I choose"}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <label className="mt-4 block">Budget
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={draft.budget ?? ""} onChange={(event) => setDraft({ ...draft, budget: event.target.value })} />
          </label>
        </section>
      )}
      {step === 6 && (
        <section>
          <h1 className="text-5xl">Confirm</h1>
          <p className="mt-4 text-lg">{draft.destination}</p>
          <p className="swan-muted">{draft.start_date} to {draft.end_date} · {draft.travellers} traveller{draft.travellers === 1 ? "" : "s"}</p>
          <p className="swan-muted mt-2">Fly {draft.outbound_window.replace("_", " ")} out, {draft.return_window.replace("_", " ")} back.</p>
          <button type="button" className="swan-btn mt-6" onClick={confirm}>Plan it</button>
        </section>
      )}
      <div className="mt-8 flex gap-3">
        {step > 1 && <button type="button" className="swan-btn-ghost" onClick={() => go(step - 1)}>Back</button>}
        {step < 6 && <button type="button" className="swan-btn" onClick={() => go(step + 1)}>Next</button>}
      </div>
    </SwanShell>
  );
}

export default function PlanNewPage() {
  return <Suspense fallback={<SwanShell><p>Loading…</p></SwanShell>}><Planner /></Suspense>;
}
