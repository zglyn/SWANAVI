import type { GeoPoint, Itinerary, Leg, Stop, TravelPackage } from "@contracts/api";
import { nearestCityName, resolveKnownPlace } from "@/lib/places";

export interface RouteStop {
  id: string;
  title: string;
  kind: Stop["kind"];
  lat: number | null;
  lng: number | null;
}

export type DirectionsProfile = "walking" | "driving";

export interface RouteLeg {
  profile: DirectionsProfile;
  fromId: string;
  toId: string;
}

export function orderedRoute(pack: TravelPackage): { stops: RouteStop[]; legs: RouteLeg[] } {
  const stops: RouteStop[] = [];
  for (const day of pack.itinerary.days) {
    for (const stop of day.stops) {
      const point = pointFor(pack, stop);
      stops.push({
        id: stop.id,
        title: stop.title,
        kind: stop.kind,
        lat: point?.lat ?? null,
        lng: point?.lng ?? null,
      });
    }
  }

  const legs: RouteLeg[] = [];
  let previous: RouteStop | null = null;
  for (const stop of stops) {
    if (stop.lat == null || stop.lng == null) {
      continue;
    }
    if (previous?.lat != null && previous.lng != null) {
      const planned = findLeg(pack.itinerary, previous.id, stop.id);
      legs.push({
        fromId: previous.id,
        toId: stop.id,
        profile: legProfile(planned, { lat: previous.lat, lng: previous.lng }, { lat: stop.lat, lng: stop.lng }),
      });
    }
    previous = stop;
  }
  return { stops, legs };
}

export function legProfile(leg: Leg | undefined, from: GeoPoint, to: GeoPoint): DirectionsProfile {
  const km = leg && leg.distance_km > 0 ? leg.distance_km : haversineKm(from, to);
  if (leg?.mode === "walk" || leg?.mode === "bike") return "walking";
  if (leg?.mode === "taxi" || leg?.mode === "car") return "driving";
  if (km >= 30) return "driving";
  const fromCity = nearestCityName(from.lat, from.lng);
  const toCity = nearestCityName(to.lat, to.lng);
  if (fromCity && toCity && fromCity === toCity) return "walking";
  return km >= 18 ? "driving" : "walking";
}

export function sliceLine(coords: [number, number][], t: number): [number, number][] {
  if (coords.length === 0) return [];
  if (t <= 0) return [coords[0], coords[0]];
  if (t >= 1 || coords.length === 1) return coords;
  const lengths: number[] = [];
  let total = 0;
  for (let index = 1; index < coords.length; index += 1) {
    const span = Math.hypot(coords[index][0] - coords[index - 1][0], coords[index][1] - coords[index - 1][1]);
    lengths.push(span);
    total += span;
  }
  if (total === 0) return [coords[0], coords[0]];
  let remain = total * t;
  const out: [number, number][] = [coords[0]];
  for (let index = 0; index < lengths.length; index += 1) {
    const span = lengths[index];
    if (remain <= span) {
      const fraction = span === 0 ? 0 : remain / span;
      const start = coords[index];
      const end = coords[index + 1];
      out.push([start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction]);
      return out;
    }
    remain -= span;
    out.push(coords[index + 1]);
  }
  return coords;
}

export function easeCinema(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return bezier(0.22, 1, 0.36, 1, clamped);
}

export function straightGeometry(stops: RouteStop[]): [number, number][] {
  const line: [number, number][] = [];
  for (const stop of stops) {
    if (stop.lat == null || stop.lng == null) continue;
    const point: [number, number] = [stop.lng, stop.lat];
    const prev = line[line.length - 1];
    if (prev && prev[0] === point[0] && prev[1] === point[1]) continue;
    line.push(point);
  }
  return line;
}

export async function routeGeometry(
  token: string,
  stops: RouteStop[],
  legs: RouteLeg[],
  signal?: AbortSignal,
): Promise<[number, number][]> {
  const placed = stops.filter((stop): stop is RouteStop & { lat: number; lng: number } => stop.lat != null && stop.lng != null);
  const parts: [number, number][][] = [];
  for (let index = 0; index < placed.length - 1; index += 1) {
    const from = placed[index];
    const to = placed[index + 1];
    const profile = legs[index]?.profile ?? "walking";
    parts.push(await legLine(token, profile, from, to, signal));
  }
  return joinLines(parts);
}

