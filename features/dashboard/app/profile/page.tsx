"use client";

import type { UserProfile } from "@contracts/api";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { SwanShell } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { airlineName } from "@/lib/format";

const BRANDS = ["Hyatt", "Marriott", "Hilton", "IHG", "Accor", "boutique"];
const AIRLINES = ["JL", "NH", "UA", "AA", "DL"];
const MODES = ["walk", "bike", "transit", "taxi"] as const;

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export default function ProfilePage() {
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    client.getProfile().then(setProfile).catch(() => setProfile(null));
  }, [client]);

  async function save(next: UserProfile) {
    setProfile(next);
    await client.putProfile(next);
    setSaved(true);
  }

  async function remove() {
    await client.deleteAccount();
    setProfile(null);
  }

  if (!profile) {
    return (
      <SwanShell>
        <h1 className="text-4xl">No profile yet</h1>
        <Link href="/onboarding" className="swan-btn mt-6 inline-flex items-center">Set up Swanavi</Link>
      </SwanShell>
    );
  }

  const field = "swan-line mt-2 w-full rounded-2xl border px-4 py-3";

  return (
    <SwanShell wide>
      <div className="flex items-baseline justify-between">
        <h1 className="text-4xl">Profile</h1>
        {saved && <p className="swan-badge" role="status">Saved</p>}
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Card title="You">
          <label className="block">
            <span className="font-medium">Name</span>
            <input className={field} value={profile.name} onChange={(event) => save({ ...profile, name: event.target.value })} />
          </label>
          <label className="mt-3 block">
            <span className="font-medium">Home</span>
            <input className={field} value={profile.home.address} onChange={(event) => save({ ...profile, home: { ...profile.home, address: event.target.value } })} />
          </label>
          <p className="swan-muted mt-3 text-sm">Fly from {profile.home.airport_codes.join(" · ") || "no airports yet"}</p>
        </Card>

        <Card title="Your rhythm">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="font-medium">Wake</span>
              <input type="time" className={field} value={profile.sleep.wake_time} onChange={(event) => save({ ...profile, sleep: { ...profile.sleep, wake_time: event.target.value } })} />
            </label>
            <label className="block">
              <span className="font-medium">Bedtime</span>
              <input type="time" className={field} value={profile.sleep.sleep_time} onChange={(event) => save({ ...profile, sleep: { ...profile.sleep, sleep_time: event.target.value } })} />
            </label>
          </div>
          <div className="swan-seg mt-4" role="radiogroup" aria-label="Pace">
            {(["relaxed", "balanced", "packed"] as const).map((item) => (
              <button key={item} type="button" role="radio" aria-checked={profile.travel.pace === item} onClick={() => save({ ...profile, travel: { ...profile.travel, pace: item } })}>{item[0].toUpperCase() + item.slice(1)}</button>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-3">
            <input type="checkbox" checked={profile.sleep.jet_lag_buffer} onChange={(event) => save({ ...profile, sleep: { ...profile.sleep, jet_lag_buffer: event.target.checked } })} />
            Go easy on day 1 after long flights
          </label>
        </Card>

        <Card title="Getting around">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Preferred modes">
            {MODES.map((item) => (
              <button key={item} type="button" className="swan-filter capitalize" aria-pressed={profile.travel.preferred_modes.includes(item)} onClick={() => save({ ...profile, travel: { ...profile.travel, preferred_modes: toggle(profile.travel.preferred_modes, item) } })}>{item}</button>
            ))}
          </div>
          <label className="mt-4 block">
            <span className="font-medium">Avoid</span>
            <input className={field} value={profile.travel.avoid.join(", ")} placeholder="crowds, long walks" onChange={(event) => save({ ...profile, travel: { ...profile.travel, avoid: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} />
          </label>
          <label className="mt-3 block">
            <span className="font-medium">Accessibility</span>
            <input className={field} value={profile.travel.accessibility.join(", ")} placeholder="step-free" onChange={(event) => save({ ...profile, travel: { ...profile.travel, accessibility: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} />
          </label>
        </Card>

        <Card title="Interests">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Interests">
            {["temples", "food", "nature", "museums", "nightlife", "shopping", "crafts", "beaches"].map((item) => (
              <button key={item} type="button" className="swan-filter capitalize" aria-pressed={profile.travel.interests.includes(item)} onClick={() => save({ ...profile, travel: { ...profile.travel, interests: toggle(profile.travel.interests, item) } })}>{item}</button>
            ))}
          </div>
        </Card>

        <Card title="Hotels">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Favourite brands">
            {BRANDS.map((item) => (
              <button key={item} type="button" className="swan-filter" aria-pressed={profile.hotels.favourite_brands.includes(item)} onClick={() => save({ ...profile, hotels: { ...profile.hotels, favourite_brands: toggle(profile.hotels.favourite_brands, item) } })}>{item}</button>
            ))}
          </div>
          <label className="mt-4 block">
            <span className="font-medium">Loyalty programme</span>
            <input className={field} value={profile.hotels.loyalty[0]?.program ?? ""} placeholder="World of Hyatt" onChange={(event) => save({ ...profile, hotels: { ...profile.hotels, loyalty: event.target.value ? [{ program: event.target.value, number: profile.hotels.loyalty[0]?.number ?? null }] : [] } })} />
          </label>
        </Card>

        <Card title="Flights">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Favourite airlines">
            {AIRLINES.map((item) => (
              <button key={item} type="button" className="swan-filter" aria-pressed={profile.flights.favourite_airlines.includes(item)} onClick={() => save({ ...profile, flights: { ...profile.flights, favourite_airlines: toggle(profile.flights.favourite_airlines, item) } })}>{airlineName(item)}</button>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-3">
            <input type="checkbox" checked={profile.flights.avoid_red_eye} onChange={(event) => save({ ...profile, flights: { ...profile.flights, avoid_red_eye: event.target.checked } })} />
            Avoid red-eyes
          </label>
          <label className="mt-3 block">
            <span className="font-medium">Airline loyalty</span>
            <input className={field} value={profile.flights.loyalty[0]?.program ?? ""} placeholder="JAL Mileage Bank" onChange={(event) => save({ ...profile, flights: { ...profile.flights, loyalty: event.target.value ? [{ program: event.target.value, number: profile.flights.loyalty[0]?.number ?? null }] : [] } })} />
          </label>
        </Card>
      </div>
      <button type="button" className="swan-btn-ghost mt-8" onClick={remove}>Delete my account</button>
    </SwanShell>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="swan-card p-5">
      <h2 className="text-xl">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}
