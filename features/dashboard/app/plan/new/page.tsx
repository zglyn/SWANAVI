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
import { planningPath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { formatDateRange, formatMoney, nightsBetween } from "@/lib/format";
import { DESTINATIONS, lookupPlace } from "@/lib/places";

const WINDOWS: TimeOfDayWindow[] = ["early_morning", "morning", "afternoon", "evening", "red_eye", "any"];
const WINDOW_LABEL: Record<TimeOfDayWindow, string> = {
  early_morning: "Early morning",
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
  red_eye: "Red-eye",
  any: "Any time",
};
const DRAFT = "swan.trip-draft";
const STEPS = 6;

function Planner() {
  const router = useRouter();
  const params = useSearchParams();
  const step = Math.min(STEPS, Math.max(1, Number(params.get("step") || "1")));
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [draft, setDraft] = useState<TripRequest | null>(null);
  const [query, setQuery] = useState("Kyoto");
  const [originQuery, setOriginQuery] = useState("");
  const [busy, setBusy] = useState(false);

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
    try {
      const created = await client.requestTrip(draft);
      sessionStorage.removeItem(DRAFT);
      router.push(planningPath(created.plan_id, created.phase));
    } finally {
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
  const originLabel = draft.origin.from_home
    ? `Home · ${(profile?.home.airport_codes ?? draft.origin.airport_codes).join(" · ")}`
    : `${draft.origin.place ?? ""} · ${draft.origin.airport_codes.join(" · ")}`;
  const nights = nightsBetween(draft.start_date, draft.end_date);
  const title = step === 1 ? "Where to?"
    : step === 2 ? "From where?"
      : step === 3 ? "When?"
        : step === 4 ? "What time do you want to fly?"
          : step === 5 ? "How much should Swanavi handle?"
            : "Confirm";

  return (
    <ChoiceFlow
      title={title}
      step={step}
      steps={STEPS}
      action={step === STEPS ? (busy ? "Starting…" : "Confirm") : "Continue"}
      onAction={step === STEPS ? confirm : () => go(step + 1)}
      actionDisabled={step === STEPS && busy}
      onBack={step > 1 ? () => go(step - 1) : undefined}
    >
      {step === 1 && (
        <ChoiceSection>
          <ChoiceField
            aria-label="Destination"
            placeholder="City"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <ChoiceStack as="ul" >
            {matches.map((city) => {
              const value = ["London", "Paris", "New York", "Los Angeles"].includes(city.label) ? city.label : `${city.label}, Japan`;
              return (
                <li key={city.label}>
                  <ChoiceRow
                    pressed={draft.destination === value}
                    onClick={() => { setDraft({ ...draft, destination: value }); setQuery(city.label); }}
                  >
                    {city.label}
                  </ChoiceRow>
                </li>
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
              <ChoiceSub>{(profile?.home.airport_codes ?? []).join(", ") || "your home airports"}</ChoiceSub>
            </ChoiceRow>
            <ChoiceRow
              pressed={!draft.origin.from_home}
              onClick={() => setDraft({ ...draft, origin: { from_home: false, place: draft.origin.place, airport_codes: draft.origin.from_home ? [] : draft.origin.airport_codes } })}
            >
              Somewhere else
            </ChoiceRow>
          </ChoiceStack>
          {!draft.origin.from_home ? (
            <div style={{ marginTop: 16 }}>
              <ChoiceField
                label="City or address"
                aria-label="Other origin"
                value={originQuery}
                onChange={(event) => setOriginQuery(event.target.value)}
                onBlur={async () => {
                  const hit = await lookupPlace(originQuery);
                  if (!hit) return;
                  setDraft({ ...draft, origin: { from_home: false, place: hit.label, airport_codes: hit.airports } });
                }}
              />
              {draft.origin.place ? <ChoiceNote>{draft.origin.place} · {draft.origin.airport_codes.join(" · ")}</ChoiceNote> : null}
            </div>
          ) : null}
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
              onChange={(event) => setDraft({ ...draft, travellers: Math.max(1, Number(event.target.value)) })}
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
                  {WINDOW_LABEL[item]}
                </ChoicePill>
              ))}
            </ChoicePills>
          </ChoiceSection>
          <ChoiceSection title="Return">
            <ChoicePills>
              {windows.map((item) => (
                <ChoicePill key={item} pressed={draft.return_window === item} onClick={() => setDraft({ ...draft, return_window: item })}>
                  {WINDOW_LABEL[item]}
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
            <ChoiceField
              label="Budget for the whole trip"
              inputMode="decimal"
              value={draft.budget ?? ""}
              onChange={(event) => setDraft({ ...draft, budget: event.target.value })}
            />
          </ChoiceSection>
        </>
      )}
      {step === 6 && (
        <ChoiceSection>
          <ChoiceSummary>{draft.destination}</ChoiceSummary>
          <ChoiceNote>
            {formatDateRange(draft.start_date, draft.end_date)} · {nights} night{nights === 1 ? "" : "s"} · {draft.travellers} traveller{draft.travellers === 1 ? "" : "s"}
          </ChoiceNote>
          <ChoiceNote>
            Fly {WINDOW_LABEL[draft.outbound_window].toLowerCase()} out, {WINDOW_LABEL[draft.return_window].toLowerCase()} back.
          </ChoiceNote>
          <ChoiceNote>From {originLabel}.</ChoiceNote>
          <ChoiceNote>Budget {draft.budget ? formatMoney(draft.budget, "USD") : "Open"}</ChoiceNote>
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
