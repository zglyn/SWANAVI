import type { FlightOffer, HotelOffer, Leg, Suggestion, TravelSegment } from "@contracts/api";

export function suggestionTitle(row: Suggestion): string {
  if (row.kind === "flight") return flightLabel(row.item);
  if (row.kind === "hotel") return row.item.offer.name;
  return row.item.title;
}

export const fmt = (v: string | number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(digits);

export const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Tokyo" });

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const short = (hash: string) => `${hash.slice(0, 6)}…${hash.slice(-4)}`;

const DOLLAR_LIKE = new Set(["USD", "RLUSD", "USDC"]);

export function formatMoney(amount: string | number | null | undefined, currency = "USD"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const value = Number(amount);
  if (Number.isNaN(value)) return String(amount);
  const whole = Math.abs(value - Math.round(value)) < 0.005;
  if (DOLLAR_LIKE.has(currency.toUpperCase())) {
    return `$${value.toLocaleString("en-US", { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 })}`;
  }
  return `${value.toLocaleString("en-US", { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 })} ${currency}`;
}

function dateOnly(value: string): Date {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

const WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", timeZone: "UTC" });
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short", timeZone: "UTC" });

export function formatDay(value: string, withMonth = true): string {
  const date = dateOnly(value);
  const base = `${WEEKDAY.format(date)} ${date.getUTCDate()}`;
  return withMonth ? `${base} ${MONTH.format(date)}` : base;
}

export function formatDateRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start) return "";
  if (!end || end.slice(0, 10) === start.slice(0, 10)) return formatDay(start);
  const first = dateOnly(start);
  const last = dateOnly(end);
  const sameMonth = first.getUTCMonth() === last.getUTCMonth() && first.getUTCFullYear() === last.getUTCFullYear();
  return `${formatDay(start, !sameMonth)} – ${formatDay(end)}`;
}

export function nightsBetween(start: string, end: string): number {
  return Math.max(1, Math.round((dateOnly(end).getTime() - dateOnly(start).getTime()) / 86_400_000));
}

export const AIRLINES: Record<string, string> = {
  JL: "Japan Airlines",
  NH: "ANA",
  UA: "United",
  AA: "American",
  DL: "Delta",
  AS: "Alaska",
  BA: "British Airways",
  LH: "Lufthansa",
  AF: "Air France",
  KL: "KLM",
  SQ: "Singapore Airlines",
  CX: "Cathay Pacific",
  QF: "Qantas",
  EK: "Emirates",
};

export const airlineName = (code: string | null | undefined) => (code ? AIRLINES[code.toUpperCase()] ?? code : "");

const TZ_BY_AIRPORT: Record<string, string> = {
  SFO: "America/Los_Angeles",
  OAK: "America/Los_Angeles",
  SJC: "America/Los_Angeles",
  LAX: "America/Los_Angeles",
  SEA: "America/Los_Angeles",
  JFK: "America/New_York",
  EWR: "America/New_York",
  BOS: "America/New_York",
  ORD: "America/Chicago",
  KIX: "Asia/Tokyo",
  ITM: "Asia/Tokyo",
  HND: "Asia/Tokyo",
  NRT: "Asia/Tokyo",
  LHR: "Europe/London",
  CDG: "Europe/Paris",
};

export function airportZone(code: string | null | undefined): string | undefined {
  return code ? TZ_BY_AIRPORT[code.toUpperCase()] : undefined;
}

export function formatClock(iso: string, zone?: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: zone });
}

function localDate(iso: string, zone?: string): string {
  return new Date(iso).toLocaleDateString("en-CA", { timeZone: zone });
}

export function dayOffset(departIso: string, departZone: string | undefined, arriveIso: string, arriveZone: string | undefined): number {
  return Math.round((dateOnly(localDate(arriveIso, arriveZone)).getTime() - dateOnly(localDate(departIso, departZone)).getTime()) / 86_400_000);
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export interface FlightSummary {
  airline: string;
  route: string;
  depart: string;
  arrive: string;
  arrivalNote: string;
  departDay: string;
  stops: string;
  duration: string;
  flightNumbers: string;
}

export function summarizeFlight(offer: FlightOffer): FlightSummary {
  const first: TravelSegment = offer.segments[0];
  const last: TravelSegment = offer.segments[offer.segments.length - 1];
  const from = first.from_place.code ?? first.from_place.name;
  const to = last.to_place.code ?? last.to_place.name;
  const departZone = airportZone(first.from_place.code);
  const arriveZone = airportZone(last.to_place.code);
  const offset = dayOffset(first.depart_at, departZone, last.arrive_at, arriveZone);
  const arrivalNote = offset > 0 ? `+${offset} day${offset > 1 ? "s" : ""}` : offset < 0 ? `${offset} day` : "";
  const layovers = offer.segments.slice(0, -1).map((segment) => segment.to_place.code ?? segment.to_place.name);
  return {
    airline: airlineName(offer.carrier),
    route: `${from} → ${to}`,
    depart: formatClock(first.depart_at, departZone),
    arrive: formatClock(last.arrive_at, arriveZone),
    arrivalNote,
    departDay: formatDay(localDate(first.depart_at, departZone)),
    stops: offer.stops === 0 ? "Nonstop" : layovers.length ? `${offer.stops} stop via ${layovers.join(", ")}` : `${offer.stops} stop`,
    duration: formatDuration(offer.duration_min),
    flightNumbers: offer.segments.map((segment) => segment.number).filter(Boolean).join(", "),
  };
}

export function flightLabel(offer: FlightOffer): string {
  const summary = summarizeFlight(offer);
  return `${summary.airline} · ${summary.route}`;
}

export function hotelPrice(offer: HotelOffer, nights?: number): string {
  const count = nights ?? (offer.check_in && offer.check_out ? nightsBetween(offer.check_in, offer.check_out) : Math.round(Number(offer.total) / Number(offer.price_per_night)) || 1);
  return `${formatMoney(offer.price_per_night, offer.currency)} / night · ${formatMoney(offer.total, offer.currency)} for ${count} night${count === 1 ? "" : "s"}`;
}

const MODE_LABEL: Record<string, string> = {
  walk: "Walk",
  bike: "Bike",
  transit: "Train or bus",
  taxi: "Taxi",
  car: "Drive",
};

export function legLabel(leg: Leg): string {
  return `${MODE_LABEL[leg.mode] ?? leg.mode} · ${formatDuration(leg.minutes)}`;
}
