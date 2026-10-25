"use client";

import type { Quote, TravelPackage } from "@contracts/api";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CinematicTrip, QuietScreen } from "@/components/swan/CinematicTrip";
import { getClient } from "@/lib/client";
import { mapboxPublicToken } from "@/lib/mapboxToken";
import { orderedRoute } from "@/lib/tripRoute";

export default function OverviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [pack, setPack] = useState<TravelPackage | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    client.getPackage(params.id).then((found) => {
      if (!cancelled) setPack(found);
    }).catch(() => {
      if (!cancelled) setMissing(true);
    });
    return () => {
      cancelled = true;
    };
  }, [client, params.id]);

  const route = useMemo(() => (pack ? orderedRoute(pack) : null), [pack]);

  if (!pack || !route || route.stops.length === 0) {
    return <QuietScreen line={missing || pack ? "Your trip is not ready yet." : "Building your trip…"} />;
  }

  const trip = pack;
  const planned = route;

  function book() {
    const quotes = [
      ...trip.itinerary.days.flatMap((item) => item.stops.map((stop) => stop.quote).filter((quote): quote is Quote => Boolean(quote))),
      ...trip.hotels.map((stay) => stay.offer.quote).filter((quote): quote is Quote => Boolean(quote)),
    ];
    sessionStorage.setItem("roam.booking", JSON.stringify(quotes));
    router.push("/dashboard?book=1");
  }

  return (
    <CinematicTrip
      destination={trip.itinerary.brief.destination}
      stops={planned.stops}
      legs={planned.legs}
      token={mapboxPublicToken()}
      onBook={book}
    />
  );
}
