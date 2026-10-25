"use client";

import type { Autonomy, BudgetLevel, UserProfile } from "@contracts/api";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { SwanShell } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { nearestAirports, suggestPlaces, type PlaceHit } from "@/lib/places";

const INTERESTS = ["temples", "food", "nature", "museums", "nightlife", "shopping", "crafts", "beaches"];
const BUDGET_LABEL: Record<BudgetLevel, string> = { budget: "Budget", mid: "Mid-range", premium: "Premium", luxury: "Luxury" };
const STEPS = 3;
const HOME = { lat: 37.77, lng: -122.42 };

function blank(): UserProfile {
  return {
    user_id: "local",
    name: "",
    home: { address: "", location: HOME, airport_codes: nearestAirports(HOME.lat, HOME.lng) },
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
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (query.trim().length < 2 || query === profile.home.address) {
      setHits([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true);
      const found = await suggestPlaces(query, controller.signal);
      if (!controller.signal.aborted) {
        setHits(found);
        setSearching(false);
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, profile.home.address]);

  function pickHome(hit: PlaceHit) {
    setProfile({
      ...profile,
      home: { address: hit.label, location: { lat: hit.lat, lng: hit.lng }, airport_codes: nearestAirports(hit.lat, hit.lng) },
    });
    setQuery(hit.label);
    setHits([]);
  }

  function toggle(list: string[], value: string) {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  async function save() {
    if (busy) return;
    setBusy(true);
    try {
      await client.putProfile(profile);
      router.push("/plan/new");
    } finally {
      setBusy(false);
    }
  }

  const aside = (
    <div>
      <p className="swan-eyebrow">Two minutes, once</p>
      <p className="mt-2 text-sm">Swanavi asks for home and what you love now. Hotel brands and airlines come up the first time they matter, and you can change anything later in your profile.</p>
    </div>
  );

  return (
    <SwanShell step={step} steps={STEPS} aside={aside}>
      {step === 1 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">Where is home?</h1>
          <p className="swan-muted mt-3">Trips start from here. Swanavi searches flights from the airports nearby.</p>
          <label className="mt-6 block">
            <span className="font-medium">City or address</span>
            <input
              className="swan-line mt-2 w-full rounded-2xl border px-4 py-3 text-lg"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="San Francisco"
              autoComplete="off"
              aria-autocomplete="list"
              aria-controls="home-suggestions"
              aria-expanded={hits.length > 0}
            />
          </label>
          <ul id="home-suggestions" className="mt-2 space-y-1" role="listbox" aria-label="Suggestions" aria-busy={searching}>
            {hits.map((hit) => (
              <li key={`${hit.label}-${hit.lat}`} role="option" aria-selected={false}>
                <button type="button" className="swan-card w-full px-4 py-3 text-left hover:bg-neutral-50" onClick={() => pickHome(hit)}>
                  <span className="font-medium">{hit.label}</span>
                  <span className="swan-muted block text-sm">{hit.airports.join(" · ")}</span>
                </button>
              </li>
            ))}
          </ul>
          {profile.home.address ? (
            <div className="mt-5">
              <p className="font-medium">Fly from</p>
              <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Home airports">
                {nearestAirports(profile.home.location.lat, profile.home.location.lng).map((code) => (
                  <button
                    key={code}
                    type="button"
                    className="swan-filter"
                    aria-pressed={profile.home.airport_codes.includes(code)}
                    onClick={() => setProfile({ ...profile, home: { ...profile.home, airport_codes: toggle(profile.home.airport_codes, code) } })}
                  >
                    {code}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      )}
      {step === 2 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">What do you love?</h1>
          <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Interests">
            {INTERESTS.map((item) => (
              <button key={item} type="button" className="swan-filter capitalize" aria-pressed={profile.travel.interests.includes(item)} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, interests: toggle(profile.travel.interests, item) } })}>{item}</button>
            ))}
          </div>
          <p className="mt-6 font-medium">Budget</p>
          <div className="swan-seg mt-2" role="radiogroup" aria-label="Budget">
            {(["budget", "mid", "premium", "luxury"] as BudgetLevel[]).map((item) => (
              <button key={item} type="button" role="radio" aria-checked={profile.travel.budget_level === item} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, budget_level: item } })}>{BUDGET_LABEL[item]}</button>
            ))}
          </div>
          <p className="mt-6 font-medium">Pace</p>
          <div className="swan-seg mt-2" role="radiogroup" aria-label="Pace">
            {(["relaxed", "balanced", "packed"] as const).map((item) => (
              <button key={item} type="button" role="radio" aria-checked={profile.travel.pace === item} onClick={() => setProfile({ ...profile, travel: { ...profile.travel, pace: item } })}>{item[0].toUpperCase() + item.slice(1)}</button>
            ))}
          </div>
        </section>
      )}
      {step === 3 && (
        <section>
          <h1 className="text-4xl sm:text-5xl">How much should Swanavi handle?</h1>
          <p className="swan-muted mt-3">You can change this per trip.</p>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <div key={key} className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <p className="font-medium capitalize">{key}</p>
              <div className="swan-seg" role="radiogroup" aria-label={key}>
                {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                  <button key={item} type="button" role="radio" aria-checked={profile.autonomy[key] === item} onClick={() => setProfile({ ...profile, autonomy: { ...profile.autonomy, [key]: item } })}>
                    {item === "swan_decides" ? "Swanavi decides" : "I choose"}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
      <div className="mt-8 flex flex-wrap items-center gap-3">
        {step > 1 && <button type="button" className="swan-btn-ghost" onClick={() => setStep(step - 1)}>Back</button>}
        {step < STEPS && <button type="button" className="swan-btn" onClick={() => setStep(step + 1)}>Continue</button>}
        {step === 1 && !profile.home.address && <button type="button" className="swan-btn-quiet" onClick={() => setStep(2)}>Skip for now</button>}
        {step === STEPS && <button type="button" className="swan-btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save and plan a trip"}</button>}
      </div>
    </SwanShell>
  );
}
