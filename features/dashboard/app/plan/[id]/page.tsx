"use client";

import type { InspectorEvent, Itinerary, Quote, Stop } from "@contracts/api";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Logo } from "@/components/Logo";
import { StopMap } from "@/components/plan/StopMap";
import { ToolProgress } from "@/components/plan/ToolProgress";
import { getClient } from "@/lib/client";

export default function ItineraryPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [events, setEvents] = useState<InspectorEvent[]>([]);
  const [plan, setPlan] = useState<Itinerary | null>(null);
  const [day, setDay] = useState(0);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    const stop = client.subscribe((event) => {
      setEvents((prev) => (prev.some((item) => item.id === event.id) ? prev : [...prev, event]));
      if (event.type === "plan.failed") setError(String(event.data.error ?? event.message));
    }, (status) => setDown(status === "down"));
    client.getPlan(params.id).then((view) => {
      if (view.status === "candidates_ready") router.replace(`/plan/${params.id}/pick`);
      if (view.itinerary) setPlan(view.itinerary);
      if (view.error) setError(view.error);
    }).catch(() => setError("The gateway is not responding."));
    return stop;
  }, [client, params.id, router]);

  useEffect(() => {
    const ready = [...events].reverse().find((event) => event.type === "plan.ready");
    const itinerary = ready?.data.itinerary as Itinerary | undefined;
    if (itinerary) setPlan(itinerary);
  }, [events]);

  const current = plan?.days[day];

  async function revise(actions: { stop_id: string; action: "accept" | "remove" | "swap" }[], note: string | null) {
    if (!plan) return;
    await client.revisePlan(params.id, { actions, feedback: note });
    const view = await client.getPlan(params.id);
    if (view.itinerary) setPlan(view.itinerary);
  }

  function book() {
    if (!plan) return;
    const quotes = plan.days.flatMap((item) => item.stops).filter((stop) => stop.quote && stop.status === "accepted").map((stop) => stop.quote as Quote);
    if (quotes.length === 0) {
      setError("Accept a stop with a price before booking.");
      return;
    }
    sessionStorage.setItem("roam.booking", JSON.stringify(quotes));
    router.push("/dashboard?book=1");
  }

  return (
    <main className="mx-auto max-w-6xl overflow-x-hidden px-4 py-6 sm:px-6">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/"><Logo /></Link>
        <span className="text-xs text-ink-3">{down ? "Reconnecting" : client.mode}</span>
      </header>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-serif text-4xl">Your days in Kyoto</h1>
        <Link href={`/plan/${params.id}/pick`} className="text-sm text-indigo">Change picks</Link>
      </div>
      {error && <p className="mt-3 rounded-xl bg-torii-soft px-3 py-2 text-sm text-torii">{error} <button type="button" className="underline" onClick={() => location.reload()}>Try again</button></p>}
      {!plan && <div className="mt-4"><ToolProgress events={events} error={events.some((event) => event.type === "plan.invalid") ? "Re-checking plan…" : null} /></div>}
      {plan && current && (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            {plan.days.map((item, index) => (
              <button key={item.date} type="button" onClick={() => setDay(index)} className={`rounded-full px-3 py-1 text-sm ${index === day ? "bg-ink text-paper" : "bg-paper-2"}`}>{item.date}</button>
            ))}
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <ol className="space-y-3">
              {current.stops.map((stop) => {
                const leg = current.legs.find((item) => item.to_stop_id === stop.id);
                return (
                  <li key={stop.id} className="rounded-2xl border border-line bg-card p-3">
                    {leg && <p className="mb-2 text-xs text-ink-3">{leg.mode} · {leg.minutes} min · {leg.distance_km} km {leg.source === "estimate" ? "· estimated" : ""}</p>}
                    <div className="flex gap-3">
                      {stop.attraction?.image_url && <img src={stop.attraction.image_url} alt="" className="h-16 w-16 rounded-xl object-cover" />}
                      <div>
                        <div className="font-medium">{stop.title} {stop.required && <span className="ml-2 rounded-full bg-torii-soft px-2 py-0.5 text-xs text-torii">Your pick</span>}</div>
                        <p className="text-xs text-ink-3">{stop.start.slice(11, 16)}–{stop.end.slice(11, 16)} {stop.attraction?.free ? "· Free" : ""} {stop.quote ? `· ${stop.quote.amount} ${stop.quote.currency}` : ""}</p>
                        {stop.quote?.viator_price && <p className="text-xs text-ink-3"><s>{stop.quote.viator_price}</s> {stop.quote.merchant_verified ? "· Verified" : ""}</p>}
                      </div>
                    </div>
                    <div className="mt-2 flex gap-2 text-xs">
                      <button type="button" onClick={() => revise([{ stop_id: stop.id, action: "accept" }], null)} className="rounded-full bg-paper-2 px-2 py-1">Accept</button>
                      <button type="button" onClick={() => revise([{ stop_id: stop.id, action: "swap" }], null)} className="rounded-full bg-paper-2 px-2 py-1">Swap</button>
                      {!stop.required && <button type="button" onClick={() => revise([{ stop_id: stop.id, action: "remove" }], null)} className="rounded-full bg-paper-2 px-2 py-1">Remove</button>}
                    </div>
                  </li>
                );
              })}
            </ol>
            <div>
              <StopMap points={current.stops.map((stop) => ({
                id: stop.id, lat: stop.location.lat, lng: stop.location.lng, label: stop.title,
                color: stop.kind === "arrival" || stop.kind === "departure" ? "#2f4b9a" : stop.kind === "lodging" ? "#b7791f" : "#c8371d",
              }))} />
              <p className="mt-3 text-sm">{plan.transport_summary}</p>
              {plan.warnings.map((warning) => <p key={warning} className="mt-1 text-sm text-amber">{warning}</p>)}
            </div>
          </div>
          <footer className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <span className="text-sm">Bookable {plan.bookable_total} RLUSD</span>
            <input value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Anything to change?" className="min-w-0 flex-1 rounded-xl border border-line px-3 py-2 text-sm" />
            <button type="button" onClick={() => revise([], feedback || null)} className="rounded-full bg-paper-2 px-4 py-2 text-sm">Revise plan</button>
            <button type="button" onClick={book} className="rounded-full bg-torii px-4 py-2 text-sm font-medium text-white">Book these</button>
          </footer>
        </>
      )}
    </main>
  );
}
