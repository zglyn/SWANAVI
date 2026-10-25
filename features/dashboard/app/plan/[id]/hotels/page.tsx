"use client";

import type { HotelOffer } from "@contracts/api";
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
import { phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";

export default function HotelsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [hotels, setHotels] = useState<HotelOffer[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [handOff, setHandOff] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setHotels(view.hotels);
      setPicked(view.hotels[0]?.id ?? null);
      setReady(true);
    }).catch(() => {
      setHotels([]);
      setReady(true);
    });
  }, [client, params.id]);

  async function save(handed: boolean) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await client.choosePackage(params.id, handed || !picked ? {} : { hotel_ids: [picked] });
      router.push(phasePath(params.id, result.phase));
    } catch {
      setError("Could not save this stay. Try again.");
      setBusy(false);
    }
  }

  return (
    <ChoiceFlow
      title="Where should you stay?"
      action="Continue"
      actionDisabled={busy || !ready || (!handOff && !picked)}
      onAction={() => save(handOff)}
    >
      <ChoiceSection>
        <ChoiceStack as="ul">
          <li>
            <ChoiceRow pressed={handOff} onClick={() => setHandOff(true)}>
              Let Swanavi handle it
            </ChoiceRow>
          </li>
          {hotels.map((hotel, index) => (
            <li key={hotel.id}>
              <ChoiceRow
                pressed={!handOff && picked === hotel.id}
                onClick={() => {
                  setHandOff(false);
                  setPicked(hotel.id);
                }}
              >
                {hotel.name}
                <ChoiceSub>
                  {index === 0 ? "Recommended · " : ""}
                  {hotel.brand || "Independent"} · {hotel.stars ?? "–"} stars · {hotel.avg_travel_min_to_attractions} min average · {hotel.total} {hotel.currency}
                </ChoiceSub>
                {hotel.why.length ? <ChoiceSub>{hotel.why.join(" · ")}</ChoiceSub> : null}
                {hotel.source === "merchant_mcp" && hotel.quote?.viator_price ? (
                  <ChoiceSub>
                    Swanavi merchant: pay with wallet, save {Number(hotel.quote.viator_price) - Number(hotel.quote.amount)} {hotel.quote.currency}
                  </ChoiceSub>
                ) : null}
                {hotel.refundable ? <ChoiceSub>Refundable</ChoiceSub> : null}
              </ChoiceRow>
            </li>
          ))}
        </ChoiceStack>
        {ready && hotels.length === 0 ? <ChoiceNote>No stays yet.</ChoiceNote> : null}
        {error ? <ChoiceNote>{error}</ChoiceNote> : null}
      </ChoiceSection>
    </ChoiceFlow>
  );
}
