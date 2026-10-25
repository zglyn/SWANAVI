"use client";

import type { BookingLine, Proposal, Stop, Suggestion, SuggestionAction, SuggestionActionName, SuggestionStatus } from "@contracts/api";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { MapStop } from "@/components/map3d/TripMap";
import { LockIcon } from "@/components/trip/LockIcon";
import { ModifySheet } from "@/components/trip/ModifySheet";
import { getClient } from "@/lib/client";
import { formatClock, formatDay, formatDuration, formatMoney, hotelPrice, legLabel, suggestionTitle, summarizeFlight } from "@/lib/format";

const TripMap = dynamic(() => import("@/components/map3d/TripMap").then((mod) => mod.TripMap), { ssr: false });

const STATUS_LABEL: Record<SuggestionStatus, string> = {
  proposed: "Proposed",
  accepted: "✓ Accepted",
  modifying: "✎ Modifying",
  rejected: "✕ Removed",
  replaced: "↻ Updated",
  booked: "Booked",
};
const REASONS = ["Too expensive", "Not my style", "Bad time", "Too far", "Other"];
const REASON_MS = 5000;

type StopRow = Extract<Suggestion, { kind: "attraction" | "transfer" }>;
type Busy = Record<string, SuggestionActionName>;

interface CardActions {
  accept: (row: Suggestion) => void;
  undo: (row: Suggestion) => void;
  modify: (row: Suggestion, opener: HTMLElement) => void;
  reject: (row: Suggestion) => void;
  reason: (row: Suggestion, reason: string | null) => void;
  keep: (row: Suggestion) => void;
  hover: (id: string | null) => void;
}

function isStopRow(row: Suggestion): row is StopRow {
  return row.kind === "attraction" || row.kind === "transfer";
}

