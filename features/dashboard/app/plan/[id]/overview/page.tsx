"use client";

import type { FlightOffer, Quote, TravelPackage } from "@contracts/api";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Logo } from "@/components/Logo";
import { TripMap, type MapStop } from "@/components/map3d/TripMap";
import { handOffToWallet, hostOf, readBooked, setBooked } from "@/lib/booking";
import { getClient } from "@/lib/client";
import { airlineName, formatClock, formatDateRange, formatDay, formatMoney, hotelPrice, legLabel, nightsBetween, summarizeFlight } from "@/lib/format";

type ChecklistItem = {
  key: string;
  title: string;
  detail: string;
  action: { label: string; href?: string; onClick?: () => void };
};

export default function OverviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [pack, setPack] = useState<TravelPackage | null>(null);
  const [day, setDay] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [booked, setBookedState] = useState<string[]>([]);
  const [highlight, setHighlight] = useState<string | null>(null);

  useEffect(() => {
    client.getPackage(params.id).then(setPack).catch((err: Error) => setError(err.message));
    setBookedState(readBooked(params.id));
  }, [client, params.id]);

  if (error) {
    return (
      <main className="swan-app p-6">
        <p>{error}</p>
        <Link className="underline" href={`/plan/${params.id}/flights`}>Choose flights</Link>
      </main>
    );
  }
  if (!pack) return <main className="swan-app p-6">Opening your trip…</main>;

  const current = pack.itinerary.days[day];
  const hotelStops: MapStop[] = pack.hotels.map((stay) => ({
    id: stay.offer.id,
    lat: stay.offer.location.lat,
    lng: stay.offer.location.lng,
    label: stay.offer.name,
    kind: stay.offer.source === "merchant_mcp" ? "merchant" : "hotel",
  }));
  const dayStops: MapStop[] = (current?.stops ?? []).map((stop) => ({
    id: stop.id,
    lat: stop.location.lat,
    lng: stop.location.lng,
    label: stop.title,
    kind: "stop" as const,
    badge: stop.kind === "lodging" ? "H" : undefined,
  }));
  const dayHasHotel = (current?.stops ?? []).some((stop) => stop.kind === "lodging");
  const mapStops = dayHasHotel ? dayStops : [...hotelStops, ...dayStops];
  const arcs = [pack.outbound, pack.return].flatMap((offer) => {
    const segment = offer?.segments[0];
    if (!segment?.from_place.location || !segment.to_place.location) return [];
    return [{
      from: [segment.from_place.location.lng, segment.from_place.location.lat] as [number, number],
      to: [segment.to_place.location.lng, segment.to_place.location.lat] as [number, number],
    }];
  });
  const quotes = [
    ...pack.itinerary.days.flatMap((item) => item.stops.map((stop) => stop.quote).filter(Boolean)),
    ...pack.hotels.map((stay) => stay.offer.quote).filter(Boolean),
  ] as Quote[];
  const walletTotal = quotes.reduce((sum, quote) => sum + Number(quote.amount), 0);
  const start = pack.itinerary.brief.start_date ?? current?.date ?? "";
  const end = pack.itinerary.brief.end_date ?? start;
  const legsByFrom = new Map((current?.legs ?? []).map((leg) => [leg.from_stop_id, leg]));

  const checklist: ChecklistItem[] = [];
  if (quotes.length) {
    checklist.push({
      key: "activities",
      title: "Activities and local stays",
      detail: `Pay with your wallet · ${formatMoney(walletTotal, "RLUSD")}`,
      action: {
        label: "Pay with wallet",
        onClick: () => {
          handOffToWallet(params.id, quotes);
          router.push("/dashboard?book=1");
        },
      },
    });
  }
  pack.hotels
    .filter((stay) => stay.offer.source !== "merchant_mcp")
    .forEach((stay) => {
      checklist.push({
        key: `hotel-${stay.offer.id}`,
        title: `Hotel: ${stay.offer.name}`,
        detail: `${formatMoney(stay.offer.total, stay.offer.currency)} · book on ${hostOf(stay.offer.deep_link)}`,
        action: { label: `Open ${hostOf(stay.offer.deep_link)}`, href: stay.offer.deep_link ?? undefined },
      });
    });
  const flights = [pack.outbound, pack.return].filter(Boolean) as FlightOffer[];
  if (flights.length) {
    const flightTotal = flights.reduce((sum, offer) => sum + Number(offer.price), 0);
    const sites = [...new Set(flights.map((offer) => hostOf(offer.deep_link)))];
    checklist.push({
      key: "flights",
      title: `Flights: ${[...new Set(flights.map((offer) => airlineName(offer.carrier)))].join(" and ")}`,
      detail: `${formatMoney(flightTotal, flights[0].currency)} · book on ${sites.join(", ")}`,
      action: { label: `Open ${sites[0]}`, href: flights[0].deep_link ?? undefined },
    });
  }
  const done = checklist.filter((item) => booked.includes(item.key)).length;

  function toggle(key: string) {
    setBookedState(setBooked(params.id, key, !booked.includes(key)));
  }

  return (
    <main className="swan-app relative h-screen overflow-hidden">
      <div className="swan-overview-map">
        <TripMap
          stops={mapStops}
          arcs={arcs}
          focus={hotelStops.length}
          dayLabel={current ? formatDay(current.date) : "Trip"}
          highlight={highlight}
        />
      </div>
      <section className="swan-sheet swan-overview-sheet relative z-10 overflow-y-auto rounded-t-3xl px-4 py-5 lg:fixed lg:inset-y-0 lg:right-0 lg:rounded-none lg:px-6">
        <Link href="/" aria-label="Swanavi home"><Logo /></Link>
        <p className="swan-eyebrow mt-5">Your trip</p>
        <h1 className="mt-1 text-4xl">{pack.itinerary.brief.destination}</h1>
        <p className="swan-muted mt-1">{formatDateRange(start, end)} · {nightsBetween(start, end)} nights</p>
        <p className="mt-4 text-4xl font-bold tracking-tight">{formatMoney(pack.totals.total, pack.totals.currency)}</p>
        <p className="swan-muted text-sm">
          Flights {formatMoney(pack.totals.flights, pack.totals.currency)} · Stay {formatMoney(pack.totals.hotels, pack.totals.currency)}
          {Number(pack.totals.activities) > 0 ? ` · Activities ${formatMoney(pack.totals.activities, pack.totals.currency)}` : ""}
        </p>
        {Number(pack.totals.savings) > 0 && (
          <p className="mt-1 text-sm">You save {formatMoney(pack.totals.savings, pack.totals.currency)} by paying Swanavi merchants directly.</p>
        )}

        <article className="mt-7">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl">Flights</h2>
            <Link className="underline underline-offset-4" href={`/plan/${params.id}/flights`}>Change</Link>
          </div>
          {flights.map((offer) => <FlightRow key={offer.id} offer={offer} />)}
        </article>

        <article className="mt-7">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl">Stay</h2>
            <Link className="underline underline-offset-4" href={`/plan/${params.id}/hotels`}>Change</Link>
          </div>
          {pack.hotels.map((stay) => (
            <div key={stay.offer.id} className="swan-card mt-3 p-4" onMouseEnter={() => setHighlight(stay.offer.id)} onMouseLeave={() => setHighlight(null)}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold">{stay.offer.name}</p>
                  <p className="swan-muted text-sm">{stay.offer.area ?? ""}{stay.offer.stars ? ` · ${stay.offer.stars} stars` : ""}</p>
                </div>
                {stay.offer.source === "merchant_mcp" ? <span className="swan-badge swan-badge-solid">Wallet</span> : null}
              </div>
              <p className="mt-2 text-sm">Check in {formatDay(stay.check_in)} · check out {formatDay(stay.check_out)}</p>
              <p className="mt-1 text-sm">{hotelPrice(stay.offer, nightsBetween(stay.check_in, stay.check_out))}</p>
              {stay.offer.avg_travel_min_to_attractions > 0 ? (
                <p className="swan-muted mt-1 text-sm">{stay.offer.avg_travel_min_to_attractions} min on average to your picks</p>
              ) : null}
            </div>
          ))}
        </article>

        <article className="mt-7">
          <h2 className="text-2xl">Day by day</h2>
          <div className="swan-seg mt-3 overflow-x-auto" role="radiogroup" aria-label="Day">
            {pack.itinerary.days.map((item, index) => (
              <button key={item.date} type="button" role="radio" aria-checked={index === day} className="shrink-0" onClick={() => setDay(index)}>
                {formatDay(item.date, false)}
              </button>
            ))}
          </div>
          <ol className="mt-4">
            {current?.stops.map((stop, index) => {
              const leg = legsByFrom.get(stop.id);
              const next = current.stops[index + 1];
              return (
                <li key={stop.id} onMouseEnter={() => setHighlight(stop.id)} onMouseLeave={() => setHighlight(null)}>
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="font-medium">{stop.title}</p>
                    <p className="swan-muted shrink-0 text-sm">{formatClock(stop.start, "Asia/Tokyo")} – {formatClock(stop.end, "Asia/Tokyo")}</p>
                  </div>
                  {leg && next ? (
                    <p className="swan-muted my-2 border-l-2 border-current pl-3 text-sm">{legLabel(leg)} to {next.title.replace(/^(Check in at|Check out of|Arrive .* at|Depart .* from) /, "")}</p>
                  ) : null}
                </li>
              );
            })}
          </ol>
          {pack.itinerary.warnings.length ? (
            <ul className="swan-muted mt-3 space-y-1 text-sm">{pack.itinerary.warnings.map((line) => <li key={line}>{line}</li>)}</ul>
          ) : null}
        </article>

        <details className="mt-6">
          <summary className="cursor-pointer font-medium">Why Swanavi chose this</summary>
          <ul className="mt-2 space-y-1 text-sm">{pack.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </details>

        <article className="mt-8 pb-6" aria-labelledby="book-heading">
          <div className="flex items-center justify-between">
            <h2 id="book-heading" className="text-2xl">Book it</h2>
            <span className="swan-badge">{done} of {checklist.length} done</span>
          </div>
          <div className="swan-progress mt-3" aria-hidden="true"><span style={{ width: `${checklist.length ? (done / checklist.length) * 100 : 0}%` }} /></div>
          <ul className="mt-4 space-y-3">
            {checklist.map((item) => {
              const isDone = booked.includes(item.key);
              return (
                <li key={item.key} className="swan-card flex items-start gap-3 p-4">
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={isDone}
                    aria-label={`${item.title} booked`}
                    className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${isDone ? "swan-invert border-transparent" : "swan-line"}`}
                    onClick={() => toggle(item.key)}
                  >
                    {isDone ? "✓" : ""}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className={`font-medium ${isDone ? "line-through" : ""}`}>{item.title}</p>
                    <p className="swan-muted text-sm">{item.detail}</p>
                    {!isDone ? (
                      item.action.href ? (
                        <a className="swan-btn-ghost mt-3 inline-flex items-center" href={item.action.href} target="_blank" rel="noreferrer">
                          {item.action.label}
                        </a>
                      ) : (
                        <button type="button" className="swan-btn mt-3" onClick={item.action.onClick}>{item.action.label}</button>
                      )
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="swan-muted mt-3 text-sm">Swanavi pays local merchants from your wallet. Airlines and hotel chains open their own sites; tick them off when you are done.</p>
        </article>
      </section>
    </main>
  );
}

function FlightRow({ offer }: { offer: FlightOffer }) {
  const summary = summarizeFlight(offer);
  return (
    <div className="swan-card mt-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{summary.airline} · {summary.route}</p>
          <p className="swan-muted text-sm">{summary.departDay} · {summary.flightNumbers} · {summary.stops}</p>
        </div>
        <p className="shrink-0 text-lg font-semibold">{formatMoney(offer.price, offer.currency)}</p>
      </div>
      <p className="mt-2 text-sm">
        {summary.depart} → {summary.arrive}
        {summary.arrivalNote ? <span className="swan-badge ml-2">{summary.arrivalNote}</span> : null}
        <span className="swan-muted"> · {summary.duration} · local times</span>
      </p>
    </div>
  );
}
