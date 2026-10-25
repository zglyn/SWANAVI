"use client";

import type { AmountLevel, AttractionSelection, Candidate } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
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
  choiceName,
} from "@/components/choice/ChoiceFlow";
import { phasePath } from "@/components/swan/Shell";
import candidatesFx from "@fixtures/candidates_kyoto.json";
import { getClient } from "@/lib/client";

const LEVELS: AmountLevel[] = ["none", "a_little", "some", "lots"];
const LEVEL_LABEL = ["none", "a little", "some", "lots"];

export default function AttractionsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const candidates = (candidatesFx as { candidates: Candidate[] }).candidates;
  const [mode, setMode] = useState<"swan_decides" | "i_choose" | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [picks, setPicks] = useState<Record<string, "must" | "nice" | "skip">>({});
  const [amounts, setAmounts] = useState<Record<string, number>>({ food: 3, temples: 2, museums: 1 });
  const [density, setDensity] = useState<"light" | "balanced" | "packed">("balanced");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const categories = [...new Set(candidates.map((item) => item.attraction?.category || item.merchant?.category).filter(Boolean))] as string[];
  const musts = Object.values(picks).filter((item) => item === "must").length;

  async function send(selection: AttractionSelection) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await client.submitAttractions(params.id, selection);
      router.push(phasePath(params.id, result.phase));
    } catch {
      setError("Could not save these places. Try again.");
      setBusy(false);
    }
  }

  if (!choosing) {
    return (
      <ChoiceFlow
        title="Who picks the places?"
        action="Continue"
        actionDisabled={busy || !mode}
        onAction={() => {
          if (mode === "swan_decides") {
            void send({ mode: "swan_decides", picks: [], amounts: [], daily_density: density, must_visit: [], maybe: [], excluded: [] });
          } else if (mode === "i_choose") {
            setChoosing(true);
          }
        }}
      >
        <ChoiceSection>
          <ChoiceStack>
            <ChoiceRow pressed={mode === "swan_decides"} onClick={() => setMode("swan_decides")}>
              Let Swanavi decide
            </ChoiceRow>
            <ChoiceRow pressed={mode === "i_choose"} onClick={() => setMode("i_choose")}>
              I&apos;ll choose
            </ChoiceRow>
          </ChoiceStack>
          {error ? <ChoiceNote>{error}</ChoiceNote> : null}
        </ChoiceSection>
      </ChoiceFlow>
    );
  }

  return (
    <ChoiceFlow
      title="What do you want?"
      action="Continue"
      actionDisabled={busy}
      onBack={() => setChoosing(false)}
      onAction={() => send({
        mode: "i_choose",
        picks: Object.entries(picks).flatMap(([candidate_id, priority]) => priority === "skip" ? [] : [{ candidate_id, priority }]),
        amounts: Object.entries(amounts).map(([category, level]) => ({ category, level: LEVELS[level] })),
        daily_density: density,
        must_visit: Object.entries(picks).filter(([, bucket]) => bucket === "must").map(([id]) => id),
        maybe: Object.entries(picks).filter(([, bucket]) => bucket === "nice").map(([id]) => id),
        excluded: Object.entries(picks).filter(([, bucket]) => bucket === "skip").map(([id]) => id),
      })}
    >
      <ChoiceNote live>{musts} must-sees picked · Swanavi will fill the rest, heavy on food.</ChoiceNote>
      <ChoiceSection title="How much">
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
      <ChoiceSection title="Pace">
        <ChoicePills>
          {(["light", "balanced", "packed"] as const).map((item) => (
            <ChoicePill key={item} pressed={density === item} onClick={() => setDensity(item)}>
              {item.charAt(0).toUpperCase() + item.slice(1)}
            </ChoicePill>
          ))}
        </ChoicePills>
      </ChoiceSection>
      <ChoiceSection title="Places">
        <ChoiceStack as="ul">
          {candidates.slice(0, 12).map((item) => {
            const title = item.attraction?.name || item.merchant?.name || item.id;
            const bucket = picks[item.id] ?? "nice";
            return (
              <li key={item.id}>
                <ChoiceCard>
                  <p className={choiceName(bucket === "skip")}>{title}</p>
                  <div style={{ marginTop: 12 }}>
                    <ChoicePills>
                      {(["must", "nice", "skip"] as const).map((choice) => (
                        <ChoicePill key={choice} pressed={bucket === choice} onClick={() => setPicks({ ...picks, [item.id]: choice })}>
                          {choice === "must" ? "Must" : choice === "nice" ? "Nice to have" : "Skip"}
                        </ChoicePill>
                      ))}
                    </ChoicePills>
                  </div>
                </ChoiceCard>
              </li>
            );
          })}
        </ChoiceStack>
      </ChoiceSection>
      {error ? <ChoiceNote>{error}</ChoiceNote> : null}
    </ChoiceFlow>
  );
}
