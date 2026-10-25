"use client";

import type { Autonomy, BudgetLevel, UserProfile } from "@contracts/api";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  ChoiceField,
  ChoiceFlow,
  ChoiceNote,
  ChoicePill,
  ChoicePills,
  ChoiceRow,
  ChoiceSection,
  ChoiceStack,
  ChoiceSummary,
} from "@/components/choice/ChoiceFlow";
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

function labelOf(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function OnboardingPage() {
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<UserProfile>(blank);
  const [avoid, setAvoid] = useState("");
  const [loyaltyHotel, setLoyaltyHotel] = useState("");
  const [loyaltyAir, setLoyaltyAir] = useState("");
  const [busy, setBusy] = useState(false);

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
    if (busy) return;
    setBusy(true);
    const next = {
      ...profile,
      travel: { ...profile.travel, avoid: avoid.split(",").map((item) => item.trim()).filter(Boolean) },
      hotels: { ...profile.hotels, loyalty: loyaltyHotel ? [{ program: loyaltyHotel, number: null }] : [] },
      flights: { ...profile.flights, loyalty: loyaltyAir ? [{ program: loyaltyAir, number: null }] : profile.flights.loyalty },
    };
    try {
      await client.putProfile(next);
      router.push("/");
    } catch {
      setBusy(false);
    }
  }

  const titles = [
    "Where is home?",
    "What do you love?",
    "Your rhythm",
    "Getting around",
    "Hotels",
    "Flights",
    "How much should Swanavi handle?",
    "You are set.",
  ];

  return (
    <ChoiceFlow
      title={titles[step - 1] ?? "You are set."}
      step={step}
      steps={STEPS}
      action={step === STEPS ? "Confirm" : step === 1 && !profile.home.address ? "Skip" : "Continue"}
      onAction={step === STEPS ? save : () => setStep(step + 1)}
      actionDisabled={step === STEPS && busy}
      onBack={step > 1 ? () => setStep(step - 1) : undefined}
    >
      {step === 1 && (
        <ChoiceSection>
          <ChoiceField
            label="Address"
            value={profile.home.address}
            onChange={(event) => setProfile({ ...profile, home: { ...profile.home, address: event.target.value } })}
          />
          <div style={{ marginTop: 12 }}>
            <ChoiceStack>
              <ChoiceRow onClick={geocode}>Find it</ChoiceRow>
            </ChoiceStack>
          </div>
          <ChoiceNote>
            {profile.home.location.lat.toFixed(2)}, {profile.home.location.lng.toFixed(2)}
            {profile.home.airport_codes.length ? ` · ${profile.home.airport_codes.join(" · ")}` : ""}
          </ChoiceNote>
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
                  {labelOf(item)}
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
                  {labelOf(item)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
        </>
      )}
      {step === 3 && (
        <>
          <ChoiceSection>
            <ChoiceField
              label="Wake"
              type="time"
              value={profile.sleep.wake_time}
              onChange={(event) => setProfile({ ...profile, sleep: { ...profile.sleep, wake_time: event.target.value } })}
            />
            <div style={{ marginTop: 16 }}>
              <ChoiceField
                label="Bedtime"
                type="time"
                value={profile.sleep.sleep_time}
                onChange={(event) => setProfile({ ...profile, sleep: { ...profile.sleep, sleep_time: event.target.value } })}
              />
            </div>
          </ChoiceSection>
          <ChoiceSection title="Pace">
            <ChoicePills>
              {(["relaxed", "balanced", "packed"] as const).map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.travel.pace === item}
                  onClick={() => setProfile({ ...profile, travel: { ...profile.travel, pace: item } })}
                >
                  {labelOf(item)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection>
            <ChoiceRow
              pressed={profile.sleep.jet_lag_buffer}
              onClick={() => setProfile({ ...profile, sleep: { ...profile.sleep, jet_lag_buffer: !profile.sleep.jet_lag_buffer } })}
            >
              Go easy on day 1 after long flights
            </ChoiceRow>
          </ChoiceSection>
        </>
      )}
      {step === 4 && (
        <>
          <ChoiceSection>
            <ChoicePills>
              {["walk", "bike", "transit", "taxi"].map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.travel.preferred_modes.includes(item as "walk")}
                  onClick={() => setProfile({ ...profile, travel: { ...profile.travel, preferred_modes: toggle(profile.travel.preferred_modes, item) as UserProfile["travel"]["preferred_modes"] } })}
                >
                  {labelOf(item)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection>
            <ChoiceField label="Avoid" value={avoid} placeholder="crowds, long walks" onChange={(event) => setAvoid(event.target.value)} />
            <div style={{ marginTop: 16 }}>
              <ChoiceField
                label="Accessibility"
                value={profile.travel.accessibility.join(", ")}
                onChange={(event) => setProfile({ ...profile, travel: { ...profile.travel, accessibility: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })}
              />
            </div>
          </ChoiceSection>
        </>
      )}
      {step === 5 && (
        <>
          <ChoiceSection>
            <ChoicePills>
              {BRANDS.map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.hotels.favourite_brands.includes(item)}
                  onClick={() => setProfile({ ...profile, hotels: { ...profile.hotels, favourite_brands: toggle(profile.hotels.favourite_brands, item) } })}
                >
                  {labelOf(item)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection>
            <ChoiceField label="Loyalty programme" value={loyaltyHotel} onChange={(event) => setLoyaltyHotel(event.target.value)} placeholder="World of Hyatt" />
          </ChoiceSection>
        </>
      )}
      {step === 6 && (
        <>
          <ChoiceSection>
            <ChoicePills>
              {AIRLINES.map((item) => (
                <ChoicePill
                  key={item}
                  pressed={profile.flights.favourite_airlines.includes(item)}
                  onClick={() => setProfile({ ...profile, flights: { ...profile.flights, favourite_airlines: toggle(profile.flights.favourite_airlines, item) } })}
                >
                  {item}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection>
            <ChoiceStack>
              <ChoiceRow
                pressed={profile.flights.avoid_red_eye}
                onClick={() => setProfile({ ...profile, flights: { ...profile.flights, avoid_red_eye: !profile.flights.avoid_red_eye } })}
              >
                Avoid red-eyes
              </ChoiceRow>
            </ChoiceStack>
          </ChoiceSection>
          <ChoiceSection>
            <ChoiceField label="Airline loyalty" value={loyaltyAir} onChange={(event) => setLoyaltyAir(event.target.value)} placeholder="JAL Mileage Bank" />
          </ChoiceSection>
        </>
      )}
      {step === 7 && (
        <>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <ChoiceSection key={key} title={labelOf(key)}>
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
      {step === 8 && (
        <ChoiceSection>
          <ChoiceSummary>{profile.home.address || "Home"}</ChoiceSummary>
          <ChoiceNote>{profile.travel.interests.join(", ") || "open interests"} · wake {profile.sleep.wake_time}</ChoiceNote>
        </ChoiceSection>
      )}
    </ChoiceFlow>
  );
}
