"use client";

import type { TravelPackage } from "@contracts/api";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Logo } from "@/components/Logo";
import { TripMap, type MapStop } from "@/components/map3d/TripMap";
import { getClient } from "@/lib/client";

export default function OverviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [pack, setPack] = useState<TravelPackage | null>(null);
  const [day, setDay] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.getPackage(params.id).then(setPack).catch((err: Error) => setError(err.message));
  }, [client, params.id]);

  if (error) {
    return <main className="swan-app p-6"><p>{error}</p><Link href={`/plan/${params.id}/flights`}>Choose flights</Link></main>;
  }
  if (!pack) return <main className="swan-app p-6">Building your trip…</main>;

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
  }));
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
  ];

  function book() {
    sessionStorage.setItem("roam.booking", JSON.stringify(quotes));
    router.push("/dashboard?book=1");
  }

  return (
    <main className="swan-app relative h-screen overflow-hidden">
      <div className="fixed inset-0 lg:right-[420px]">
        <TripMap stops={[...hotelStops, ...dayStops]} arcs={arcs} focus={hotelStops.length} dayLabel={current?.date ?? "Trip"} />
      </div>
      <section className="swan-sheet relative z-10 mt-[38vh] h-[62vh] overflow-y-auto rounded-t-3xl px-4 py-5 lg:fixed lg:inset-y-0 lg:right-0 lg:mt-0 lg:h-screen lg:w-[420px] lg:rounded-none lg:px-6">
        <Logo />
        <h1 className="mt-4 text-4xl">{pack.itinerary.brief.destination}</h1>
        <p className="swan-muted mt-1">{pack.itinerary.brief.start_date?.slice(0, 10)} – {pack.itinerary.brief.end_date?.slice(0, 10)}</p>
        <p className="mt-3 font-mono text-3xl">{pack.totals.total} {pack.totals.currency}</p>
        {Number(pack.totals.savings) > 0 && <p className="text-sm">Save {pack.totals.savings} on Swan merchants versus the aggregator price.</p>}
        <article className="mt-6">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl">Flights</h2>
            <Link href={`/plan/${params.id}/flights`}>Change</Link>
          </div>
          {pack.outbound && <p className="mt-2">{pack.outbound.carrier} out · {pack.outbound.price} {pack.outbound.currency}</p>}
          {pack.return && <p>{pack.return.carrier} back · {pack.return.price} {pack.return.currency}</p>}
          <a className="mt-1 inline-block underline" href={pack.outbound?.deep_link || "#"}>Book on the airline</a>
        </article>
        <article className="mt-6">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl">Stay</h2>
            <Link href={`/plan/${params.id}/hotels`}>Change</Link>
          </div>
          {pack.hotels.map((stay) => (
            <p key={stay.offer.id} className="mt-2">{stay.offer.name} · {stay.check_in} to {stay.check_out}</p>
          ))}
          {pack.hotels.some((stay) => stay.offer.deep_link) && (
            <a className="mt-1 inline-block underline" href={pack.hotels.find((stay) => stay.offer.deep_link)?.offer.deep_link || "#"}>Book on the hotel site</a>
          )}
        </article>
        <div className="mt-6 flex gap-2 overflow-x-auto">
          {pack.itinerary.days.map((item, index) => (
            <button key={item.date} type="button" className="swan-chip shrink-0" aria-pressed={index === day} onClick={() => setDay(index)}>{item.date.slice(5)}</button>
          ))}
        </div>
        <ol className="mt-4 space-y-3">
          {current?.stops.map((stop) => (
            <li key={stop.id}>
              <p className="font-medium">{stop.title}</p>
              <p className="swan-muted font-mono text-sm">{stop.start.slice(11, 16)}–{stop.end.slice(11, 16)}</p>
            </li>
          ))}
        </ol>
        <details className="mt-4">
          <summary>Why Swan chose this</summary>
          <ul className="mt-2 space-y-1 text-sm">{pack.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </details>
        <button type="button" className="swan-btn mt-6 w-full" onClick={book}>Book Swan merchants</button>
        <p className="swan-muted mt-2 text-sm">Flights and chain hotels open the provider. Wallet checkout only includes Swan merchants.</p>
      </section>
    </main>
  );
}
