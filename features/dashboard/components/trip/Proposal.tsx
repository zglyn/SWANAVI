"use client";

import type { FlightOffer, HotelStay, Stop, Suggestion, SuggestionStatus } from "@contracts/api";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { MapStop } from "@/components/map3d/TripMap";
import { kyotoProposal } from "@/lib/conversationPlay";

const TripMap = dynamic(() => import("@/components/map3d/TripMap").then((mod) => mod.TripMap), { ssr: false });

const STATUS_LABEL: Record<SuggestionStatus, string> = {
  proposed: "Proposed",
  accepted: "Accepted",
  modifying: "Modifying",
  rejected: "Rejected",
  replaced: "Updated",
  booked: "Booked",
};

export function ProposalWorkspace({ tripId }: { tripId: string }) {
  const proposal = kyotoProposal();
  const [rows, setRows] = useState<Suggestion[]>(proposal.suggestions);
  const [day, setDay] = useState(0);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const days = proposal.package.itinerary.days;
  const current = days[day];

  const accepted = rows.filter((row) => row.status === "accepted").length;
  const review = rows.filter((row) => row.status === "proposed" || row.status === "replaced").length;

  function setStatus(id: string, status: SuggestionStatus) {
    setRows((currentRows) => currentRows.map((row) => row.id === id ? { ...row, status } : row));
    setNote("");
  }

  const mapStops: MapStop[] = useMemo(() => current.stops.map((stop) => ({
    id: stop.id,
    lat: stop.location.lat,
    lng: stop.location.lng,
    label: stop.title,
    kind: stop.kind === "lodging" ? "hotel" as const : "stop" as const,
  })), [current]);

  return (
    <div className="proposal">
      <header className="home-bar">
        <Link href="/" className="home-brand">Swanavi</Link>
        <p className="swan-muted">Trip {tripId}</p>
      </header>
      <div className="proposal-body">
        <div className="proposal-list">
          <section className="proposal-summary">
            <p>${Number(proposal.totals.total).toLocaleString("en-US")} total</p>
            <p>{accepted} accepted · {review} to review</p>
            <div className="proposal-actions">
              <button type="button" className="swan-btn-ghost" onClick={() => setRows((currentRows) => currentRows.map((row) => row.status === "proposed" ? { ...row, status: "accepted" } : row))}>
                Accept all remaining
              </button>
              <button type="button" className="proposal-book" onClick={() => setNote("Booking opens on the review step.")}>Book accepted</button>
            </div>
          </section>
          {note ? <p role="status">{note}</p> : null}
          <h2>Flights</h2>
          {rows.filter((row) => row.kind === "flight").map((row) => (
            <FlightCard key={row.id} row={row} onStatus={setStatus} onStub={setNote} onHover={setHighlight} />
          ))}
          <h2>Stay</h2>
          {rows.filter((row) => row.kind === "hotel").map((row) => (
            <HotelCard key={row.id} row={row} onStatus={setStatus} onStub={setNote} onHover={setHighlight} />
          ))}
          <h2>Days</h2>
          <div className="home-chips" role="tablist" aria-label="Days">
            {days.map((item, index) => (
              <button key={item.date} type="button" className="home-chip" role="tab" aria-selected={index === day} onClick={() => setDay(index)}>
                {item.date.slice(5)}
              </button>
            ))}
          </div>
          <ol className="proposal-day">
            {current.stops.map((stop) => {
              const row = rows.find((item) => item.id === `sug-stop-${stop.id}`);
              return (
                <li key={stop.id} id={`card-${stop.id}`}>
                  {row ? (
                    <StopCard row={row} stop={stop} onStatus={setStatus} onStub={setNote} onHover={setHighlight} />
                  ) : (
                    <p className="convo-msg">{stop.title}</p>
                  )}
                </li>
              );
            })}
          </ol>
          <form className="home-prompt" onSubmit={(event) => { event.preventDefault(); setNote("Typed changes arrive with the replanner."); }}>
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
    </div>
  );
}

function Actions({
  row,
  onStatus,
  onStub,
}: {
  row: Suggestion;
  onStatus: (id: string, status: SuggestionStatus) => void;
  onStub: (note: string) => void;
}) {
  return (
    <div className="proposal-actions">
      <span className="convo-fact is-known">{STATUS_LABEL[row.status]}</span>
      {row.status === "accepted" ? (
        <button type="button" className="swan-btn-ghost" onClick={() => onStatus(row.id, "proposed")}>Undo</button>
      ) : (
        <button type="button" className="swan-btn" onClick={() => onStatus(row.id, "accepted")}>Accept</button>
      )}
      <button type="button" className="swan-btn-ghost" onClick={() => onStub("Modify opens on the next step.")}>Modify</button>
      <button type="button" className="swan-btn-ghost" onClick={() => onStub("Reject opens on the next step.")}>Reject</button>
    </div>
  );
}

function FlightCard({
  row,
  onStatus,
  onStub,
  onHover,
}: {
  row: Suggestion;
  onStatus: (id: string, status: SuggestionStatus) => void;
  onStub: (note: string) => void;
  onHover: (id: string | null) => void;
}) {
  const flight = row.item as FlightOffer;
  const first = flight.segments[0];
  const last = flight.segments[flight.segments.length - 1];
  return (
    <article className="convo-msg" onMouseEnter={() => onHover(first.from_place.code ?? flight.id)} onMouseLeave={() => onHover(null)}>
      <p>{flight.carrier} · {first.from_place.code} → {last.to_place.code}</p>
      <p>{clock(first.depart_at)} → {clock(last.arrive_at)} · {flight.stops === 0 ? "Nonstop" : `${flight.stops} stops`} · ${Number(flight.price).toLocaleString("en-US")}</p>
      <p className="swan-muted">{row.why.join(" · ")}</p>
      <Actions row={row} onStatus={onStatus} onStub={onStub} />
    </article>
  );
}

function HotelCard({
  row,
  onStatus,
  onStub,
  onHover,
}: {
  row: Suggestion;
  onStatus: (id: string, status: SuggestionStatus) => void;
  onStub: (note: string) => void;
  onHover: (id: string | null) => void;
}) {
  const stay = row.item as HotelStay;
  return (
    <article className="convo-msg" id="card-check-in" onMouseEnter={() => onHover("check-in")} onMouseLeave={() => onHover(null)}>
      <p>{stay.offer.name}</p>
      <p>${Number(stay.offer.price_per_night).toLocaleString("en-US")} / night · {stay.offer.avg_travel_min_to_attractions} min average to your stops</p>
      <p className="swan-muted">{row.why.join(" · ")}</p>
      <Actions row={row} onStatus={onStatus} onStub={onStub} />
    </article>
  );
}

function StopCard({
  row,
  stop,
  onStatus,
  onStub,
  onHover,
}: {
  row: Suggestion;
  stop: Stop;
  onStatus: (id: string, status: SuggestionStatus) => void;
  onStub: (note: string) => void;
  onHover: (id: string | null) => void;
}) {
  return (
    <article className="convo-msg" onMouseEnter={() => onHover(stop.id)} onMouseLeave={() => onHover(null)}>
      <p>{clock(stop.start)} {stop.title}</p>
      <p className="swan-muted">{row.why.join(" · ")}</p>
      <Actions row={row} onStatus={onStatus} onStub={onStub} />
    </article>
  );
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
