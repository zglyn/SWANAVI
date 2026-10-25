"use client";

import type { FlightOffer, UserProfile } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TripMap } from "@/components/map3d/TripMap";
import { BrandPrompt } from "@/components/swan/BrandPrompt";
import { ChoiceLayout, WhyChips } from "@/components/swan/ChoiceLayout";
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
  const arcs = [chosenOut, chosenBack].flatMap((offer) => {
    const first = offer?.segments[0];
    const last = offer?.segments[offer.segments.length - 1];
    if (!first?.from_place.location || !last?.to_place.location) return [];
    return [{
      from: [first.from_place.location.lng, first.from_place.location.lat] as [number, number],
      to: [last.to_place.location.lng, last.to_place.location.lat] as [number, number],
    }];
  });
  const airports = [chosenOut?.segments[0].from_place, chosenOut?.segments[chosenOut.segments.length - 1].to_place].flatMap((place) =>
    place?.location ? [{ id: place.code ?? place.name, lat: place.location.lat, lng: place.location.lng, label: place.name, kind: "stop" as const }] : [],
  );
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
    <ChoiceLayout
      eyebrow="Choose flights"
      title="Flights"
      map={<TripMap stops={airports} arcs={arcs} focus={0} dayLabel="Your flights" showToggle={false} />}
      footer={
        <>
          <button type="button" className="swan-btn-quiet" onClick={() => save(true)} disabled={busy}>Let Swanavi handle it</button>
          <button type="button" className="swan-btn" onClick={() => save(false)} disabled={busy || !outbound}>
            Continue · {formatMoney(total, currency)}
          </button>
        </>
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="swan-seg" role="radiogroup" aria-label="Direction">
          {(["outbound", "return"] as Direction[]).map((item) => {
            const picked = item === "outbound" ? chosenOut : chosenBack;
            return (
              <button key={item} type="button" role="radio" aria-checked={direction === item} onClick={() => setDirection(item)}>
                {item === "outbound" ? "Outbound" : "Return"}{picked ? ` · ${formatMoney(picked.price, picked.currency)}` : ""}
              </button>
            );
          })}
        </div>
        <button type="button" className="swan-filter" aria-pressed={nonstop} onClick={() => setNonstop((value) => !value)}>Nonstop only</button>
      </div>

      <ul className="mt-4 space-y-3">
        {visible.map((offer, index) => {
          const summary = summarizeFlight(offer);
          const selected = selectedId === offer.id;
          return (
            <li key={offer.id}>
              <button
                type="button"
                className={`swan-card w-full p-4 text-left ${index === 0 ? "swan-card-featured" : ""}`}
                aria-pressed={selected}
                onClick={() => select(offer.id)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      {index === 0 ? <span className="swan-badge swan-badge-solid">Recommended</span> : null}
                      {selected ? <span className="swan-badge swan-badge-outline">Selected</span> : null}
                    </div>
                    <p className="mt-2 text-2xl font-bold tracking-tight">
                      {summary.depart} → {summary.arrive}
                      {summary.arrivalNote ? <span className="swan-badge ml-2 align-middle">{summary.arrivalNote}</span> : null}
                    </p>
                    <p className="swan-muted mt-1 text-sm">
                      {summary.airline} · {summary.flightNumbers} · {summary.route} · {summary.departDay}
                    </p>
                    <p className="swan-muted text-sm">{summary.stops} · {summary.duration} · {offer.fare_conditions.refundable ? "Refundable" : "Non-refundable"} · local times</p>
                  </div>
                  <p className="shrink-0 text-2xl font-bold tracking-tight">{formatMoney(offer.price, offer.currency)}</p>
                </div>
                <WhyChips reasons={offer.why} />
              </button>
            </li>
          );
        })}
        {!visible.length ? <li className="swan-muted">No {direction} flights match. Try allowing a stop.</li> : null}
      </ul>

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
    </ChoiceLayout>
  );
}
