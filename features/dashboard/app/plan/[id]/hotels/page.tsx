"use client";

import type { HotelOffer, UserProfile } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TripMap, type MapStop } from "@/components/map3d/TripMap";
import { BrandPrompt } from "@/components/swan/BrandPrompt";
import { ChoiceLayout, WhyChips } from "@/components/swan/ChoiceLayout";
import { Photo } from "@/components/swan/Photo";
import { planningPath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { formatMoney, hotelPrice, nightsBetween } from "@/lib/format";

export default function HotelsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [hotels, setHotels] = useState<HotelOffer[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [nights, setNights] = useState(2);
  const [picked, setPicked] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setHotels(view.hotels);
      setPicked(view.hotels[0]?.id ?? null);
      setNights(nightsBetween(view.request.start_date, view.request.end_date));
    }).catch(() => setHotels([]));
    client.getProfile().then(setProfile).catch(() => setProfile(null));
  }, [client, params.id]);

  const stops: MapStop[] = hotels.map((hotel) => ({
    id: hotel.id,
    lat: hotel.location.lat,
    lng: hotel.location.lng,
    label: hotel.name,
    kind: hotel.source === "merchant_mcp" ? "merchant" : "hotel",
  }));
  const chosen = hotels.find((item) => item.id === picked) ?? null;
  const brands = [...new Set(hotels.map((hotel) => hotel.brand).filter(Boolean))] as string[];
  const favourites = profile?.hotels.favourite_brands ?? [];

  async function save(handOff: boolean) {
    if (busy) return;
    setBusy(true);
    try {
      const result = await client.choosePackage(params.id, handOff || !picked ? {} : { hotel_ids: [picked] });
      router.push(planningPath(params.id, result.phase));
    } finally {
      setBusy(false);
    }
  }

  async function toggleBrand(brand: string) {
    if (!profile) return;
    const next = favourites.includes(brand) ? favourites.filter((item) => item !== brand) : [...favourites, brand];
    const updated = { ...profile, hotels: { ...profile.hotels, favourite_brands: next } };
    setProfile(updated);
    await client.putProfile(updated);
  }

  return (
    <ChoiceLayout
      eyebrow="Choose a stay"
      title="Stay"
      map={<TripMap stops={stops} arcs={[]} focus={Math.max(0, hotels.findIndex((item) => item.id === picked))} dayLabel="Hotels near your picks" highlight={hover ?? picked} onSelect={setPicked} />}
      footer={
        <>
          <button type="button" className="swan-btn-quiet" onClick={() => save(true)} disabled={busy}>Let Swanavi handle it</button>
          <button type="button" className="swan-btn" onClick={() => save(false)} disabled={busy || !picked}>
            Continue{chosen ? ` · ${formatMoney(chosen.total, chosen.currency)}` : ""}
          </button>
        </>
      }
    >
      <p className="swan-muted">Ranked by travel time to the places on your plan, then by your brands and budget.</p>
      <ul className="mt-4 space-y-3">
        {hotels.map((hotel, index) => {
          const selected = picked === hotel.id;
          const saving = hotel.quote?.viator_price ? Number(hotel.quote.viator_price) - Number(hotel.quote.amount) : 0;
          return (
            <li key={hotel.id}>
              <button
                type="button"
                className={`swan-card w-full overflow-hidden text-left ${index === 0 ? "swan-card-featured" : ""}`}
                aria-pressed={selected}
                onClick={() => setPicked(hotel.id)}
                onMouseEnter={() => setHover(hotel.id)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(hotel.id)}
                onBlur={() => setHover(null)}
              >
                <div className="sm:flex">
                  <Photo src={hotel.image_url} alt={hotel.name} label={hotel.name} className="h-36 w-full sm:h-auto sm:w-44 sm:shrink-0" />
                  <div className="min-w-0 flex-1 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      {index === 0 ? <span className="swan-badge swan-badge-solid">Recommended</span> : null}
                      {selected ? <span className="swan-badge swan-badge-outline">Selected</span> : null}
                      {hotel.source === "merchant_mcp" ? <span className="swan-badge">Pay from wallet{saving > 0 ? ` · save ${formatMoney(saving, hotel.quote?.currency)}` : ""}</span> : null}
                    </div>
                    <div className="mt-2 flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-xl font-bold tracking-tight">{hotel.name}</p>
                        <p className="swan-muted text-sm">
                          {hotel.brand || "Independent"}{hotel.stars ? ` · ${hotel.stars} stars` : ""}{hotel.area ? ` · ${hotel.area}` : ""}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-2xl font-bold tracking-tight">{formatMoney(hotel.price_per_night, hotel.currency)}</p>
                        <p className="swan-muted text-xs">per night</p>
                      </div>
                    </div>
                    <p className="mt-2 text-sm">
                      {hotel.avg_travel_min_to_attractions > 0 ? `${hotel.avg_travel_min_to_attractions} min on average to your picks · ` : ""}
                      {hotelPrice(hotel, nights).split(" · ")[1]}
                      {hotel.refundable ? " · refundable" : ""}
                    </p>
                    <WhyChips reasons={hotel.why.filter((line) => !/min average to your picks$|^refundable|^Swanavi merchant|vs the aggregator$/.test(line))} />
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      {profile && !favourites.length ? (
        <BrandPrompt question="Prefer a hotel brand?" options={brands} chosen={favourites} onToggle={toggleBrand} />
      ) : null}
    </ChoiceLayout>
  );
}