function pointFor(pack: TravelPackage, stop: Stop): GeoPoint | null {
  const own = validPoint(stop.location) ?? validPoint(stop.attraction?.location) ?? validPoint(stop.quote?.location);
  if (own) return own;
  const brief = pack.itinerary.brief;
  if (stop.kind === "lodging") {
    const named = brief.lodging?.find((stay) => stop.title.toLowerCase().includes(stay.name.toLowerCase()));
    const stay = validPoint((named ?? brief.lodging?.[0])?.location);
    if (stay) return stay;
    const hotel = pack.hotels.find((item) => stop.title.toLowerCase().includes(item.offer.name.toLowerCase()));
    const hotelPoint = validPoint(hotel?.offer.location);
    if (hotelPoint) return hotelPoint;
  }
  if (stop.kind === "arrival") {
    const hit = validPoint(brief.arrival?.to_place.location) ?? validPoint(brief.arrival?.from_place.location);
    if (hit) return hit;
  }
  if (stop.kind === "departure") {
    const hit = validPoint(brief.departure?.from_place.location) ?? validPoint(brief.departure?.to_place.location);
    if (hit) return hit;
  }
  return resolveKnownPlace(stop.title)
    ?? (stop.attraction?.name ? resolveKnownPlace(stop.attraction.name) : null)
    ?? (stop.quote?.merchant_name ? resolveKnownPlace(stop.quote.merchant_name) : null)
    ?? (stop.quote?.title ? resolveKnownPlace(stop.quote.title) : null);
}

function findLeg(itinerary: Itinerary, fromId: string, toId: string): Leg | undefined {
  for (const day of itinerary.days) {
    const leg = day.legs.find((item) => item.from_stop_id === fromId && item.to_stop_id === toId);
    if (leg) return leg;
  }
  return undefined;
}

function validPoint(point: { lat?: number; lng?: number } | null | undefined): GeoPoint | null {
  if (!point) return null;
  const lat = Number(point.lat);
  const lng = Number(point.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  if (lat === 0 && lng === 0) return null;
  return { lat, lng };
}

function haversineKm(from: GeoPoint, to: GeoPoint) {
  const rad = Math.PI / 180;
  const dLat = (to.lat - from.lat) * rad;
  const dLng = (to.lng - from.lng) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(from.lat * rad) * Math.cos(to.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function legLine(
  token: string,
  profile: DirectionsProfile,
  from: GeoPoint,
  to: GeoPoint,
  signal?: AbortSignal,
): Promise<[number, number][]> {
  const straight: [number, number][] = [[from.lng, from.lat], [to.lng, to.lat]];
  if (!token.startsWith("pk.") || haversineKm(from, to) < 0.04) return straight;
  const path = `${from.lng},${from.lat};${to.lng},${to.lat}`;
  try {
    const response = await fetch(
      `https://api.mapbox.com/directions/v5/mapbox/${profile}/${path}?geometries=geojson&overview=full&access_token=${encodeURIComponent(token)}`,
      { signal },
    );
    if (!response.ok) return straight;
    const body = await response.json() as { routes?: { geometry?: { coordinates?: [number, number][] } }[] };
    const coords = body.routes?.[0]?.geometry?.coordinates;
    if (!coords || coords.length < 2) return straight;
    return coords;
  } catch {
    return straight;
  }
}

function joinLines(parts: [number, number][][]): [number, number][] {
  const out: [number, number][] = [];
  for (const part of parts) {
    for (const coord of part) {
      const prev = out[out.length - 1];
      if (prev && prev[0] === coord[0] && prev[1] === coord[1]) continue;
      out.push(coord);
    }
  }
  return out;
}

function bezier(x1: number, y1: number, x2: number, y2: number, x: number) {
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  const sampleX = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sampleY = (t: number) => ((ay * t + by) * t + cy) * t;
  const slopeX = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  let t = x;
  for (let step = 0; step < 8; step += 1) {
    const delta = sampleX(t) - x;
    const slope = slopeX(t);
    if (Math.abs(delta) < 1e-6) return sampleY(t);
    if (Math.abs(slope) < 1e-6) break;
    t -= delta / slope;
  }
  let lo = 0;
  let hi = 1;
  t = x;
  for (let step = 0; step < 20; step += 1) {
    if (sampleX(t) < x) lo = t;
    else hi = t;
    t = (lo + hi) / 2;
  }
  return sampleY(t);
}
