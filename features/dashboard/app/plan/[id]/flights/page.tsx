"use client";

import type { FlightOffer } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TripMap } from "@/components/map3d/TripMap";
import { SwanShell, phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";

export default function FlightsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [flights, setFlights] = useState<FlightOffer[]>([]);
  const [outbound, setOutbound] = useState<string | null>(null);
  const [inbound, setInbound] = useState<string | null>(null);
  const [stops, setStops] = useState<"any" | "0">("any");
  const [showMap, setShowMap] = useState(false);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setFlights(view.flights);
      const out = view.flights.find((item) => item.direction === "outbound");
      const back = view.flights.find((item) => item.direction === "return");
      setOutbound(out?.id ?? null);
      setInbound(back?.id ?? null);
    }).catch(() => setFlights([]));
  }, [client, params.id]);

  const chosen = flights.find((item) => item.id === outbound);
  const arc = chosen?.segments[0].from_place.location && chosen.segments[0].to_place.location
    ? [{ from: [chosen.segments[0].from_place.location.lng, chosen.segments[0].from_place.location.lat] as [number, number], to: [chosen.segments[0].to_place.location.lng, chosen.segments[0].to_place.location.lat] as [number, number] }]
    : [];

  async function save(handOff: boolean) {
    const result = await client.choosePackage(params.id, handOff ? {} : { outbound_id: outbound, return_id: inbound });
    router.push(phasePath(params.id, result.phase));
  }

  function list(direction: "outbound" | "return", selected: string | null, set: (id: string) => void) {
    return flights.filter((item) => item.direction === direction && (stops === "any" || item.stops === 0)).map((item, index) => {
      const first = item.segments[0];
      const last = item.segments[item.segments.length - 1];
      return (
        <li key={item.id}>
          <button type="button" className="swan-line w-full rounded-2xl border p-4 text-left" aria-pressed={selected === item.id} onClick={() => set(item.id)}>
            {index === 0 && <span className="swan-chip">Recommended</span>}
            <p className="mt-2 font-medium">{item.carrier} · {first.depart_at.slice(11, 16)}–{last.arrive_at.slice(11, 16)}</p>
            <p className="swan-muted text-sm">{item.stops === 0 ? "Nonstop" : `${item.stops} stop`} · {Math.round(item.duration_min / 60)}h · {item.price} {item.currency}</p>
            <p className="mt-1 text-sm">{item.why.join(" · ") || (item.fare_conditions.refundable ? "Refundable" : "Fare rules vary")}</p>
          </button>
        </li>
      );
    });
  }

  return (
    <SwanShell>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-4xl">Flights</h1>
        <button type="button" className="swan-chip lg:hidden" onClick={() => setShowMap((value) => !value)}>{showMap ? "List" : "Map"}</button>
      </div>
      <div className={`${showMap ? "block" : "hidden"} mb-4 h-64 lg:hidden`}>
        <TripMap stops={[]} arcs={arc} focus={0} dayLabel="Flight" />
      </div>
      <button type="button" className="swan-btn-ghost mb-4" onClick={() => save(true)}>Let Swan handle it</button>
      <div className="mb-3 flex gap-2">
        <button type="button" className="swan-chip" aria-pressed={stops === "any"} onClick={() => setStops("any")}>Any stops</button>
        <button type="button" className="swan-chip" aria-pressed={stops === "0"} onClick={() => setStops("0")}>Nonstop</button>
      </div>
      <h2 className="text-2xl">Outbound</h2>
      <ul className="mt-2 space-y-2">{list("outbound", outbound, setOutbound)}</ul>
      <h2 className="mt-6 text-2xl">Return</h2>
      <ul className="mt-2 space-y-2">{list("return", inbound, setInbound)}</ul>
      <button type="button" className="swan-btn mt-6" onClick={() => save(false)}>Use these flights</button>
    </SwanShell>
  );
}
