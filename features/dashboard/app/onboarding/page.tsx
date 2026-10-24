"use client";

import type { Autonomy, BudgetLevel, UserProfile } from "@contracts/api";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { TripMap } from "@/components/map3d/TripMap";
import { SwanShell } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { lookupPlace, nearestAirports } from "@/lib/places";

const INTERESTS = ["temples", "food", "nature", "museums", "nightlife", "shopping", "crafts", "beaches"];
const BRANDS = ["Hyatt", "Marriott", "Hilton", "IHG", "Accor", "boutique"];
const AIRLINES = ["JL", "NH", "UA", "AA", "DL"];
const STEPS = 8;

function blank(): UserProfile {
  return {
    user_id: "local",
    name: "",
    home: { address: "", location: { lat: 37.77, lng: -122.42 }, airport_codes: ["SFO"] },
    currency: "USD",
    travel: {
      interests: ["temples", "food"],
      pace: "balanced",
      budget_level: "mid",
      preferred_modes: ["walk", "transit"],
      dietary: [],
      accessibility: [],
      avoid: [],
    },
    sleep: { wake_time: "07:30", sleep_time: "23:00", jet_lag_buffer: true },
    hotels: { favourite_brands: [], min_stars: 3, must_have: ["wifi"], room_type: null, loyalty: [] },
    flights: {
      favourite_airlines: [],
      alliances: [],
      cabin: "economy",
      max_stops: 1,
      seat: "any",
      loyalty: [],
      avoid_red_eye: true,
    },
    autonomy: { attractions: "swan_decides", hotels: "swan_decides", flights: "swan_decides" },
  };
}

