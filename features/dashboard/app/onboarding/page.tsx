"use client";

import type { Autonomy, BudgetLevel, UserProfile } from "@contracts/api";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ChoiceField,
  ChoiceFlow,
  ChoiceNote,
  ChoicePill,
  ChoicePills,
  ChoiceRow,
  ChoiceSection,
  ChoiceStack,
} from "@/components/choice/ChoiceFlow";
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
      router.push("/");
    } finally {
      setBusy(false);
    }
  }

  const title = step === 1 ? "Where is home?" : step === 2 ? "What do you love?" : "How much should Swanavi handle?";

  return (
    <ChoiceFlow
      title={title}
      step={step}
      steps={STEPS}
      action={step === STEPS ? (busy ? "Saving…" : "Save and plan a trip") : "Continue"}
      onAction={step === STEPS ? save : () => setStep(step + 1)}
      actionDisabled={step === STEPS && busy}
      onBack={step > 1 ? () => setStep(step - 1) : undefined}
    >
      {step === 1 && (
        <ChoiceSection>
          <ChoiceNote>Trips start from here. Swanavi searches flights from the airports nearby.</ChoiceNote>
          <div style={{ marginTop: 16 }}>
            <ChoiceField
              label="City or address"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="San Francisco"
              autoComplete="off"
              aria-autocomplete="list"
              aria-controls="home-suggestions"
              aria-expanded={hits.length > 0}
            />
          </div>
          <ChoiceStack as="ul">
            {hits.map((hit) => (
              <li key={`${hit.label}-${hit.lat}`}>
                <ChoiceRow pressed={false} onClick={() => pickHome(hit)}>
                  {hit.label}
                </ChoiceRow>
              </li>
            ))}
          </ChoiceStack>
          {searching ? <ChoiceNote>Looking up places…</ChoiceNote> : null}
          {profile.home.address ? (
            <div style={{ marginTop: 20 }}>
              <ChoiceNote>Fly from</ChoiceNote>
              <ChoicePills>
                {nearestAirports(profile.home.location.lat, profile.home.location.lng).map((code) => (
                  <ChoicePill
                    key={code}
                    pressed={profile.home.airport_codes.includes(code)}
                    onClick={() => setProfile({ ...profile, home: { ...profile.home, airport_codes: toggle(profile.home.airport_codes, code) } })}
                  >
                    {code}
                  </ChoicePill>
                ))}
              </ChoicePills>
            </div>
          ) : (
            <div style={{ marginTop: 16 }}>
              <ChoiceRow pressed={false} onClick={() => setStep(2)}>Skip for now</ChoiceRow>
            </div>
          )}
        </ChoiceSection>
      )}
      {step === 2 && (
        <>
          <ChoiceSection title="Interests">
            <ChoicePills>
              {INTERESTS.map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.travel.interests.includes(item)}
                  onClick={() => setProfile({ ...profile, travel: { ...profile.travel, interests: toggle(profile.travel.interests, item) } })}
                >
                  {item[0].toUpperCase() + item.slice(1)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection title="Budget">
            <ChoicePills>
              {(["budget", "mid", "premium", "luxury"] as BudgetLevel[]).map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.travel.budget_level === item}
                  onClick={() => setProfile({ ...profile, travel: { ...profile.travel, budget_level: item } })}
                >
                  {BUDGET_LABEL[item]}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection title="Pace">
            <ChoicePills>
              {(["relaxed", "balanced", "packed"] as const).map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.travel.pace === item}
                  onClick={() => setProfile({ ...profile, travel: { ...profile.travel, pace: item } })}
                >
                  {item[0].toUpperCase() + item.slice(1)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
        </>
      )}
      {step === 3 && (
        <>
          <ChoiceNote>You can change this per trip.</ChoiceNote>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <ChoiceSection key={key} title={key[0].toUpperCase() + key.slice(1)}>
              <ChoicePills>
                {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                  <ChoicePill
                    key={item}
                    pressed={profile.autonomy[key] === item}
                    onClick={() => setProfile({ ...profile, autonomy: { ...profile.autonomy, [key]: item } })}
                  >
                    {item === "swan_decides" ? "Swanavi decides" : "I choose"}
                  </ChoicePill>
                ))}
              </ChoicePills>
            </ChoiceSection>
          ))}
        </>
      )}
    </ChoiceFlow>
  );
}