export function ProposalWorkspace({ tripId, onReview }: { tripId: string; onReview: () => void }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [bookings, setBookings] = useState<BookingLine[]>([]);
  const [day, setDay] = useState(0);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>({});
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [modifying, setModifying] = useState<Suggestion | null>(null);
  const [preview, setPreview] = useState<Suggestion | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const timer = useRef<number | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const focusCard = useRef<string | null>(null);

  useEffect(() => {
    getClient().getTrip(tripId).then((view) => {
      setProposal(view.proposal ?? null);
      setBookings(view.bookings);
    });
  }, [tripId]);

  useEffect(() => {
    const sid = focusCard.current;
    if (!sid) return;
    focusCard.current = null;
    const card = document.getElementById(`card-${sid}`);
    (card?.querySelector<HTMLElement>("[data-focus]") ?? card?.querySelector<HTMLElement>("button"))?.focus();
  }, [proposal, rejecting]);

  useEffect(() => () => clearTimer(), []);

  function clearTimer() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
  }

  async function send(action: SuggestionAction, row: Suggestion) {
    setBusy((current) => ({ ...current, [row.id]: action.action }));
    try {
      const result = await getClient().actOnSuggestion(tripId, action);
      setProposal(result.proposal);
      setAnnouncement(describe(action, row, result.proposal.suggestions.find((item) => item.id === row.id)));
      focusCard.current = row.id;
    } catch {
      setAnnouncement(`Swan could not update ${suggestionTitle(row)}. Try again.`);
    } finally {
      setBusy((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== row.id)));
    }
  }

  function commitReject(row: Suggestion, reason: string | null) {
    clearTimer();
    setRejecting(null);
    void send({ suggestion_id: row.id, action: "reject", reason }, row);
  }

  const actions: CardActions = {
    accept: (row) => void send({ suggestion_id: row.id, action: "accept" }, row),
    undo: (row) => void send({ suggestion_id: row.id, action: "undo" }, row),
    modify: (row, from) => {
      opener.current = from;
      setModifying(row);
    },
    reject: (row) => {
      const pending = rejecting && proposal?.suggestions.find((item) => item.id === rejecting);
      if (pending) commitReject(pending, null);
      setRejecting(row.id);
      focusCard.current = row.id;
      setAnnouncement(`${suggestionTitle(row)} will be rejected. Pick a reason, or Undo.`);
      timer.current = window.setTimeout(() => commitReject(row, null), REASON_MS);
    },
    reason: commitReject,
    keep: (row) => {
      clearTimer();
      setRejecting(null);
      focusCard.current = row.id;
      setAnnouncement(`Kept ${suggestionTitle(row)}.`);
    },
    hover: setHighlight,
  };

  function closeSheet() {
    setModifying(null);
    setPreview(null);
    opener.current?.focus();
  }

  if (!proposal) return <p className="convo-status" role="status">Loading the proposal…</p>;

  const rows = proposal.suggestions;
  const days = proposal.package.itinerary.days;
  const current = days[Math.min(day, days.length - 1)];
  const zone = proposal.package.itinerary.brief.timezone;
  const stopRow = (stop: Stop) => rows.filter(isStopRow).find((row) => row.item.id === stop.id);
  const removed = rows.filter(isStopRow).filter((row) => row.status === "rejected" && row.item.start.slice(0, 10) === current.date);
  const entries = [
    ...removed.map((row) => ({ stop: row.item, row })),
    ...current.stops.map((stop) => ({ stop, row: stopRow(stop) })),
  ].sort((left, right) => Date.parse(left.stop.start) - Date.parse(right.stop.start));
  const accepted = rows.filter((row) => row.status === "accepted" || row.status === "booked").length;
  const review = rows.filter((row) => row.status === "proposed" || row.status === "replaced").length;
  const savings = Number(proposal.totals.savings);
  const hotelRow = (offerId: string) => rows.find((row) => row.kind === "hotel" && row.item.offer.id === offerId);

  const mapStops: MapStop[] = [
    ...current.stops.filter((stop) => stop.kind !== "lodging").map((stop): MapStop => ({
      id: stopRow(stop)?.id ?? stop.id,
      lat: stop.location.lat,
      lng: stop.location.lng,
      label: stop.title,
      kind: "stop",
    })),
    ...proposal.package.hotels.map((stay): MapStop => ({
      id: hotelRow(stay.offer.id)?.id ?? stay.offer.id,
      lat: stay.offer.location.lat,
      lng: stay.offer.location.lng,
      label: stay.offer.name,
      kind: "hotel",
    })),
    ...ghost(preview, modifying),
  ];

  const card = (row: Suggestion, body: React.ReactNode) => (
    <SuggestionCard
      key={row.id}
      row={row}
      busy={busy[row.id]}
      rejecting={rejecting === row.id}
      modifying={modifying?.id === row.id}
      code={bookings.find((line) => line.suggestion_id === row.id)?.confirmation_code ?? null}
      actions={actions}
    >
      {body}
    </SuggestionCard>
  );

  return (
    <div className="proposal">
      <header className="home-bar">
        <Link href="/" className="home-brand">Swanavi</Link>
        <p className="swan-muted">Trip {tripId}</p>
      </header>
      <div className="proposal-body">
        <div className="proposal-list">
          <section className="proposal-summary" aria-label="Trip summary">
            <p className="proposal-total">
              <strong>{formatMoney(proposal.totals.total, proposal.totals.currency)}</strong> total
              {savings > 0 ? ` · ${formatMoney(savings, proposal.totals.currency)} saved` : ""}
            </p>
            <p>{accepted} accepted · {review} to review</p>
            <div className="proposal-actions">
              <button
                type="button"
                className="swan-btn-ghost"
                disabled={review === 0}
                onClick={async () => {
                  setProposal(await getClient().acceptAll(tripId));
                  setAnnouncement("Accepted everything left to review.");
                }}
              >
                Accept all remaining
              </button>
              <button type="button" className="proposal-book" disabled={accepted === 0} onClick={onReview}>Book accepted</button>
            </div>
            <p className="proposal-note" role="status" aria-live="polite">{announcement}</p>
          </section>
          <h2>Flights</h2>
          {rows.filter((row) => row.kind === "flight").map((row) => row.kind === "flight" && card(row, <FlightBody row={row} />))}
          <h2>Stay</h2>
          {rows.filter((row) => row.kind === "hotel").map((row) => row.kind === "hotel" && card(row, <HotelBody row={row} />))}
          <h2>Days</h2>
          <div className="home-chips proposal-days" role="tablist" aria-label="Days">
            {days.map((item, index) => (
              <button key={item.date} type="button" className="home-chip" role="tab" aria-selected={index === day} onClick={() => setDay(index)}>
                {formatDay(item.date, false)}
              </button>
            ))}
          </div>
          <ol className="proposal-day" aria-label={`Stops on ${formatDay(current.date)}`}>
            {entries.map(({ stop, row }) => {
              const leg = row?.status === "rejected" ? undefined : current.legs.find((item) => item.from_stop_id === stop.id);
              return (
                <li key={row?.id ?? stop.id}>
                  {row ? card(row, <StopBody stop={stop} zone={zone} />) : (
                    <p className="trip-card trip-fixed">{formatClock(stop.start, zone)} · {stop.title}</p>
                  )}
                  {leg ? <p className="trip-leg">↓ {legLabel(leg)}</p> : null}
                </li>
              );
            })}
          </ol>
          <form className="home-prompt" onSubmit={(event) => { event.preventDefault(); setAnnouncement("Typed changes arrive with the replanner."); }}>
            <label className="sr-only" htmlFor="change-prompt">Ask Swan to change anything</label>
            <input id="change-prompt" placeholder="Ask Swan to change anything…" />
            <button className="home-send" type="submit" aria-label="Send a change">↑</button>
          </form>
        </div>
        <div className="proposal-map">
          <TripMap
            stops={mapStops}
            arcs={[]}
            focus={day}
            dayLabel={current.date}
            highlight={highlight}
            onSelect={(id) => {
              setHighlight(id);
              document.getElementById(`card-${id}`)?.scrollIntoView({ block: "center" });
            }}
          />
        </div>
      </div>
      {modifying ? (
        <ModifySheet
          tripId={tripId}
          row={modifying}
          onPreview={setPreview}
          onClose={closeSheet}
          onPick={(alternative) => {
            const row = modifying;
            closeSheet();
            void send({ suggestion_id: row.id, action: "modify", alternative_id: alternative.id }, row);
          }}
        />
      ) : null}
    </div>
  );
}

