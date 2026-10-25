"use client";

import type { Suggestion, TimeOfDayWindow } from "@contracts/api";
import { useEffect, useRef, useState } from "react";
import { getClient } from "@/lib/client";
import { airlineName, formatMoney, hotelPrice, suggestionTitle, summarizeFlight } from "@/lib/format";
import type { Constraints } from "@/lib/proposalOps";

type Option<T> = { label: string; value: T | undefined };

const TIMES: Option<TimeOfDayWindow>[] = [
  { label: "Any time", value: undefined },
  { label: "Early morning", value: "early_morning" },
  { label: "Morning", value: "morning" },
  { label: "Afternoon", value: "afternoon" },
  { label: "Evening", value: "evening" },
];
const STOPS: Option<number>[] = [
  { label: "Any stops", value: undefined },
  { label: "Nonstop", value: 0 },
  { label: "1 stop at most", value: 1 },
];
const STARS: Option<number>[] = [
  { label: "Any stars", value: undefined },
  { label: "3+ stars", value: 3 },
  { label: "4+ stars", value: 4 },
];
const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ModifySheet({
  tripId,
  row,
  onClose,
  onPick,
  onPreview,
}: {
  tripId: string;
  row: Suggestion;
  onClose: () => void;
  onPick: (alternative: Suggestion) => void;
  onPreview: (alternative: Suggestion | null) => void;
}) {
  const [constraints, setConstraints] = useState<Constraints>({});
  const [options, setOptions] = useState<Suggestion[] | null>(null);
  const [baseline, setBaseline] = useState<Suggestion[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  const handlers = useRef({ onClose, onPreview });
  handlers.current = { onClose, onPreview };
  const title = suggestionTitle(row);

  function show(list: Suggestion[]) {
    setOptions(list);
    setSelected(list[0]?.id ?? null);
    handlers.current.onPreview(list[0] ?? null);
  }

  useEffect(() => {
    let live = true;
    setOptions(null);
    const wait = window.setTimeout(() => {
      getClient().suggestionAlternatives(tripId, row.id, constraints).then((list) => {
        if (!live) return;
        show(list);
        if (Object.keys(constraints).length === 0) setBaseline(list);
      });
    }, 200);
    return () => {
      live = false;
      window.clearTimeout(wait);
    };
  }, [tripId, row.id, constraints]);

  useEffect(() => {
    const node = panel.current;
    if (!node) return;
    node.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        handlers.current.onClose();
        return;
      }
      if (event.key !== "Tab" || !node) return;
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function change(next: Constraints) {
    setConstraints((current) => {
      const merged = { ...current, ...next };
      return Object.fromEntries(Object.entries(merged).filter(([, value]) => value !== undefined)) as Constraints;
    });
  }

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const typed = text.trim();
    if (!typed) return;
    setOptions(null);
    const result = await getClient().actOnSuggestion(tripId, { suggestion_id: row.id, action: "modify", text: typed });
    show(result.alternatives);
  }

  function pick(id: string) {
    setSelected(id);
    onPreview(options?.find((option) => option.id === id) ?? null);
  }

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="modify-title" ref={panel}>
        <header className="sheet-head">
          <h2 id="modify-title">Change {title}</h2>
          <button type="button" className="sheet-close" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <section aria-labelledby="alt-heading">
          <h3 id="alt-heading" className="sheet-label">Swan&apos;s alternatives</h3>
          {options === null ? <p className="convo-status" role="status">Finding options…</p> : null}
          {options && options.length === 0 ? <p role="status">Nothing matches. Loosen a control.</p> : null}
          {options && options.length ? (
            <ol className="alt-list">
              {options.map((option, rank) => (
                <li key={option.id}>
                  <article className="alt-card" data-selected={option.id === selected || undefined}>
                    <button type="button" className="alt-select" aria-pressed={option.id === selected} onClick={() => pick(option.id)}>
                      <span className="alt-rank" aria-hidden="true">{rank + 1}</span>
                      <span>
                        <strong>{suggestionTitle(option)}</strong>
                        <span className="alt-meta">{detail(option)}</span>
                      </span>
                    </button>
                    {option.why.length ? (
                      <ul className="why-chips" aria-label="Why">
                        {option.why.map((line) => <li key={line}>{line}</li>)}
                      </ul>
                    ) : null}
                    <button type="button" className="swan-btn alt-choose" onClick={() => onPick(option)}>
                      Choose {suggestionTitle(option)}
                    </button>
                  </article>
                </li>
              ))}
            </ol>
          ) : null}
        </section>
        <section aria-labelledby="tune-heading" className="sheet-tune">
          <h3 id="tune-heading" className="sheet-label">Fine-tune</h3>
          <Controls row={row} constraints={constraints} baseline={baseline} onChange={change} />
        </section>
        <form className="home-prompt sheet-ask" onSubmit={ask}>
          <label className="sr-only" htmlFor="modify-text">Tell Swan what to change</label>
          <input
            id="modify-text"
            value={text}
            placeholder={row.kind === "hotel" ? "Closer to Gion" : row.kind === "flight" ? "Make it cheaper" : "Something with food"}
            onChange={(event) => setText(event.target.value)}
          />
          <button className="home-send" type="submit" aria-label="Ask Swan" disabled={!text.trim()}>↑</button>
        </form>
      </div>
    </div>
  );
}

