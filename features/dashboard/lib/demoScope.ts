import type { FlightOffer, HotelOffer, Proposal, Quote } from "@contracts/api";
import demo from "@fixtures/demo_city.json";

export const demoCity = demo;

const NAMES = [demo.destination, ...demo.aliases].map((name) => name.toLowerCase());
const DEMO_MERCHANTS = new Set(demo.merchants.map((row) => row.id));

export function namesDemo(text: string | null | undefined): boolean {
  const lower = (text ?? "").toLowerCase();
  return NAMES.some((name) => lower.includes(name));
}

export function isKyoto(text: string | null | undefined): boolean {
  return (text ?? "").toLowerCase().includes("kyoto");
}

function km(lat: number, lng: number, otherLat: number, otherLng: number): number {
  const rad = Math.PI / 180;
  const dLat = (otherLat - lat) * rad;
  const dLng = (otherLng - lng) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat * rad) * Math.cos(otherLat * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function airportsFor(destination: string): Set<string> | null {
  const text = destination.toLowerCase();
  if (namesDemo(destination)) return new Set(demo.airports);
  if (text.includes("kyoto") || text.includes("osaka")) return new Set(["KIX", "ITM"]);
  if (text.includes("tokyo")) return new Set(["HND", "NRT"]);
  return null;
}

function centerFor(destination: string): { lat: number; lng: number } | null {
  const text = destination.toLowerCase();
  if (namesDemo(destination)) return demo.center;
  if (text.includes("kyoto")) return { lat: 35.0116, lng: 135.7681 };
  if (text.includes("osaka")) return { lat: 34.6937, lng: 135.5023 };
  if (text.includes("tokyo")) return { lat: 35.6762, lng: 139.6503 };
  return null;
}

export function flightsFor(offers: FlightOffer[], destination: string): FlightOffer[] {
  const airports = airportsFor(destination);
  if (!airports) return offers;
  return offers.filter((offer) => offer.segments.some((segment) => {
    const from = segment.from_place.code ?? "";
    const to = segment.to_place.code ?? "";
    return airports.has(from) || airports.has(to);
  }));
}

export function hotelsFor(offers: HotelOffer[], destination: string): HotelOffer[] {
  const center = centerFor(destination);
  if (!center) return offers;
  return offers.filter((offer) => km(center.lat, center.lng, offer.location.lat, offer.location.lng) <= 80);
}

export function displayCurrency(merchantId: string, currency: string): string {
  return DEMO_MERCHANTS.has(merchantId) ? demo.currency : currency;
}

function freshenStamp(slotEnd: string, now: number, hours: number): string {
  const end = Date.parse(slotEnd);
  return new Date(Math.max(now, end) + hours * 3_600_000).toISOString();
}

export function freshenQuote<T extends Quote>(quote: T, now = Date.now()): T {
  return {
    ...quote,
    expires_at: freshenStamp(quote.slot_end, now, demo.quote_valid_hours),
    cancel_after: new Date(now + demo.escrow_cancel_after_hours * 3_600_000).toISOString(),
  };
}

export function freshenProposal(proposal: Proposal, now = Date.now()): Proposal {
  const place = proposal.package.itinerary.brief.destination;
  if (proposal.package.plan_id !== demo.plan_id && !namesDemo(place)) return proposal;
  const next = structuredClone(proposal);
  for (const day of next.package.itinerary.days) {
    for (const stop of day.stops) {
      if (stop.quote) stop.quote = freshenQuote(stop.quote, now);
    }
  }
  for (const stay of next.package.hotels) {
    if (stay.offer.quote) stay.offer.quote = freshenQuote(stay.offer.quote, now);
  }
  for (const row of next.suggestions) {
    if (row.kind === "attraction" && row.item.quote) row.item.quote = freshenQuote(row.item.quote, now);
    if (row.kind === "hotel" && row.item.offer.quote) row.item.offer.quote = freshenQuote(row.item.offer.quote, now);
  }
  return next;
}
