"use client";

import type { FlightOffer, UserProfile } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ChoiceFlow,
  ChoiceNote,
  ChoicePill,
  ChoicePills,
  ChoiceRow,
  ChoiceSection,
  ChoiceStack,
  ChoiceSub,
} from "@/components/choice/ChoiceFlow";
import { BrandPrompt } from "@/components/swan/BrandPrompt";
import { planningPath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { airlineName, formatMoney, summarizeFlight } from "@/lib/format";

type Direction = "outbound" | "return";

export default function FlightsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [flights, setFlights] = useState<FlightOffer[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [outbound, setOutbound] = useState<string | null>(null);
  const [inbound, setInbound] = useState<string | null>(null);
  const [direction, setDirection] = useState<Direction>("outbound");
  const [nonstop, setNonstop] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setFlights(view.flights);
      setOutbound(view.flights.find((item) => item.direction === "outbound")?.id ?? null);
      setInbound(view.flights.find((item) => item.direction === "return")?.id ?? null);
    }).catch(() => setFlights([]));
    client.getProfile().then(setProfile).catch(() => setProfile(null));
  }, [client, params.id]);

  const chosenOut = flights.find((item) => item.id === outbound) ?? null;
  const chosenBack = flights.find((item) => item.id === inbound) ?? null;
  const total = [chosenOut, chosenBack].reduce((sum, offer) => sum + (offer ? Number(offer.price) : 0), 0);
  const currency = chosenOut?.currency ?? chosenBack?.currency ?? "USD";
  const carriers = [...new Set(flights.map((offer) => offer.carrier))];
  const favourites = profile?.flights.favourite_airlines ?? [];

  async function save(handOff: boolean) {
    if (busy) return;
    setBusy(true);
    try {
      const result = await client.choosePackage(params.id, handOff ? {} : { outbound_id: outbound, return_id: inbound });
      router.push(planningPath(params.id, result.phase));
    } finally {
      setBusy(false);
    }
  }

  async function toggleAirline(code: string) {
    if (!profile) return;
    const next = favourites.includes(code) ? favourites.filter((item) => item !== code) : [...favourites, code];
    const updated = { ...profile, flights: { ...profile.flights, favourite_airlines: next } };
    setProfile(updated);
    await client.putProfile(updated);
  }

  const visible = flights.filter((item) => item.direction === direction && (!nonstop || item.stops === 0));
  const selectedId = direction === "outbound" ? outbound : inbound;
  const select = (id: string) => {
    if (direction === "outbound") {
      setOutbound(id);
      setDirection("return");
    } else {
      setInbound(id);
    }
  };

  return (
    <ChoiceFlow
      title="Flights"
      action={busy ? "Saving…" : `Continue · ${formatMoney(total, currency)}`}
      onAction={() => save(false)}
      actionDisabled={busy || !outbound}
    >
      <ChoiceSection>
        <ChoiceRow pressed={false} onClick={() => save(true)}>Let Swanavi handle it</ChoiceRow>
      </ChoiceSection>
      <ChoiceSection>
        <ChoicePills>
          {(["outbound", "return"] as Direction[]).map((item) => {
            const picked = item === "outbound" ? chosenOut : chosenBack;
            return (
              <ChoicePill key={item} pressed={direction === item} onClick={() => setDirection(item)}>
                {item === "outbound" ? "Outbound" : "Return"}{picked ? ` · ${formatMoney(picked.price, picked.currency)}` : ""}
              </ChoicePill>
            );
          })}
          <ChoicePill pressed={nonstop} onClick={() => setNonstop((value) => !value)}>Nonstop only</ChoicePill>
        </ChoicePills>
      </ChoiceSection>
      <ChoiceSection title={direction === "outbound" ? "Outbound" : "Return"}>
        <ChoiceStack as="ul">
          {visible.map((offer, index) => {
            const summary = summarizeFlight(offer);
            return (
              <li key={offer.id}>
                <ChoiceRow pressed={selectedId === offer.id} onClick={() => select(offer.id)}>
                  {summary.depart} → {summary.arrive}{summary.arrivalNote ? ` ${summary.arrivalNote}` : ""}
                  <ChoiceSub>
                    {index === 0 ? "Recommended · " : ""}
                    {summary.airline} · {summary.flightNumbers} · {summary.route} · {summary.departDay}
                  </ChoiceSub>
                  <ChoiceSub>
                    {summary.stops} · {summary.duration} · {offer.fare_conditions.refundable ? "Refundable" : "Non-refundable"} · {formatMoney(offer.price, offer.currency)}
                  </ChoiceSub>
                  {offer.why.length ? <ChoiceSub>{offer.why.join(" · ")}</ChoiceSub> : null}
                </ChoiceRow>
              </li>
            );
          })}
        </ChoiceStack>
        {!visible.length ? <ChoiceNote>No {direction} flights match. Try allowing a stop.</ChoiceNote> : null}
      </ChoiceSection>
      {profile && !favourites.length ? (
        <BrandPrompt
          question="Prefer an airline?"
          options={carriers.map(airlineName)}
          chosen={favourites.map(airlineName)}
          onToggle={(name) => {
            const code = carriers.find((item) => airlineName(item) === name);
            if (code) toggleAirline(code);
          }}
        />
      ) : null}
    </ChoiceFlow>
  );
}
