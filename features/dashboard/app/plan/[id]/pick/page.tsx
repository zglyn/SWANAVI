"use client";

import type { Candidate, InspectorEvent, PlanSelection } from "@contracts/api";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Logo } from "@/components/Logo";
import { StopMap } from "@/components/plan/StopMap";
import { ToolProgress } from "@/components/plan/ToolProgress";
import { getClient } from "@/lib/client";

type Choice = "must" | "maybe" | "skip";

export default function PickPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [events, setEvents] = useState<InspectorEvent[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [hours, setHours] = useState(0);
  const [choice, setChoice] = useState<Record<string, Choice>>({});
  const [interest, setInterest] = useState<string | null>(null);
  const [freeOnly, setFreeOnly] = useState(false);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    const stop = client.subscribe((event) => setEvents((prev) => prev.some((item) => item.id === event.id) ? prev : [...prev, event]), (status) => setDown(status === "down"));
    let timer = window.setTimeout(() => setError("No candidates yet. Try again."), 60_000);
    client.getPlan(params.id).then((view) => {
      window.clearTimeout(timer);
      if (view.status === "ready" && view.itinerary) router.replace(`/plan/${params.id}`);
      if (view.status === "planning") router.replace(`/plan/${params.id}`);
      if (view.candidates) {
        setCandidates(view.candidates.candidates);
        setHours(view.candidates.available_hours);
        setChoice(Object.fromEntries(view.candidates.candidates.map((item) => [item.id, "maybe" as Choice])));
        setError(null);
      } else if (view.error) setError(view.error);
    }).catch(() => setError("The gateway is not responding."));
    return () => {
      window.clearTimeout(timer);
      stop();
    };
  }, [client, params.id, router]);

  useEffect(() => {
    const ready = [...events].reverse().find((event) => event.type === "plan.candidates");
    const payload = ready?.data.candidates as { candidates: Candidate[]; available_hours: number } | undefined;
    if (!payload) return;
    setCandidates(payload.candidates);
    setHours(payload.available_hours);
    setChoice((current) => Object.keys(current).length ? current : Object.fromEntries(payload.candidates.map((item) => [item.id, "maybe" as Choice])));
    setError(null);
  }, [events]);

  const interests = [...new Set(candidates.map((item) => item.attraction?.category).filter(Boolean))] as string[];
  const shown = candidates.filter((item) => {
    if (interest && item.attraction && item.attraction.category !== interest) return false;
    if (freeOnly && item.attraction && !item.attraction.free) return false;
    if (verifiedOnly && item.merchant && item.quote?.merchant_verified === false) return false;
    return true;
  });
  const selectedHours = candidates.reduce((sum, item) => {
    if (choice[item.id] === "skip") return sum;
    return sum + (item.attraction?.typical_duration_min ?? 60) / 60;
  }, 0);

  async function submit() {
    const selection: PlanSelection = { must_visit: [], maybe: [], excluded: [] };
    for (const item of candidates) {
      const bucket = choice[item.id] ?? "maybe";
      if (bucket === "must") selection.must_visit.push(item.id);
      else if (bucket === "skip") selection.excluded.push(item.id);
      else selection.maybe.push(item.id);
    }
    try {
      await client.submitSelection(params.id, selection);
      router.push(`/plan/${params.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the itinerary.");
    }
  }

  return (
    <main className="mx-auto max-w-6xl overflow-x-hidden px-4 py-6 sm:px-6">
      <header className="mb-4 flex items-center justify-between gap-3">
        <Link href="/"><Logo /></Link>
        <span className="text-xs text-ink-3">{down ? "Reconnecting" : client.mode === "mock" ? "mock data" : "gateway"}</span>
      </header>
      <h1 className="font-serif text-4xl">What do you actually want to do?</h1>
      {error && (
        <p className="mt-3 rounded-xl bg-torii-soft px-3 py-2 text-sm text-torii">
          {error} <button type="button" className="underline" onClick={() => location.reload()}>Try again</button>
        </p>
      )}
      {candidates.length === 0 && <div className="mt-4"><ToolProgress events={events} /></div>}
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <button type="button" onClick={() => setInterest(null)} className={`rounded-full px-3 py-1 ${interest === null ? "bg-ink text-paper" : "bg-paper-2"}`}>All</button>
        {interests.map((item) => (
          <button key={item} type="button" onClick={() => setInterest(item)} className={`rounded-full px-3 py-1 ${interest === item ? "bg-ink text-paper" : "bg-paper-2"}`}>{item}</button>
        ))}
        <button type="button" onClick={() => setFreeOnly((value) => !value)} className={`rounded-full px-3 py-1 ${freeOnly ? "bg-matcha text-white" : "bg-paper-2"}`}>Free only</button>
        <button type="button" onClick={() => setVerifiedOnly((value) => !value)} className={`rounded-full px-3 py-1 ${verifiedOnly ? "bg-matcha text-white" : "bg-paper-2"}`}>Verified shops</button>
      </div>
      <p className="mt-3 text-sm text-ink-2">About {selectedHours.toFixed(1)} h selected vs {hours.toFixed(1)} h available. {selectedHours > hours ? "That is more than the trip window. You can still build it." : "Fits the window."}</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <ul className="grid gap-3 sm:grid-cols-2">
          {shown.map((item) => {
            const title = item.attraction?.name ?? item.merchant?.name ?? item.id;
            const photo = item.attraction?.image_url;
            const blurb = item.attraction?.description ?? item.quote?.title ?? "";
            const area = item.attraction?.area ?? item.merchant?.city;
            return (
              <li key={item.id} className="overflow-hidden rounded-2xl border border-line bg-card">
                {photo && <img src={photo} alt="" className="h-32 w-full object-cover" />}
                <div className="space-y-2 p-3">
                  <div className="font-medium">{title}</div>
                  <p className="text-sm text-ink-2">{blurb}</p>
                  <p className="text-xs text-ink-3">{area} · {item.attraction ? `${item.attraction.typical_duration_min} min` : item.quote ? `${item.quote.amount} ${item.quote.currency}` : ""} {item.attraction?.free ? "· Free" : ""} {item.quote?.merchant_verified ? "· Verified" : ""}</p>
                  <div className="flex flex-wrap gap-1 text-xs">
                    {(["must", "maybe", "skip"] as const).map((bucket) => (
                      <button key={bucket} type="button" onClick={() => setChoice((current) => ({ ...current, [item.id]: bucket }))} className={`rounded-full px-2 py-1 ${(choice[item.id] ?? "maybe") === bucket ? "bg-ink text-paper" : "bg-paper-2"}`}>
                        {bucket === "must" ? "Must go" : bucket === "maybe" ? "Maybe" : "Skip"}
                      </button>
                    ))}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
        <StopMap points={shown.map((item) => {
          const loc = item.attraction?.location ?? item.merchant?.location ?? item.quote?.location;
          const bucket = choice[item.id] ?? "maybe";
          return {
            id: item.id,
            lat: loc?.lat ?? 35,
            lng: loc?.lng ?? 135,
            label: item.attraction?.name ?? item.merchant?.name ?? item.id,
            color: bucket === "must" ? "#c8371d" : bucket === "skip" ? "#8a857a" : "#2f4b9a",
          };
        })} />
      </div>
      <button type="button" onClick={submit} disabled={candidates.length === 0} className="mt-6 rounded-full bg-torii px-6 py-3 font-medium text-white disabled:opacity-40">Build my itinerary</button>
    </main>
  );
}