function Controls({
  row,
  constraints,
  baseline,
  onChange,
}: {
  row: Suggestion;
  constraints: Constraints;
  baseline: Suggestion[];
  onChange: (next: Constraints) => void;
}) {
  if (row.kind === "flight") {
    const airlines = [...new Set([row.item.carrier, ...baseline.flatMap((option) => (option.kind === "flight" ? [option.item.carrier] : []))])];
    const prices = [row.item, ...baseline.flatMap((option) => (option.kind === "flight" ? [option.item] : []))].map((offer) => Number(offer.price));
    return (
      <>
        <Chips label={row.item.direction === "outbound" ? "Outbound time" : "Return time"} options={TIMES} value={constraints.time_of_day} onChange={(time_of_day) => onChange({ time_of_day })} />
        <Chips label="Stops" options={STOPS} value={constraints.max_stops} onChange={(max_stops) => onChange({ max_stops })} />
        <Chips label="Airline" options={[{ label: "Any airline", value: undefined }, ...airlines.map((code) => ({ label: airlineName(code), value: code }))]} value={constraints.airline} onChange={(airline) => onChange({ airline })} />
        <PriceSlider label="Most you want to pay" prices={prices} value={constraints.max_price} onChange={(max_price) => onChange({ max_price })} />
      </>
    );
  }
  if (row.kind === "hotel") {
    const areas = [...new Set(baseline.flatMap((option) => (option.kind === "hotel" && option.item.offer.area ? [option.item.offer.area] : [])))];
    const prices = [row.item, ...baseline.flatMap((option) => (option.kind === "hotel" ? [option.item] : []))].map((stay) => Number(stay.offer.price_per_night));
    return (
      <>
        <PriceSlider label="Most per night" prices={prices} value={constraints.max_price} onChange={(max_price) => onChange({ max_price })} />
        <Chips label="Area" options={[{ label: "Any area", value: undefined }, ...areas.map((area) => ({ label: area, value: area }))]} value={constraints.area} onChange={(area) => onChange({ area })} />
        <Chips label="Stars" options={STARS} value={constraints.min_stars} onChange={(min_stars) => onChange({ min_stars })} />
      </>
    );
  }
  const similar = row.item.attraction?.category;
  const kinds: Option<string>[] = [
    { label: "Anything", value: undefined },
    ...(similar ? [{ label: "Something similar", value: similar }] : []),
    { label: "More food", value: "food" },
    { label: "More nature", value: "nature" },
  ];
  return <Chips label="Kind of place" options={kinds} value={constraints.category} onChange={(category) => onChange({ category })} />;
}

function Chips<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  value: T | undefined;
  onChange: (value: T | undefined) => void;
}) {
  return (
    <fieldset className="sheet-field">
      <legend>{label}</legend>
      <div className="sheet-chips">
        {options.map((option) => (
          <button key={option.label} type="button" className="home-chip" aria-pressed={option.value === value} onClick={() => onChange(option.value)}>
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function PriceSlider({
  label,
  prices,
  value,
  onChange,
}: {
  label: string;
  prices: number[];
  value: number | undefined;
  onChange: (value: number | undefined) => void;
}) {
  const low = Math.floor(Math.min(...prices) / 10) * 10;
  const high = Math.ceil(Math.max(...prices) / 10) * 10;
  const shown = value ?? high;
  const text = value === undefined ? "Any price" : `Up to ${formatMoney(shown)}`;
  return (
    <label className="sheet-field convo-slider">
      {label}: {text}
      <input
        type="range"
        min={low}
        max={high}
        step={10}
        value={shown}
        aria-valuetext={text}
        onChange={(event) => {
          const next = Number(event.target.value);
          onChange(next >= high ? undefined : next);
        }}
      />
    </label>
  );
}

function detail(option: Suggestion): string {
  if (option.kind === "flight") {
    const flight = summarizeFlight(option.item);
    return `${flight.departDay} ${flight.depart} → ${flight.arrive}${flight.arrivalNote ? ` ${flight.arrivalNote}` : ""} · ${flight.stops} · ${formatMoney(option.item.price, option.item.currency)}`;
  }
  if (option.kind === "hotel") return hotelPrice(option.item.offer);
  const place = option.item.attraction;
  return [place?.area, place ? `${place.typical_duration_min} min` : null, place?.free ? "Free" : null].filter(Boolean).join(" · ");
}