function ghost(preview: Suggestion | null, modifying: Suggestion | null): MapStop[] {
  if (!preview || !modifying) return [];
  if (preview.kind === "hotel") {
    const { offer } = preview.item;
    return [{ id: `preview-${offer.id}`, lat: offer.location.lat, lng: offer.location.lng, label: `Preview: ${offer.name}`, kind: "hotel", replaces: modifying.id }];
  }
  if (preview.kind === "attraction") {
    const { location, title } = preview.item;
    return [{ id: `preview-${preview.id}`, lat: location.lat, lng: location.lng, label: `Preview: ${title}`, kind: "stop", replaces: modifying.id }];
  }
  return [];
}

function describe(action: SuggestionAction, before: Suggestion, after: Suggestion | undefined): string {
  const name = suggestionTitle(before);
  if (action.action === "accept") return `Accepted ${name}.`;
  if (action.action === "undo") return `Restored ${after ? suggestionTitle(after) : name}.`;
  if (action.action === "modify") return `Switched to ${after ? suggestionTitle(after) : name} and accepted it.`;
  if (isStopRow(before)) return `Removed ${name}. The day was reflowed.`;
  if (after?.status === "replaced") return `Replaced ${name} with ${suggestionTitle(after)}.`;
  return `No other option was found for ${name}.`;
}

function SuggestionCard({
  row,
  busy,
  rejecting,
  modifying,
  code,
  actions,
  children,
}: {
  row: Suggestion;
  busy: SuggestionActionName | undefined;
  rejecting: boolean;
  modifying: boolean;
  code: string | null;
  actions: CardActions;
  children: React.ReactNode;
}) {
  const name = suggestionTitle(row);
  const reasons = rejecting ? <ReasonRow row={row} actions={actions} /> : null;
  if (isStopRow(row) && (rejecting || row.status === "rejected")) {
    return (
      <article id={`card-${row.id}`} className="trip-card is-collapsed">
        <p><span aria-hidden="true">✕</span> Removed: {name}</p>
        <button type="button" className="swan-btn-ghost" disabled={Boolean(busy)} onClick={() => (rejecting ? actions.keep(row) : actions.undo(row))} aria-label={`Undo removing ${name}`}>
          Undo
        </button>
        {reasons}
      </article>
    );
  }
  const searching = busy === "reject" && row.required;
  const label = modifying ? STATUS_LABEL.modifying : rejecting ? "✕ Rejected" : STATUS_LABEL[row.status];
  return (
    <article
      id={`card-${row.id}`}
      className="trip-card"
      data-status={row.status}
      data-raised={modifying || undefined}
      onMouseEnter={() => actions.hover(row.id)}
      onMouseLeave={() => actions.hover(null)}
    >
      <p className="trip-status">
        {row.status === "booked" ? <><LockIcon /> Booked{code ? ` · ${code}` : ""}</> : searching ? "Finding another…" : label}
      </p>
      {children}
      {row.why.length ? (
        <ul className="why-chips" aria-label="Why Swan picked this">
          {row.why.map((line) => <li key={line}>{line}</li>)}
        </ul>
      ) : null}
      {rejecting ? (
        <>
          <button type="button" className="swan-btn-ghost" onClick={() => actions.keep(row)} aria-label={`Undo rejecting ${name}`}>Undo</button>
          {reasons}
        </>
      ) : (
        <Actions row={row} busy={Boolean(busy)} actions={actions} />
      )}
    </article>
  );
}

