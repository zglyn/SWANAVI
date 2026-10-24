"use client";

import type { AmountLevel, AttractionSelection, Candidate } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { SwanShell, phasePath } from "@/components/swan/Shell";
import candidatesFx from "@fixtures/candidates_kyoto.json";
import { getClient } from "@/lib/client";

const LEVELS: AmountLevel[] = ["none", "a_little", "some", "lots"];
const LEVEL_LABEL = ["none", "a little", "some", "lots"];

export default function AttractionsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const candidates = (candidatesFx as { candidates: Candidate[] }).candidates;
  const [mode, setMode] = useState<"choose" | null>(null);
  const [picks, setPicks] = useState<Record<string, "must" | "nice" | "skip">>({});
  const [amounts, setAmounts] = useState<Record<string, number>>({ food: 3, temples: 2, museums: 1 });
  const [density, setDensity] = useState<"light" | "balanced" | "packed">("balanced");

  const categories = [...new Set(candidates.map((item) => item.attraction?.category || item.merchant?.category).filter(Boolean))] as string[];
  const musts = Object.values(picks).filter((item) => item === "must").length;

  async function send(selection: AttractionSelection) {
    const result = await client.submitAttractions(params.id, selection);
    router.push(phasePath(params.id, result.phase));
  }

  if (mode !== "choose") {
    return (
      <SwanShell>
        <h1 className="text-5xl">Attractions</h1>
        <button type="button" className="swan-btn mt-6 w-full" onClick={() => send({ mode: "swan_decides", picks: [], amounts: [], daily_density: density, must_visit: [], maybe: [], excluded: [] })}>Let Swan decide</button>
        <button type="button" className="swan-btn-ghost mt-3 w-full" onClick={() => setMode("choose")}>I&apos;ll choose</button>
      </SwanShell>
    );
  }

  return (
    <SwanShell>
      <h1 className="text-4xl">What do you want?</h1>
      <p className="mt-3" aria-live="polite">{musts} must-sees picked · Swan will fill the rest, heavy on food.</p>
      <div className="mt-4 space-y-3">
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
      <div className="mt-4 flex gap-2">
        {(["light", "balanced", "packed"] as const).map((item) => (
          <button key={item} type="button" className="swan-chip" aria-pressed={density === item} onClick={() => setDensity(item)}>{item}</button>
        ))}
      </div>
      <ul className="mt-4 space-y-3">
        {candidates.slice(0, 12).map((item) => {
          const title = item.attraction?.name || item.merchant?.name || item.id;
          return (
            <li key={item.id} className="swan-line rounded-2xl border p-3">
              <p className={`font-medium ${picks[item.id] === "skip" ? "line-through opacity-60" : ""}`}>{title}</p>
              <div className="mt-2 flex gap-2">
                {(["must", "nice", "skip"] as const).map((bucket) => (
                  <button key={bucket} type="button" className="swan-chip" aria-pressed={(picks[item.id] ?? "nice") === bucket} onClick={() => setPicks({ ...picks, [item.id]: bucket })}>
                    {bucket === "must" ? "Must" : bucket === "nice" ? "Nice to have" : "Skip"}
                  </button>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        className="swan-btn mt-6"
        onClick={() => send({
          mode: "i_choose",
          picks: Object.entries(picks).flatMap(([candidate_id, priority]) => priority === "skip" ? [] : [{ candidate_id, priority }]),
          amounts: Object.entries(amounts).map(([category, level]) => ({ category, level: LEVELS[level] })),
          daily_density: density,
          must_visit: Object.entries(picks).filter(([, bucket]) => bucket === "must").map(([id]) => id),
          maybe: Object.entries(picks).filter(([, bucket]) => bucket === "nice").map(([id]) => id),
          excluded: Object.entries(picks).filter(([, bucket]) => bucket === "skip").map(([id]) => id),
        })}
      >
        Continue
      </button>
    </SwanShell>
  );
}
