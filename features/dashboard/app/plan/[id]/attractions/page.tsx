"use client";

import type { AmountLevel, AttractionSelection, Candidate, TripRequest, UserProfile } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { SwanShell, planningPath } from "@/components/swan/Shell";
import { Photo } from "@/components/swan/Photo";
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

  const summary = request ? (
    <div>
      <p className="swan-eyebrow">Trip</p>
      <p className="mt-2 text-xl font-bold tracking-tight">{request.destination}</p>
      <p className="swan-muted text-sm">{formatDateRange(request.start_date, request.end_date)} · {days} night{days === 1 ? "" : "s"}</p>
      <p className="mt-4 text-sm">{picks.length} places over {days + 1} days. Swanavi routes them, books the local ones from your wallet, and keeps the first day light after the flight.</p>
    </div>
  ) : null;

  return (
    <SwanShell aside={summary}>
      <p className="swan-eyebrow">{request?.destination ?? "Your trip"}{request ? ` · ${formatDateRange(request.start_date, request.end_date)}` : ""}</p>
      <h1 className="mt-2 text-4xl sm:text-5xl">Swanavi&apos;s picks for you</h1>
      <p className="swan-muted mt-3">
        Based on {profile?.travel.interests.length ? profile.travel.interests.join(" and ") : "what Kyoto does best"}. Keep what you like, swap what you don&apos;t, or let Swanavi decide.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <div className="swan-seg" role="radiogroup" aria-label="Daily pace">
          {(["light", "balanced", "packed"] as const).map((item) => (
            <button key={item} type="button" role="radio" aria-checked={density === item} onClick={() => { setDensity(item); setKept(null); setSwapped([]); }}>
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>
        <span className="swan-muted text-sm">{PER_DAY[density]} places a day</span>
      </div>

      <ul className="mt-6 grid gap-3 sm:grid-cols-2" aria-live="polite">
        {picks.map((id) => {
          const item = byId.get(id);
          if (!item) return null;
          const title = titleOf(item);
          return (
            <li key={id} className="swan-card overflow-hidden">
              <Photo src={item.attraction?.image_url} alt={title} label={title} className="h-24 w-full sm:h-32" />
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold">{title}</p>
                  {item.merchant ? <span className="swan-badge swan-badge-solid shrink-0">Wallet</span> : null}
                </div>
                <p className="swan-muted mt-1 text-sm capitalize">
                  {categoryOf(item)}{item.attraction?.area ? ` · ${item.attraction.area}` : ""}{item.attraction ? ` · ${item.attraction.typical_duration_min} min` : ""}
                </p>
                <div className="mt-3 flex gap-2">
                  <span className="swan-badge">Kept</span>
                  <button type="button" className="swan-filter" onClick={() => swap(id)} disabled={!bench.length} aria-label={`Swap ${title}`}>Swap</button>
                  <button type="button" className="swan-filter" onClick={() => remove(id)} aria-label={`Remove ${title}`}>Remove</button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <button type="button" className="swan-btn-ghost mt-4" onClick={addMore} disabled={!bench.length}>Add more</button>

      <details className="mt-6">
        <summary className="cursor-pointer font-medium">Fine-tune how much of each</summary>
        <div className="mt-3 space-y-3">
          {categories.map((category) => (
            <label key={category} className="block">
              <span className="flex justify-between text-sm"><span className="capitalize">{category}</span><span>{LEVEL_LABEL[amounts[category] ?? 2]}</span></span>
              <input
                type="range"
                min={0}
                max={3}
                step={1}
                value={amounts[category] ?? 2}
                aria-valuetext={LEVEL_LABEL[amounts[category] ?? 2]}
                onChange={(event) => setAmounts({ ...amounts, [category]: Number(event.target.value) })}
                className="mt-2 w-full"
              />
            </label>
          ))}
        </div>
      </details>

      <div className="swan-sticky mt-8 -mx-4 flex flex-wrap items-center gap-3 px-4 py-4 sm:-mx-6 sm:px-6">
        <button type="button" className="swan-btn" onClick={letSwan} disabled={busy}>Let Swanavi decide</button>
        <button type="button" className="swan-btn-ghost" onClick={useThese} disabled={busy || !picks.length}>Use these {picks.length} picks</button>
      </div>
    </SwanShell>
  );
}