export default function OnboardingPage() {
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<UserProfile>(blank);
  const [avoid, setAvoid] = useState("");
  const [loyaltyHotel, setLoyaltyHotel] = useState("");
  const [loyaltyAir, setLoyaltyAir] = useState("");

  async function geocode() {
    const hit = await lookupPlace(profile.home.address);
    if (!hit) return;
    setProfile({
      ...profile,
      home: { address: hit.label, location: { lat: hit.lat, lng: hit.lng }, airport_codes: hit.airports.length ? hit.airports : nearestAirports(hit.lat, hit.lng) },
    });
  }

  function toggle(list: string[], value: string) {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  async function save() {
    const next = {
      ...profile,
      travel: { ...profile.travel, avoid: avoid.split(",").map((item) => item.trim()).filter(Boolean) },
      hotels: { ...profile.hotels, loyalty: loyaltyHotel ? [{ program: loyaltyHotel, number: null }] : [] },
      flights: { ...profile.flights, loyalty: loyaltyAir ? [{ program: loyaltyAir, number: null }] : profile.flights.loyalty },
    };
    await client.putProfile(next);
    router.push("/");
  }

  return (
    <SwanShell step={step} steps={STEPS}>
      {step === 1 && (
        <section>
          <h1 className="text-4xl">Where is home?</h1>
          <label className="mt-6 block">Address
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={profile.home.address} onChange={(event) => setProfile({ ...profile, home: { ...profile.home, address: event.target.value } })} />
          </label>
          <button type="button" className="swan-btn-ghost mt-3" onClick={geocode}>Find it</button>
          <div className="mt-4 h-60 overflow-hidden rounded-3xl">
            <TripMap
              stops={[{ id: "home", lat: profile.home.location.lat, lng: profile.home.location.lng, label: "Home", kind: "stop" }]}
              arcs={[]}
              focus={0}
              dayLabel="Home"
            />
          </div>
          <p className="swan-muted mt-3 text-sm">Pin {profile.home.location.lat.toFixed(2)}, {profile.home.location.lng.toFixed(2)}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {profile.home.airport_codes.map((code) => <span key={code} className="swan-chip">{code}</span>)}
          </div>
        </section>
      )}
      {step === 2 && (
        <section>
          <h1 className="text-4xl">What do you love?</h1>
          <div className="mt-6 flex flex-wrap gap-2">
            {INTERESTS.map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={profile.travel.interests.includes(item)} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, interests: toggle(profile.travel.interests, item) } })}>{item}</button>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            {(["budget", "mid", "premium", "luxury"] as BudgetLevel[]).map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={profile.travel.budget_level === item} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, budget_level: item } })}>{item}</button>
            ))}
          </div>
        </section>
      )}
      {step === 3 && (
        <section>
          <h1 className="text-4xl">Your rhythm</h1>
          <label className="mt-6 block">Wake
            <input type="time" className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={profile.sleep.wake_time} onChange={(event) => setProfile({ ...profile, sleep: { ...profile.sleep, wake_time: event.target.value } })} />
          </label>
          <label className="mt-3 block">Bedtime
            <input type="time" className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={profile.sleep.sleep_time} onChange={(event) => setProfile({ ...profile, sleep: { ...profile.sleep, sleep_time: event.target.value } })} />
          </label>
          <div className="mt-4 flex flex-wrap gap-2">
            {(["relaxed", "balanced", "packed"] as const).map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={profile.travel.pace === item} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, pace: item } })}>{item}</button>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-3">
            <input type="checkbox" checked={profile.sleep.jet_lag_buffer} onChange={(event) => setProfile({ ...profile, sleep: { ...profile.sleep, jet_lag_buffer: event.target.checked } })} />
            Go easy on day 1 after long flights
          </label>
        </section>
      )}
      {step === 4 && (
        <section>
          <h1 className="text-4xl">Getting around</h1>
          <div className="mt-6 flex flex-wrap gap-2">
            {["walk", "bike", "transit", "taxi"].map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={profile.travel.preferred_modes.includes(item as "walk")} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, preferred_modes: toggle(profile.travel.preferred_modes, item) as UserProfile["travel"]["preferred_modes"] } })}>{item}</button>
            ))}
          </div>
          <label className="mt-4 block">Avoid
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={avoid} placeholder="crowds, long walks" onChange={(event) => setAvoid(event.target.value)} />
          </label>
          <label className="mt-3 block">Accessibility
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={profile.travel.accessibility.join(", ")} onChange={(event) => setProfile({ ...profile, travel: { ...profile.travel, accessibility: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} />
          </label>
        </section>
      )}
      {step === 5 && (
        <section>
          <h1 className="text-4xl">Hotels</h1>
          <div className="mt-6 flex flex-wrap gap-2">
            {BRANDS.map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={profile.hotels.favourite_brands.includes(item)} onClick={() => setProfile({ ...profile, hotels: { ...profile.hotels, favourite_brands: toggle(profile.hotels.favourite_brands, item) } })}>{item}</button>
            ))}
          </div>
          <label className="mt-4 block">Loyalty programme
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={loyaltyHotel} onChange={(event) => setLoyaltyHotel(event.target.value)} placeholder="World of Hyatt" />
          </label>
        </section>
      )}
      {step === 6 && (
        <section>
          <h1 className="text-4xl">Flights</h1>
          <div className="mt-6 flex flex-wrap gap-2">
            {AIRLINES.map((item) => (
              <button key={item} type="button" className="swan-chip" aria-pressed={profile.flights.favourite_airlines.includes(item)} onClick={() => setProfile({ ...profile, flights: { ...profile.flights, favourite_airlines: toggle(profile.flights.favourite_airlines, item) } })}>{item}</button>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-3">
            <input type="checkbox" checked={profile.flights.avoid_red_eye} onChange={(event) => setProfile({ ...profile, flights: { ...profile.flights, avoid_red_eye: event.target.checked } })} />
            Avoid red-eyes
          </label>
          <label className="mt-3 block">Airline loyalty
            <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={loyaltyAir} onChange={(event) => setLoyaltyAir(event.target.value)} placeholder="JAL Mileage Bank" />
          </label>
        </section>
      )}
      {step === 7 && (
        <section>
          <h1 className="text-4xl">How much should Swan handle?</h1>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <div key={key} className="mt-4">
              <p className="capitalize">{key}</p>
              <div className="mt-2 flex gap-2">
                {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                  <button key={item} type="button" className="swan-chip" aria-pressed={profile.autonomy[key] === item} onClick={() => setProfile({ ...profile, autonomy: { ...profile.autonomy, [key]: item } })}>
                    {item === "swan_decides" ? "Swan decides" : "I choose"}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
      {step === 8 && (
        <section>
          <h1 className="text-4xl">You are set.</h1>
          <p className="swan-muted mt-3">{profile.home.address || "Home"} · {profile.travel.interests.join(", ") || "open interests"} · wake {profile.sleep.wake_time}</p>
          <button type="button" className="swan-btn mt-6" onClick={save}>Save and plan a trip</button>
        </section>
      )}
      <div className="mt-8 flex gap-3">
        {step > 1 && <button type="button" className="swan-btn-ghost" onClick={() => setStep(step - 1)}>Back</button>}
        {step < 8 && <button type="button" className="swan-btn" onClick={() => setStep(step + 1)}>{step === 1 && !profile.home.address ? "Skip" : "Next"}</button>}
      </div>
    </SwanShell>
  );
}