function ReasonRow({ row, actions }: { row: Suggestion; actions: CardActions }) {
  return (
    <div className="reason-row" role="group" aria-label={`Why are you rejecting ${suggestionTitle(row)}?`}>
      {REASONS.map((reason, index) => (
        <button key={reason} type="button" className="home-chip" data-focus={index === 0 || undefined} onClick={() => actions.reason(row, reason)}>
          {reason}
        </button>
      ))}
    </div>
  );
}

function Actions({ row, busy, actions }: { row: Suggestion; busy: boolean; actions: CardActions }) {
  const name = suggestionTitle(row);
  if (row.status === "booked") return null;
  if (row.status === "rejected") {
    return (
      <div className="proposal-actions">
        <button type="button" className="swan-btn-ghost" disabled={busy} onClick={() => actions.undo(row)} aria-label={`Undo rejecting ${name}`}>Undo</button>
      </div>
    );
  }
  return (
    <div className="proposal-actions">
      {row.status === "accepted" ? (
        <button type="button" className="swan-btn-ghost" disabled={busy} onClick={() => actions.undo(row)} aria-label={`Undo accepting ${name}`}>Undo</button>
      ) : (
        <button type="button" className="swan-btn" disabled={busy} onClick={() => actions.accept(row)} aria-label={`Accept ${name}`}>Accept</button>
      )}
      <button type="button" className="swan-btn-ghost" disabled={busy} onClick={(event) => actions.modify(row, event.currentTarget)} aria-label={`Modify ${name}`}>Modify</button>
      {row.status !== "accepted" ? (
        <button type="button" className="swan-btn-ghost" disabled={busy} onClick={() => actions.reject(row)} aria-label={`Reject ${name}`}>Reject</button>
      ) : null}
      {row.status === "replaced" ? (
        <button type="button" className="swan-btn-ghost" disabled={busy} onClick={() => actions.undo(row)} aria-label={`Undo replacing ${name}`}>Undo</button>
      ) : null}
    </div>
  );
}

function FlightBody({ row }: { row: Extract<Suggestion, { kind: "flight" }> }) {
  const flight = summarizeFlight(row.item);
  return (
    <>
      <p className="trip-card-title">{flight.airline} · {flight.route}</p>
      <p>
        {flight.departDay} {flight.depart} → {flight.arrive}{flight.arrivalNote ? ` ${flight.arrivalNote}` : ""} · {flight.stops} · {flight.duration} ·{" "}
        {formatMoney(row.item.price, row.item.currency)}
      </p>
    </>
  );
}

function HotelBody({ row }: { row: Extract<Suggestion, { kind: "hotel" }> }) {
  const { offer } = row.item;
  return (
    <>
      <p className="trip-card-title">{offer.name}</p>
      <p>{hotelPrice(offer)} · {offer.avg_travel_min_to_attractions} min average to your stops</p>
    </>
  );
}

function StopBody({ stop, zone }: { stop: Stop; zone: string }) {
  const minutes = Math.round((Date.parse(stop.end) - Date.parse(stop.start)) / 60000);
  const price = stop.quote ? formatMoney(stop.quote.amount, stop.quote.currency) : stop.attraction?.free ? "Free" : null;
  return (
    <>
      <p className="trip-card-title">{formatClock(stop.start, zone)} · {stop.title}</p>
      <p>{[formatDuration(minutes), price].filter(Boolean).join(" · ")}</p>
    </>
  );
}
