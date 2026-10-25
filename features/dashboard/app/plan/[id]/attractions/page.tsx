"use client";

import type { AmountLevel, AttractionSelection, Candidate, TripRequest, UserProfile } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ChoiceCard,
  ChoiceFlow,
  ChoiceNote,
  ChoicePill,
  ChoicePills,
  ChoiceRow,
  ChoiceSection,
  ChoiceSlider,
  ChoiceStack,
  ChoiceSub,
} from "@/components/choice/ChoiceFlow";
import { planningPath } from "@/components/swan/Shell";
import candidatesFx from "@fixtures/candidates_kyoto.json";
import { getClient } from "@/lib/client";
import { formatDateRange, nightsBetween } from "@/lib/format";

const LEVELS: AmountLevel[] = ["none", "a_little", "some", "lots"];
const LEVEL_LABEL = ["none", "a little", "some", "lots"];
const PER_DAY = { light: 2, balanced: 3, packed: 4 } as const;

function titleOf(item: Candidate) {
  return item.attraction?.name || item.quote?.title || item.merchant?.name || item.id;
}

function categoryOf(item: Candidate) {
  return (item.attraction?.category || item.merchant?.category || "").toLowerCase();
}

function rankForProfile(candidates: Candidate[], profile: UserProfile | null): Candidate[] {
  const interests = new Set((profile?.travel.interests ?? []).map((item) => item.toLowerCase()));
  const avoid = (profile?.travel.avoid ?? []).map((item) => item.toLowerCase());
  const score = (item: Candidate) => {
    const text = `${titleOf(item)} ${item.attraction?.description ?? ""} ${categoryOf(item)}`.toLowerCase();
    if (avoid.some((tag) => text.includes(tag))) return -100;
    return (interests.has(categoryOf(item)) ? 10 : 0) + (item.attraction?.popularity ?? 0) / 10;
  };
  return [...candidates].sort((a, b) => score(b) - score(a));
}

export default function AttractionsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const candidates = (candidatesFx as { candidates: Candidate[] }).candidates;
  const [request, setRequest] = useState<TripRequest | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [density, setDensity] = useState<"light" | "balanced" | "packed">("balanced");
  const [kept, setKept] = useState<string[] | null>(null);
  const [swapped, setSwapped] = useState<string[]>([]);
  const [amounts, setAmounts] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([client.getSwan(params.id), client.getProfile()])
      .then(([view, found]) => {
        setRequest(view.request);
        setProfile(found);
      })
      .catch(() => setRequest(null));
  }, [client, params.id]);

  const ranked = useMemo(() => rankForProfile(candidates, profile), [candidates, profile]);
  const days = request ? nightsBetween(request.start_date, request.end_date) : 2;
  const cap = Math.max(1, days) * PER_DAY[density];
  const picks = kept ?? ranked.slice(0, cap).map((item) => item.id);
  const byId = new Map(candidates.map((item) => [item.id, item]));
  const bench = ranked.filter((item) => !picks.includes(item.id) && !swapped.includes(item.id));
  const categories = [...new Set(candidates.map(categoryOf).filter(Boolean))];

  function swap(id: string) {
    const replacement = bench[0];
    setSwapped([...swapped, id]);
    setKept(picks.flatMap((item) => (item === id ? (replacement ? [replacement.id] : []) : [item])));
  }

  function remove(id: string) {
    setKept(picks.filter((item) => item !== id));
  }

  function addMore() {
    const extra = bench.slice(0, 2).map((item) => item.id);
    if (extra.length) setKept([...picks, ...extra]);
  }

  async function send(selection: AttractionSelection) {
    if (busy) return;
    setBusy(true);
    try {
      const result = await client.submitAttractions(params.id, selection);
      router.push(planningPath(params.id, result.phase));
    } finally {
      setBusy(false);
    }
  }

  const letSwan = () => send({ mode: "swan_decides", picks: [], amounts: [], daily_density: density, must_visit: [], maybe: [], excluded: [] });
  const useThese = () => send({
    mode: "i_choose",
    picks: picks.map((candidate_id) => ({ candidate_id, priority: "must" as const })),
    amounts: Object.entries(amounts).map(([category, level]) => ({ category, level: LEVELS[level] })),
    daily_density: density,
    must_visit: picks,
    maybe: [],
    excluded: swapped,
  });

  return (
    <ChoiceFlow
      title="Swanavi's picks for you"
      action={busy ? "Saving…" : `Use these ${picks.length} picks`}
      onAction={useThese}
      actionDisabled={busy || !picks.length}
    >
      <ChoiceNote>
        {request?.destination ?? "Your trip"}
        {request ? ` · ${formatDateRange(request.start_date, request.end_date)}` : ""}
        {" · "}
        Based on {profile?.travel.interests.length ? profile.travel.interests.join(" and ") : "what Kyoto does best"}.
        {" "}
        {picks.length} places over {days + 1} days.
      </ChoiceNote>
      <ChoiceSection>
        <ChoiceRow pressed={false} onClick={letSwan}>
          Let Swanavi decide
        </ChoiceRow>
      </ChoiceSection>
      <ChoiceSection title="Pace">
        <ChoicePills>
          {(["light", "balanced", "packed"] as const).map((item) => (
            <ChoicePill key={item} pressed={density === item} onClick={() => { setDensity(item); setKept(null); setSwapped([]); }}>
              {item[0].toUpperCase() + item.slice(1)}
            </ChoicePill>
          ))}
        </ChoicePills>
        <ChoiceNote>{PER_DAY[density]} places a day</ChoiceNote>
      </ChoiceSection>
      <ChoiceSection title="Places">
        <ChoiceStack as="ul">
          {picks.map((id) => {
            const item = byId.get(id);
            if (!item) return null;
            const title = titleOf(item);
            return (
              <li key={id}>
                <ChoiceCard>
                  <p className="font-medium">{title}</p>
                  <ChoiceSub>
                    {categoryOf(item)}
                    {item.attraction?.area ? ` · ${item.attraction.area}` : ""}
                    {item.attraction ? ` · ${item.attraction.typical_duration_min} min` : ""}
                    {item.merchant ? " · Wallet" : ""}
                  </ChoiceSub>
                  <div style={{ marginTop: 12 }}>
                    <ChoicePills>
                      <ChoicePill pressed onClick={() => undefined}>Kept</ChoicePill>
                      <ChoicePill pressed={false} onClick={() => swap(id)}>Swap</ChoicePill>
                      <ChoicePill pressed={false} onClick={() => remove(id)}>Remove</ChoicePill>
                    </ChoicePills>
                  </div>
                </ChoiceCard>
              </li>
            );
          })}
        </ChoiceStack>
        <div style={{ marginTop: 12 }}>
          <ChoiceRow pressed={false} onClick={addMore}>Add more</ChoiceRow>
        </div>
      </ChoiceSection>
      <ChoiceSection title="How much of each">
        <ChoiceStack>
          {categories.map((category) => (
            <ChoiceSlider
              key={category}
              label={category}
              valueLabel={LEVEL_LABEL[amounts[category] ?? 2]}
              min={0}
              max={3}
              step={1}
              value={amounts[category] ?? 2}
              aria-valuetext={LEVEL_LABEL[amounts[category] ?? 2]}
              onChange={(event) => setAmounts({ ...amounts, [category]: Number(event.target.value) })}
            />
          ))}
        </ChoiceStack>
      </ChoiceSection>
    </ChoiceFlow>
  );
}
