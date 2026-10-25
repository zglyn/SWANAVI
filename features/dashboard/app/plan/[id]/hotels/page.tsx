"use client";

import type { HotelOffer, UserProfile } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ChoiceFlow,
  ChoiceNote,
  ChoiceRow,
  ChoiceSection,
  ChoiceStack,
  ChoiceSub,
} from "@/components/choice/ChoiceFlow";
import { BrandPrompt } from "@/components/swan/BrandPrompt";
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
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setHotels(view.hotels);
      setPicked(view.hotels[0]?.id ?? null);
      setNights(nightsBetween(view.request.start_date, view.request.end_date));
    }).catch(() => setHotels([]));
    client.getProfile().then(setProfile).catch(() => setProfile(null));
  }, [client, params.id]);

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
    <ChoiceFlow
      title="Stay"
      action={busy ? "Saving…" : `Continue${chosen ? ` · ${formatMoney(chosen.total, chosen.currency)}` : ""}`}
      onAction={() => save(false)}
      actionDisabled={busy || !picked}
    >
      <ChoiceNote>Ranked by travel time to the places on your plan, then by your brands and budget.</ChoiceNote>
      <ChoiceSection>
        <ChoiceStack as="ul">
          <li>
            <ChoiceRow pressed={false} onClick={() => save(true)}>Let Swanavi handle it</ChoiceRow>
          </li>
          {hotels.map((hotel, index) => {
            const saving = hotel.quote?.viator_price ? Number(hotel.quote.viator_price) - Number(hotel.quote.amount) : 0;
            return (
              <li key={hotel.id}>
                <ChoiceRow pressed={picked === hotel.id} onClick={() => setPicked(hotel.id)}>
                  {hotel.name}
                  <ChoiceSub>
                    {index === 0 ? "Recommended · " : ""}
                    {hotel.brand || "Independent"}
                    {hotel.stars ? ` · ${hotel.stars} stars` : ""}
                    {hotel.area ? ` · ${hotel.area}` : ""}
                  </ChoiceSub>
                  <ChoiceSub>
                    {hotel.avg_travel_min_to_attractions > 0 ? `${hotel.avg_travel_min_to_attractions} min on average to your picks · ` : ""}
                    {hotelPrice(hotel, nights)}
                    {hotel.refundable ? " · refundable" : ""}
                  </ChoiceSub>
                  {hotel.source === "merchant_mcp" ? (
                    <ChoiceSub>Pay from wallet{saving > 0 ? ` · save ${formatMoney(saving, hotel.quote?.currency)}` : ""}</ChoiceSub>
                  ) : null}
                  {hotel.why.length ? (
                    <ChoiceSub>
                      {hotel.why.filter((line) => !/min average to your picks$|^refundable|^Swanavi merchant|vs the aggregator$/.test(line)).join(" · ")}
                    </ChoiceSub>
                  ) : null}
                </ChoiceRow>
              </li>
            );
          })}
        </ChoiceStack>
        {!hotels.length ? <ChoiceNote>No stays yet.</ChoiceNote> : null}
      </ChoiceSection>
      {profile && !favourites.length ? (
        <BrandPrompt question="Prefer a hotel brand?" options={brands} chosen={favourites} onToggle={toggleBrand} />
      ) : null}
    </ChoiceFlow>
  );
}
