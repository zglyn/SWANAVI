"use client";

import type { FlightOffer } from "@contracts/api";
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
import { phasePath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";

export default function FlightsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [flights, setFlights] = useState<FlightOffer[]>([]);
  const [outbound, setOutbound] = useState<string | null>(null);
  const [inbound, setInbound] = useState<string | null>(null);
  const [stops, setStops] = useState<"any" | "0">("any");
  const [handOff, setHandOff] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.getSwan(params.id).then((view) => {
      setFlights(view.flights);
      const out = view.flights.find((item) => item.direction === "outbound");
      const back = view.flights.find((item) => item.direction === "return");
      setOutbound(out?.id ?? null);
      setInbound(back?.id ?? null);
      setReady(true);
    }).catch(() => {
      setFlights([]);
      setReady(true);
    });
  }, [client, params.id]);

  async function save(handed: boolean) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await client.choosePackage(params.id, handed ? {} : { outbound_id: outbound, return_id: inbound });
      router.push(phasePath(params.id, result.phase));
    } catch {
      setError("Could not save these flights. Try again.");
      setBusy(false);
    }
  }

  function list(direction: "outbound" | "return", selected: string | null, set: (id: string) => void) {
    return flights.filter((item) => item.direction === direction && (stops === "any" || item.stops === 0)).map((item, index) => {
      const first = item.segments[0];
      const last = item.segments[item.segments.length - 1];
      return (
        <li key={item.id}>
          <ChoiceRow
            pressed={!handOff && selected === item.id}
            onClick={() => {
              setHandOff(false);
              set(item.id);
            }}
          >
            {item.carrier} · {first.depart_at.slice(11, 16)}–{last.arrive_at.slice(11, 16)}
            <ChoiceSub>
              {index === 0 ? "Recommended · " : ""}
              {item.stops === 0 ? "Nonstop" : `${item.stops} stop`} · {Math.round(item.duration_min / 60)}h · {item.price} {item.currency}
            </ChoiceSub>
            <ChoiceSub>{item.why.join(" · ") || (item.fare_conditions.refundable ? "Refundable" : "Fare rules vary")}</ChoiceSub>
          </ChoiceRow>
        </li>
      );
    });
  }

  return (
    <ChoiceFlow
      title="Which flights?"
      action="Continue"
      actionDisabled={busy || !ready || (!handOff && (!outbound || !inbound))}
      onAction={() => save(handOff)}
    >
      <ChoiceSection>
        <ChoiceStack>
          <ChoiceRow pressed={handOff} onClick={() => setHandOff(true)}>
            Let Swanavi handle it
          </ChoiceRow>
        </ChoiceStack>
      </ChoiceSection>
      <ChoiceSection title="Stops">
        <ChoicePills>
          <ChoicePill pressed={stops === "any"} onClick={() => setStops("any")}>Any stops</ChoicePill>
          <ChoicePill pressed={stops === "0"} onClick={() => setStops("0")}>Nonstop</ChoicePill>
        </ChoicePills>
      </ChoiceSection>
      <ChoiceSection title="Outbound">
        {ready && flights.length === 0 ? <ChoiceNote>No flights yet.</ChoiceNote> : null}
        <ChoiceStack as="ul">{list("outbound", outbound, setOutbound)}</ChoiceStack>
      </ChoiceSection>
      <ChoiceSection title="Return">
        <ChoiceStack as="ul">{list("return", inbound, setInbound)}</ChoiceStack>
      </ChoiceSection>
      {error ? <ChoiceNote>{error}</ChoiceNote> : null}
    </ChoiceFlow>
  );
}
