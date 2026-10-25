"use client";

import type { HotelOffer } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TripMap } from "@/components/map3d/TripMap";
import { SwanShell, phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";

export default function HotelsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [hotels, setHotels] = useState<HotelOffer[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(false);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setHotels(view.hotels);
      setPicked(view.hotels[0]?.id ?? null);
    }).catch(() => setHotels([]));
  }, [client, params.id]);

  const stops = hotels.map((hotel) => ({
    id: hotel.id,
    lat: hotel.location.lat,
    lng: hotel.location.lng,
    label: hotel.name,
    kind: hotel.source === "merchant_mcp" ? "merchant" as const : "hotel" as const,
  }));

  async function save(handOff: boolean) {
    const result = await client.choosePackage(params.id, handOff || !picked ? {} : { hotel_ids: [picked] });
    router.push(phasePath(params.id, result.phase));
  }

  return (
    <SwanShell>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-4xl">Stay</h1>
        <button type="button" className="swan-chip lg:hidden" onClick={() => setShowMap((value) => !value)}>{showMap ? "List" : "Map"}</button>
      </div>
      <div className={`mb-4 h-72 ${showMap ? "block" : "hidden"} lg:block`}>
        <TripMap stops={stops} arcs={[]} focus={Math.max(0, hotels.findIndex((item) => item.id === picked))} dayLabel="Hotels" />
      </div>
      <button type="button" className="swan-btn-ghost mb-4" onClick={() => save(true)}>Let Swanavi handle it</button>
      <ul className="space-y-3">
        {hotels.map((hotel, index) => (
          <li key={hotel.id}>
            <button type="button" className="swan-line w-full rounded-2xl border p-4 text-left" aria-pressed={picked === hotel.id} onClick={() => setPicked(hotel.id)} onMouseEnter={() => setPicked(hotel.id)}>
              {index === 0 && <span className="swan-chip">Recommended</span>}
              <p className="mt-2 text-lg font-medium">{hotel.name}</p>
              <p className="swan-muted text-sm">{hotel.brand || "Independent"} · {hotel.stars ?? "–"} stars · {hotel.avg_travel_min_to_attractions} min average · {hotel.total} {hotel.currency}</p>
              <p className="mt-1 text-sm">{hotel.why.join(" · ")}</p>
              {hotel.source === "merchant_mcp" && hotel.quote?.viator_price && (
                <p className="mt-2 text-sm font-medium">Swanavi merchant: pay with wallet, save {Number(hotel.quote.viator_price) - Number(hotel.quote.amount)} {hotel.quote.currency}</p>
              )}
              {hotel.refundable && <p className="text-sm">Refundable</p>}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="swan-btn mt-6" onClick={() => save(false)}>Use this stay</button>
    </SwanShell>
  );
}
