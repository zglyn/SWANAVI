"use client";

import type { SegmentStatus, TripBrief } from "@contracts/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Logo } from "@/components/Logo";
import { getClient } from "@/lib/client";

const INTERESTS = ["temples", "food", "nature", "crafts", "nightlife", "shopping", "museums"];
const MODES = ["walk", "bike", "transit", "taxi"] as const;
const DESTINATIONS: Record<string, string> = {
  Kyoto: "Asia/Tokyo",
  Osaka: "Asia/Tokyo",
  Tokyo: "Asia/Tokyo",
};

function nightsBetween(start: string, end: string): string[] {
  const nights: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  if (Number.isNaN(cursor.getTime()) || Number.isNaN(last.getTime())) return nights;
  while (cursor < last) {
    nights.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return nights;
}

export default function PlanBriefPage() {
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [destination, setDestination] = useState("Kyoto");
  const [budget, setBudget] = useState("200");
  const [interests, setInterests] = useState<string[]>(["temples", "nature"]);
  const [pace, setPace] = useState<"relaxed" | "balanced" | "packed">("balanced");
  const [modes, setModes] = useState<string[]>(["walk", "transit"]);
  const [dailyStart, setDailyStart] = useState("09:00");
  const [dailyEnd, setDailyEnd] = useState("21:00");
  const [arrivalMode, setArrivalMode] = useState("flight");
  const [arrivalNumber, setArrivalNumber] = useState("JL3020");
  const [arrivalDate, setArrivalDate] = useState("2026-11-14");
  const [arrivalTime, setArrivalTime] = useState("10:35");
  const [arrivalPlace, setArrivalPlace] = useState("KIX");
  const [arrivalStatus, setArrivalStatus] = useState<SegmentStatus>("scheduled");
  const [stays, setStays] = useState([{ name: "Hotel Granvia Kyoto", checkIn: "2026-11-14", checkOut: "2026-11-16" }]);
  const [departureNumber, setDepartureNumber] = useState("JL3025");
  const [departureDate, setDepartureDate] = useState("2026-11-16");
  const [departureTime, setDepartureTime] = useState("18:20");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle(list: string[], value: string, set: (next: string[]) => void) {
    set(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  async function lookup() {
    try {
      const segment = await client.lookupFlight(arrivalNumber, arrivalDate);
      setArrivalTime(segment.arrive_at.slice(11, 16));
      setArrivalPlace(segment.to_place.code ?? segment.to_place.name);
      setArrivalStatus(segment.status);
      setError(null);
    } catch {
      setArrivalStatus("unverified");
      setError("Lookup failed. Enter the airport and time yourself.");
    }
  }

  const summary = `You land at ${arrivalPlace} ${arrivalTime} on ${arrivalDate} · leave ${departureDate} at ${departureTime} · stay at ${stays[0]?.name ?? "a hotel"}`;
  const lodgingGaps = nightsBetween(arrivalDate, departureDate).filter(
    (night) => !stays.some((stay) => stay.checkIn <= night && night < stay.checkOut),
  );

  async function submit() {
    const problems: string[] = [];
    if (Number(budget) <= 0) problems.push("Budget has to be more than zero.");
    if (interests.length === 0) problems.push("Pick at least one interest.");
    const arrive = new Date(`${arrivalDate}T${arrivalTime}:00+09:00`);
    const depart = new Date(`${departureDate}T${departureTime}:00+09:00`);
    if (!(depart > arrive)) problems.push("Departure has to be after arrival.");
    if (problems.length) {
      setError(problems.join(" "));
      return;
    }
    const brief: TripBrief = {
      destination: `${destination}, Japan`,
      timezone: DESTINATIONS[destination] ?? "Asia/Tokyo",
      budget,
      interests,
      pace,
      preferred_modes: modes as TripBrief["preferred_modes"],
      daily_start: dailyStart,
      daily_end: dailyEnd,
      arrival: {
        mode: arrivalMode === "flight" ? "flight" : arrivalMode === "train" ? "train" : "car",
        number: arrivalNumber,
        from_place: { name: "Origin" },
        to_place: { code: arrivalPlace, name: arrivalPlace },
        depart_at: `${arrivalDate}T${arrivalTime}:00+09:00`,
        arrive_at: `${arrivalDate}T${arrivalTime}:00+09:00`,
        status: arrivalStatus,
        source: arrivalStatus === "unverified" ? "user" : "fixture",
      },
      departure: {
        mode: "flight",
        number: departureNumber,
        from_place: { code: "KIX", name: "Kansai" },
        to_place: { name: "Home" },
        depart_at: `${departureDate}T${departureTime}:00+09:00`,
        arrive_at: `${departureDate}T${departureTime}:00+09:00`,
        status: "scheduled",
        source: "user",
      },
      lodging: stays.map((stay, index) => ({
        name: stay.name,
        location: index === 0 && destination === "Kyoto" ? { lat: 34.9858, lng: 135.7588 } : null,
        check_in: `${stay.checkIn}T15:00:00+09:00`,
        check_out: `${stay.checkOut}T11:00:00+09:00`,
      })),
      start_date: `${arrivalDate}T00:00:00+09:00`,
      end_date: `${departureDate}T00:00:00+09:00`,
    };
    setBusy(true);
    try {
      const created = await client.createPlan(brief);
      router.push(`/plan/${created.plan_id}/pick`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The gateway did not start a plan.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl overflow-x-hidden px-4 py-6 sm:px-6">
      <header className="mb-6 flex items-center justify-between">
        <Link href="/"><Logo /></Link>
        <Link href="/dashboard" className="text-sm text-ink-2">Open demo</Link>
      </header>
      <h1 className="font-serif text-4xl">Plan a trip</h1>
      <p className="mt-2 text-ink-2">{summary}</p>
      {error && <p className="mt-4 rounded-xl bg-torii-soft px-3 py-2 text-sm text-torii">{error}</p>}
      {lodgingGaps.length > 0 && <p className="mt-4 rounded-xl bg-amber-soft px-3 py-2 text-sm text-amber">No lodging on {lodgingGaps.join(", ")}.</p>}

      <section className="mt-6 space-y-3 rounded-2xl border border-line bg-card p-4">
        <h2 className="font-medium">Trip</h2>
        <label className="block text-sm">Destination
          <input list="cities" value={destination} onChange={(event) => setDestination(event.target.value)} className="mt-1 w-full rounded-xl border border-line px-3 py-2" />
          <datalist id="cities">{Object.keys(DESTINATIONS).map((city) => <option key={city} value={city} />)}</datalist>
        </label>
        <label className="block text-sm">Budget (RLUSD)
          <input value={budget} onChange={(event) => setBudget(event.target.value)} className="mt-1 w-full rounded-xl border border-line px-3 py-2" />
        </label>
        <div className="flex flex-wrap gap-2">
          {INTERESTS.map((interest) => (
            <button key={interest} type="button" onClick={() => toggle(interests, interest, setInterests)} className={`rounded-full px-3 py-1 text-sm ${interests.includes(interest) ? "bg-ink text-paper" : "bg-paper-2"}`}>{interest}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          {(["relaxed", "balanced", "packed"] as const).map((item) => (
            <button key={item} type="button" onClick={() => setPace(item)} className={`rounded-full px-3 py-1 ${pace === item ? "bg-indigo text-white" : "bg-paper-2"}`}>{item}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          {MODES.map((mode) => (
            <button key={mode} type="button" onClick={() => toggle(modes, mode, setModes)} className={`rounded-full px-3 py-1 ${modes.includes(mode) ? "bg-matcha text-white" : "bg-paper-2"}`}>{mode}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">Day starts<input type="time" value={dailyStart} onChange={(event) => setDailyStart(event.target.value)} className="mt-1 w-full rounded-xl border border-line px-3 py-2" /></label>
          <label className="text-sm">Day ends<input type="time" value={dailyEnd} onChange={(event) => setDailyEnd(event.target.value)} className="mt-1 w-full rounded-xl border border-line px-3 py-2" /></label>
        </div>
      </section>

      <section className="mt-4 space-y-3 rounded-2xl border border-line bg-card p-4">
        <h2 className="font-medium">Flights and stay</h2>
        <div className="flex flex-wrap gap-2 text-sm">
          {["flight", "train", "other"].map((mode) => (
            <button key={mode} type="button" onClick={() => setArrivalMode(mode)} className={`rounded-full px-3 py-1 ${arrivalMode === mode ? "bg-ink text-paper" : "bg-paper-2"}`}>{mode}</button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <input value={arrivalNumber} onChange={(event) => setArrivalNumber(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Arrival number" />
          <input type="date" value={arrivalDate} onChange={(event) => setArrivalDate(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Arrival date" />
          <button type="button" onClick={lookup} className="rounded-xl bg-paper-2 px-3 py-2 text-sm">Look up</button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <input value={arrivalPlace} onChange={(event) => setArrivalPlace(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Arrival place" />
          <input type="time" value={arrivalTime} onChange={(event) => setArrivalTime(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Arrival time" />
        </div>
        <p className="text-xs text-ink-3">{arrivalStatus === "unverified" ? "Unverified manual entry" : `Status: ${arrivalStatus}`}</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <input value={departureNumber} onChange={(event) => setDepartureNumber(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Departure number" />
          <input type="date" value={departureDate} onChange={(event) => setDepartureDate(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Departure date" />
          <input type="time" value={departureTime} onChange={(event) => setDepartureTime(event.target.value)} className="rounded-xl border border-line px-3 py-2" aria-label="Departure time" />
        </div>
        {stays.map((stay, index) => (
          <div key={index} className="grid gap-3 sm:grid-cols-3">
            <input value={stay.name} aria-label={`Hotel ${index + 1}`} onChange={(event) => setStays((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} className="rounded-xl border border-line px-3 py-2" />
            <input type="date" value={stay.checkIn} aria-label={`Check in ${index + 1}`} onChange={(event) => setStays((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, checkIn: event.target.value } : item))} className="rounded-xl border border-line px-3 py-2" />
            <input type="date" value={stay.checkOut} aria-label={`Check out ${index + 1}`} onChange={(event) => setStays((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, checkOut: event.target.value } : item))} className="rounded-xl border border-line px-3 py-2" />
          </div>
        ))}
        <button type="button" onClick={() => setStays((current) => [...current, { name: "", checkIn: arrivalDate, checkOut: departureDate }])} className="text-sm text-indigo">Add another stay</button>
      </section>

      <button type="button" disabled={busy} onClick={submit} className="mt-6 w-full rounded-full bg-torii py-3 font-medium text-white disabled:opacity-50 sm:w-auto sm:px-8">
        {busy ? "Finding places…" : "Find places"}
      </button>
    </main>
  );
}
