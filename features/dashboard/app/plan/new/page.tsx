"use client";

import type { Autonomy, TimeOfDayWindow, TripRequest, UserProfile } from "@contracts/api";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import {
  ChoiceField,
  ChoiceFlow,
  ChoiceNote,
  ChoicePill,
  ChoicePills,
  ChoiceRow,
  ChoiceSection,
  ChoiceStack,
  ChoiceSub,
  ChoiceSummary,
} from "@/components/choice/ChoiceFlow";
import { phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { DESTINATIONS, lookupPlace } from "@/lib/places";

const WINDOWS: TimeOfDayWindow[] = ["early_morning", "morning", "afternoon", "evening", "red_eye", "any"];
const DRAFT = "swan.trip-draft";

function windowLabel(value: string) {
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Planner() {
  const router = useRouter();
  const params = useSearchParams();
  const step = Number(params.get("step") || "1");
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [draft, setDraft] = useState<TripRequest | null>(null);
  const [query, setQuery] = useState("Kyoto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setError(null);
    try {
      const created = await client.requestTrip(draft);
      sessionStorage.removeItem(DRAFT);
      router.push(phasePath(created.plan_id, created.phase));
    } catch {
      setError("Could not send this trip. Try again.");
      setBusy(false);
    }
  }

  if (!draft) {
    return (
      <ChoiceFlow title="Where to?">
        <ChoiceNote>Loading your profile…</ChoiceNote>
      </ChoiceFlow>
    );
  }

  const windows = WINDOWS.filter((item) => item !== "red_eye" || !profile?.flights.avoid_red_eye);
  const matches = DESTINATIONS.filter((city) => city.label.toLowerCase().includes(query.toLowerCase()));
  const back = step > 1 ? () => go(step - 1) : undefined;

  return (
    <ChoiceFlow
      title={
        step === 1 ? "Where to?"
          : step === 2 ? "From where?"
            : step === 3 ? "When?"
              : step === 4 ? "What time do you want to fly?"
                : step === 5 ? "How much should Swanavi handle?"
                  : "Confirm"
      }
      step={step}
      steps={6}
      action={step === 6 ? "Confirm" : "Continue"}
      onAction={step === 6 ? confirm : () => go(step + 1)}
      actionDisabled={step === 6 && busy}
      onBack={back}
    >
      {step === 1 && (
        <ChoiceSection>
          <ChoiceField
            aria-label="Destination"
            placeholder="Search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <ChoiceStack>
            {matches.map((city) => {
              const destination = ["London", "Paris", "New York", "Los Angeles"].includes(city.label) ? city.label : `${city.label}, Japan`;
              const selected = draft.destination === destination || draft.destination.toLowerCase().startsWith(city.label.toLowerCase());
              return (
                <ChoiceRow
                  key={city.label}
                  pressed={selected}
                  onClick={() => {
                    setDraft({ ...draft, destination });
                    setQuery(city.label);
                  }}
                >
                  {city.label}
                </ChoiceRow>
              );
            })}
          </ChoiceStack>
          <ChoiceNote>Going to {draft.destination}</ChoiceNote>
        </ChoiceSection>
      )}
      {step === 2 && (
        <ChoiceSection>
          <ChoiceStack>
            <ChoiceRow
              pressed={draft.origin.from_home}
              onClick={() => setDraft({ ...draft, origin: { from_home: true, place: null, airport_codes: profile?.home.airport_codes ?? [] } })}
            >
              From home
              {profile?.home.airport_codes.length ? <ChoiceSub>{profile.home.airport_codes.join(" · ")}</ChoiceSub> : null}
            </ChoiceRow>
          </ChoiceStack>
          <div style={{ marginTop: 20 }}>
            <ChoiceField
              label="Somewhere else"
              aria-label="Other origin"
              placeholder="City or address"
              onBlur={async (event) => {
                const hit = await lookupPlace(event.target.value);
                if (!hit) return;
                setDraft({ ...draft, origin: { from_home: false, place: hit.label, airport_codes: hit.airports } });
              }}
            />
            {!draft.origin.from_home && draft.origin.place ? (
              <ChoiceNote>{draft.origin.place}{draft.origin.airport_codes.length ? ` · ${draft.origin.airport_codes.join(" · ")}` : ""}</ChoiceNote>
            ) : null}
          </div>
        </ChoiceSection>
      )}
      {step === 3 && (
        <ChoiceSection>
          <ChoiceField label="Arrive" type="date" value={draft.start_date} onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} />
          <div style={{ marginTop: 16 }}>
            <ChoiceField label="Leave" type="date" value={draft.end_date} onChange={(event) => setDraft({ ...draft, end_date: event.target.value })} />
          </div>
          <div style={{ marginTop: 16 }}>
            <ChoiceField
              label="Travellers"
              type="number"
              min={1}
              value={draft.travellers}
              onChange={(event) => setDraft({ ...draft, travellers: Number(event.target.value) })}
            />
          </div>
        </ChoiceSection>
      )}
      {step === 4 && (
        <>
          <ChoiceSection title="Outbound">
            <ChoicePills>
              {windows.map((item) => (
                <ChoicePill key={item} pressed={draft.outbound_window === item} onClick={() => setDraft({ ...draft, outbound_window: item })}>
                  {windowLabel(item)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection title="Return">
            <ChoicePills>
              {windows.map((item) => (
                <ChoicePill key={item} pressed={draft.return_window === item} onClick={() => setDraft({ ...draft, return_window: item })}>
                  {windowLabel(item)}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
        </>
      )}
      {step === 5 && (
        <>
          {(["attractions", "hotels", "flights"] as const).map((key) => (
            <ChoiceSection key={key} title={key.charAt(0).toUpperCase() + key.slice(1)}>
              <ChoicePills>
                {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                  <ChoicePill
                    key={item}
                    pressed={draft.autonomy[key] === item}
                    onClick={() => setDraft({ ...draft, autonomy: { ...draft.autonomy, [key]: item } })}
                  >
                    {item === "swan_decides" ? "Swanavi decides" : "I choose"}
                  </ChoicePill>
                ))}
              </ChoicePills>
            </ChoiceSection>
          ))}
          <ChoiceSection>
            <ChoiceField label="Budget" value={draft.budget ?? ""} onChange={(event) => setDraft({ ...draft, budget: event.target.value })} />
          </ChoiceSection>
        </>
      )}
      {step === 6 && (
        <ChoiceSection>
          <ChoiceSummary>{draft.destination}</ChoiceSummary>
          <ChoiceNote>
            {draft.start_date} to {draft.end_date} · {draft.travellers} traveller{draft.travellers === 1 ? "" : "s"}
          </ChoiceNote>
          <ChoiceNote>
            Fly {draft.outbound_window.replace("_", " ")} out, {draft.return_window.replace("_", " ")} back.
          </ChoiceNote>
          <ChoiceNote>
            {draft.origin.from_home ? "From home" : draft.origin.place || "From somewhere else"}
            {draft.origin.airport_codes.length ? ` · ${draft.origin.airport_codes.join(" · ")}` : ""}
          </ChoiceNote>
          {draft.budget ? <ChoiceNote>Budget {draft.budget}</ChoiceNote> : null}
          {error ? <ChoiceNote>{error}</ChoiceNote> : null}
        </ChoiceSection>
      )}
    </ChoiceFlow>
  );
}

export default function PlanNewPage() {
  return (
    <Suspense fallback={<ChoiceFlow title="Where to?"><ChoiceNote>Loading…</ChoiceNote></ChoiceFlow>}>
      <Planner />
    </Suspense>
  );
}
