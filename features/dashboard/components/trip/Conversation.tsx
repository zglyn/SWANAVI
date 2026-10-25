"use client";

import type { Control } from "@contracts/api";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { TRIP_MESSAGE_KEY } from "@/lib/tripDraft";
import { demoCity } from "@/lib/demoScope";
import {
  advanceStream,
  answerControl,
  begin,
  commitAnswers,
  controlsReady,
  demoScript,
  editFact,
  factChips,
  missingFacts,
  planNow,
  type PlayState,
} from "@/lib/conversationPlay";

const TripMap = dynamic(() => import("@/components/map3d/TripMap").then((mod) => mod.TripMap), { ssr: false });

const PROGRESS = [
  `Finding flights from ${demoCity.origin.code}…`,
  "Choosing a hotel near your picks…",
  "Building day 2…",
];

export function Conversation({ tripId, onProposal }: { tripId: string; onProposal: () => void }) {
  const script = demoScript().messages;
  const [state, setState] = useState<PlayState | null>(null);
  const [draft, setDraft] = useState("");
  const [progress, setProgress] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const live = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opening = sessionStorage.getItem(TRIP_MESSAGE_KEY) ?? "";
    setState(begin(script, opening));
  }, [script]);

  useEffect(() => {
    if (!state || state.mode !== "stream") return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setState((current) => current && advanceStream(current, script, true));
      return;
    }
    const id = window.setInterval(() => {
      setState((current) => current && current.mode === "stream" ? advanceStream(current, script, false) : current);
    }, 40);
    return () => window.clearInterval(id);
  }, [state?.mode, state?.cursor, script]);

  useEffect(() => {
    if (state?.mode !== "planning") return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;
    const id = window.setInterval(() => setProgress((index) => (index + 1) % PROGRESS.length), 1200);
    return () => window.clearInterval(id);
  }, [state?.mode]);

  useEffect(() => {
    live.current?.scrollTo({ top: live.current.scrollHeight });
  }, [state?.messages.length, state?.shown]);

  if (!state) return null;
  const chips = factChips(state.brief);
  const asking = state.messages[state.messages.length - 1];
  const canPlan = state.mode === "offer" && missingFacts(state.brief).length === 0;

  function choose(control: Control, value: string | number) {
    setState((current) => {
      if (!current || current.mode !== "ask") return current;
      const next = answerControl(current, control, value);
      return controlsReady(next) ? commitAnswers(next, script) : next;
    });
  }

  function sendText(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const people = trimmed.match(/\b([1-4])\b/);
    const money = trimmed.match(/\$?\s*([\d,]+)/);
    setState((current) => {
      if (!current || current.mode === "planning") return current;
      if (current.mode !== "ask") {
        return {
          ...current,
          messages: [...current.messages, { id: `local-${current.messages.length}`, role: "user", text: trimmed, controls: [], created_at: new Date().toISOString() }],
        };
      }
      let next = current;
      if (people) next = answerControl(next, { slot: "travellers", type: "chips" }, people[1]);
      if (money) next = answerControl(next, { slot: "budget", type: "slider" }, Number(money[1].replace(/,/g, "")));
      if (controlsReady(next)) return commitAnswers(next, script);
      return {
        ...next,
        messages: [...next.messages, { id: `local-${next.messages.length}`, role: "user", text: trimmed, controls: [], created_at: new Date().toISOString() }],
      };
    });
    setDraft("");
  }

  return (
    <div className="convo">
      <header className="home-bar">
        <Link href="/" className="home-brand">Swanavi</Link>
        <p className="swan-muted">Trip {tripId}</p>
      </header>
      <div className="convo-brief" aria-label="Trip brief">
        {chips.map((chip) => (
          editing === chip.id ? (
            <input
              key={chip.id}
              className="convo-fact"
              aria-label={`Edit ${chip.id}`}
              defaultValue={chip.known ? chip.label : ""}
              autoFocus
              onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                const value = event.currentTarget.value;
                setState((current) => current && ({ ...current, brief: editFact(current.brief, chip.id, value) }));
                setEditing(null);
              }}
            />
          ) : (
            <button
              key={chip.id}
              type="button"
              className={chip.known ? "convo-fact is-known" : "convo-fact"}
              onClick={() => setEditing(chip.id)}
            >
              {chip.known ? "✓" : "○"} {chip.label}
            </button>
          )
        ))}
      </div>
      <div className={state.mode === "planning" ? "convo-stage is-planning" : "convo-stage"}>
        {state.mode === "planning" ? (
          <div className="convo-map">
            <TripMap
              stops={[{ id: "destination", lat: demoCity.center.lat, lng: demoCity.center.lng, label: demoCity.destination, kind: "stop" }]}
              arcs={[]}
              focus={0}
              dayLabel={demoCity.destination}
              route={false}
            />
          </div>
        ) : null}
        <div className="convo-column" ref={live} aria-live="polite">
          {state.messages.map((message) => (
            <article key={message.id} className={message.role === "user" ? "convo-msg is-user" : "convo-msg"}>
              <p>{message.text}</p>
              {message.role === "assistant" && message.controls.length > 0 && state.mode !== "stream" ? (
                <Controls controls={message.controls} answers={state.answers} onChoose={choose} />
              ) : null}
            </article>
          ))}
          {state.mode === "stream" && state.shown ? <p className="convo-msg">{state.shown}</p> : null}
          {state.mode === "stream" && !state.shown ? <p className="convo-status">Swan is writing…</p> : null}
          {state.mode === "planning" ? (
            <section className="convo-progress" aria-live="polite">
              {PROGRESS.map((line, index) => (
                <p key={line} className={index === progress ? "is-current" : undefined}>{line}</p>
              ))}
              <button type="button" className="swan-btn" onClick={onProposal}>See the proposal</button>
            </section>
          ) : null}
          {canPlan ? (
            <button type="button" className="swan-btn convo-plan" onClick={() => setState((current) => current && planNow(current, script))}>
              Plan it now
            </button>
          ) : null}
        </div>
      </div>
      <form
        className="home-prompt home-prompt-docked"
        onSubmit={(event) => {
          event.preventDefault();
          sendText(draft);
        }}
      >
        <label className="sr-only" htmlFor="trip-reply">Reply</label>
        <input id="trip-reply" value={draft} placeholder="Reply…" onChange={(event) => setDraft(event.target.value)} />
        <button className="home-send" type="submit" aria-label="Send" disabled={!draft.trim()}>↑</button>
      </form>
    </div>
  );
}

function Controls({
  controls,
  answers,
  onChoose,
}: {
  controls: Control[];
  answers: Record<string, string | number>;
  onChoose: (control: Control, value: string | number) => void;
}) {
  return (
    <div className="convo-controls">
      {controls.map((control) => {
        if (control.type === "slider") {
          const value = Number(answers[control.slot] ?? control.value ?? control.min ?? 0);
          return (
            <label key={control.slot} className="convo-slider">
              Budget ${value.toLocaleString("en-US")}
              <input
                type="range"
                min={control.min ?? 0}
                max={control.max ?? 5000}
                step={100}
                value={value}
                aria-valuetext={`$${value.toLocaleString("en-US")}`}
                onChange={(event) => onChoose(control, Number(event.target.value))}
              />
            </label>
          );
        }
        const options = control.options ?? [];
        return (
          <div key={control.slot} className="home-chips" role="group" aria-label={control.slot}>
            {options.map((option) => (
              <button
                key={option}
                type="button"
                className="home-chip"
                aria-pressed={String(answers[control.slot] ?? "") === option}
                onClick={() => onChoose(control, control.slot === "travellers" ? option : option)}
              >
                {option}
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}
