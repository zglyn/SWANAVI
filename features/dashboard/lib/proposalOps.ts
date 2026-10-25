import type {
  Candidate,
  FlightOffer,
  HotelOffer,
  HotelStay,
  ItineraryDay,
  Leg,
  Proposal,
  Stop,
  Suggestion,
  SuggestionAction,
  TimeOfDayWindow,
  TravelMode,
  TravelPackage,
} from "@contracts/api";

export interface Catalog {
  flights: FlightOffer[];
  hotels: HotelOffer[];
  candidates: Candidate[];
}

export interface Constraints {
  time_of_day?: TimeOfDayWindow;
  max_stops?: number;
  airline?: string;
  cheaper?: boolean;
  max_price?: number;
  min_stars?: number;
  area?: string;
  category?: string;
  text?: string;
}

export interface TripState {
  proposal: Proposal;
  rejected: string[];
}

const WINDOWS: Record<Exclude<TimeOfDayWindow, "any">, [number, number]> = {
  red_eye: [0, 5],
  early_morning: [5, 8],
  morning: [8, 12],
  afternoon: [12, 17],
  evening: [17, 22],
};

const SPEED_KMH: Record<TravelMode, number> = { walk: 4.5, bike: 12, transit: 18, taxi: 22, car: 22 };
const VISITS = new Set(["attraction", "merchant", "transfer"]);
const BUFFER_MIN = 10;

const WORDS: [RegExp, (row: Suggestion) => Constraints][] = [
  [/cheap|less expensive|lower price/i, () => ({ cheaper: true })],
  [/nonstop|non-stop|direct/i, () => ({ max_stops: 0 })],
  [/early morning/i, () => ({ time_of_day: "early_morning" })],
  [/\bmorning\b/i, () => ({ time_of_day: "morning" })],
  [/afternoon/i, () => ({ time_of_day: "afternoon" })],
  [/evening/i, () => ({ time_of_day: "evening" })],
  [/\bgion\b/i, () => ({ area: "Gion" })],
  [/arashiyama/i, () => ({ area: "Arashiyama" })],
  [/downtown|central/i, () => ({ area: "Downtown" })],
  [/food|eat|market/i, () => ({ category: "food" })],
  [/nature|garden|park|walk/i, () => ({ category: "nature" })],
  [/temple|shrine/i, () => ({ category: "temples" })],
  [/museum|castle|history/i, () => ({ category: "museums" })],
  [/similar|like this/i, (row) => (row.kind === "attraction" && row.item.attraction ? { category: row.item.attraction.category } : {})],
];

export function initialState(proposal: Proposal): TripState {
  return { proposal, rejected: [] };
}

export function itemId(row: Suggestion): string {
  if (row.kind === "flight") return row.item.id;
  if (row.kind === "hotel") return row.item.offer.id;
  return row.item.id;
}

export function readConstraints(text: string | null | undefined, row: Suggestion): Constraints {
  if (!text) return {};
  return WORDS.reduce<Constraints>((found, [pattern, read]) => (pattern.test(text) ? { ...read(row), ...found } : found), {});
}

export function alternatives(state: TripState, sid: string, constraints: Constraints, catalog: Catalog): Suggestion[] {
  const row = state.proposal.suggestions.find((item) => item.id === sid);
  if (!row) return [];
  const wanted = { ...readConstraints(constraints.text, row), ...constraints };
  return options(state, row, catalog).filter((option) => fits(option, row, wanted)).slice(0, 3);
}

export function apply(state: TripState, action: SuggestionAction, catalog: Catalog): TripState {
  const row = state.proposal.suggestions.find((item) => item.id === action.suggestion_id);
  if (!row) return state;
  if (action.action === "accept") {
    if (row.status === "rejected" || row.status === "booked") return state;
    return withProposal(state, setRow(state.proposal, row.id, { status: "accepted" }));
  }
  if (action.action === "modify") {
    if (!action.alternative_id || row.status === "rejected" || row.status === "booked") return state;
    const pick = options(state, row, catalog).find((option) => option.id === action.alternative_id);
    return pick ? withProposal(state, swap(state.proposal, row, pick, "accepted")) : state;
  }
  if (action.action === "reject") {
    if (row.status === "rejected" || row.status === "booked") return state;
    if (row.kind === "attraction" || row.kind === "transfer") {
      const dropped = dropStop(state.proposal.package, row.item.id);
      return withProposal(state, retotal(setRow({ ...state.proposal, package: dropped }, row.id, { status: "rejected" })));
    }
    const rejected = { ...state, rejected: [...state.rejected, itemId(row)] };
    const next = options(rejected, row, catalog)[0];
    if (!next) return withProposal(rejected, setRow(state.proposal, row.id, { status: "rejected" }));
    return withProposal(rejected, swap(state.proposal, row, next, "replaced"));
  }
  return state;
}

function withProposal(state: TripState, proposal: Proposal): TripState {
  return { ...state, proposal };
}

function setRow(proposal: Proposal, sid: string, change: Partial<Pick<Suggestion, "status">>): Proposal {
  return {
    ...proposal,
    suggestions: proposal.suggestions.map((row) => (row.id === sid ? { ...row, ...change } : row)),
  };
}

function replaceRow(proposal: Proposal, next: Suggestion): Proposal {
  return { ...proposal, suggestions: proposal.suggestions.map((row) => (row.id === next.id ? next : row)) };
}

function options(state: TripState, row: Suggestion, catalog: Catalog): Suggestion[] {
  const skip = new Set(state.rejected);
  const pkg = state.proposal.package;
  if (row.kind === "flight") {
    const current = row.item;
    [pkg.outbound?.id, pkg.return?.id].forEach((id) => id && skip.add(id));
    return catalog.flights
      .filter((offer) => offer.direction === current.direction && !skip.has(offer.id))
      .sort((left, right) => right.score - left.score)
      .map((offer): Suggestion => ({ id: offer.id, kind: "flight", status: "proposed", item: offer, why: offer.why, alternatives_available: true, required: true }));
  }
  if (row.kind === "hotel") {
    const current = row.item;
    pkg.hotels.forEach((stay) => skip.add(stay.offer.id));
    return catalog.hotels
      .filter((offer) => !skip.has(offer.id))
      .sort((left, right) => right.score - left.score)
      .map((offer): Suggestion => {
        const stay: HotelStay = { offer, check_in: offer.check_in ?? current.check_in, check_out: offer.check_out ?? current.check_out };
        return { id: offer.id, kind: "hotel", status: "proposed", item: stay, why: offer.why, alternatives_available: true, required: true };
      });
  }
  const current = row.item;
  pkg.itinerary.days.forEach((day) => day.stops.forEach((stop) => skip.add(stop.id)));
  state.proposal.suggestions.forEach((item) => skip.add(itemId(item)));
  return catalog.candidates
    .filter((candidate) => candidate.attraction && !skip.has(candidate.id))
    .sort((left, right) => (right.attraction?.popularity ?? 0) - (left.attraction?.popularity ?? 0))
    .map((candidate): Suggestion => {
      const place = candidate.attraction!;
      const stop: Stop = {
        id: candidate.id,
        kind: "attraction",
        start: current.start,
        end: shift(current.start, place.typical_duration_min),
        location: place.location,
        title: place.name,
        attraction: place,
        quote: null,
        required: false,
        status: "proposed",
      };
      const why = [place.category, place.area, `${place.typical_duration_min} min`].filter((line): line is string => Boolean(line));
      return { id: candidate.id, kind: "attraction", status: "proposed", item: stop, why, alternatives_available: true, required: false };
    });
}

function fits(option: Suggestion, row: Suggestion, wanted: Constraints): boolean {
  if (option.kind === "flight" && row.kind === "flight") {
    const offer = option.item;
    const hour = Number(offer.segments[0].depart_at.slice(11, 13));
    if (wanted.time_of_day && wanted.time_of_day !== "any") {
      const [from, to] = WINDOWS[wanted.time_of_day];
      if (hour < from || hour >= to) return false;
    }
    if (wanted.max_stops != null && offer.stops > wanted.max_stops) return false;
    if (wanted.airline && offer.carrier !== wanted.airline) return false;
    if (wanted.max_price != null && Number(offer.price) > wanted.max_price) return false;
    if (wanted.cheaper && Number(offer.price) >= Number(row.item.price)) return false;
    return true;
  }
  if (option.kind === "hotel" && row.kind === "hotel") {
    const offer = option.item.offer;
    if (wanted.max_price != null && Number(offer.price_per_night) > wanted.max_price) return false;
    if (wanted.cheaper && Number(offer.price_per_night) >= Number(row.item.offer.price_per_night)) return false;
    if (wanted.min_stars != null && (offer.stars ?? 0) < wanted.min_stars) return false;
    if (wanted.area && offer.area !== wanted.area) return false;
    return true;
  }
  if (option.kind === "attraction") {
    const place = option.item.attraction;
    if (wanted.category && place?.category !== wanted.category) return false;
    if (wanted.area && place?.area !== wanted.area) return false;
    if (wanted.cheaper && !place?.free) return false;
    return true;
  }
  return false;
}

function swap(proposal: Proposal, row: Suggestion, pick: Suggestion, status: "accepted" | "replaced"): Proposal {
  let pkg = proposal.package;
  if (row.kind === "hotel" && pick.kind === "hotel") pkg = swapHotel(pkg, row.item, pick.item);
  else if (row.kind === "flight" && pick.kind === "flight") pkg = swapFlight(pkg, pick.item);
  else if ((row.kind === "attraction" || row.kind === "transfer") && pick.kind === "attraction") pkg = swapStop(pkg, row.item, pick.item);
  else return proposal;
  const next = { ...row, kind: pick.kind, item: pick.item, why: pick.why, status } as Suggestion;
  return retotal(replaceRow({ ...proposal, package: pkg }, next));
}

function swapHotel(pkg: TravelPackage, current: HotelStay, stay: HotelStay): TravelPackage {
  const oldName = current.offer.name;
  const offer = stay.offer;
  const index = pkg.hotels.findIndex((item) => item.offer.id === current.offer.id);
  const lodging = (pkg.itinerary.brief.lodging ?? []).map((item, at) => (at === index ? { ...item, name: offer.name, location: offer.location } : item));
  const days = pkg.itinerary.days.map((day) => ({
    ...day,
    stops: day.stops.map((stop) => {
      if (stop.kind !== "lodging" || !stop.title.includes(oldName)) return stop;
      return { ...stop, title: stop.title.replace(oldName, offer.name), location: offer.location };
    }),
  }));
  return {
    ...pkg,
    hotels: pkg.hotels.map((item, at) => (at === index ? stay : item)),
    itinerary: { ...pkg.itinerary, brief: { ...pkg.itinerary.brief, lodging }, days },
  };
}

function swapFlight(pkg: TravelPackage, offer: FlightOffer): TravelPackage {
  if (offer.direction === "outbound") {
    const last = offer.segments[offer.segments.length - 1];
    const days = pkg.itinerary.days.map((day, index) => {
      if (index !== 0) return day;
      const arrival = day.stops.find((stop) => stop.kind === "arrival");
      if (!arrival) return day;
      const late = Math.max(0, minutesBetween(arrival.start, last.arrive_at));
      return {
        ...day,
        stops: day.stops.map((stop) => {
          if (stop.kind === "arrival") {
            return { ...stop, start: last.arrive_at, end: shift(last.arrive_at, 20), title: `Arrive ${last.number ?? offer.carrier} at ${last.to_place.name}` };
          }
          return Date.parse(stop.start) > Date.parse(arrival.start) ? moveStop(stop, late) : stop;
        }),
      };
    });
    return { ...pkg, outbound: offer, itinerary: { ...pkg.itinerary, days } };
  }
  const first = offer.segments[0];
  const days = pkg.itinerary.days.map((day) => ({
    ...day,
    stops: day.stops.map((stop) => (stop.kind === "departure"
      ? { ...stop, start: first.depart_at, end: shift(first.depart_at, 20), title: `Depart ${first.number ?? offer.carrier} from ${first.from_place.name}` }
      : stop)),
  }));
  return { ...pkg, return: offer, itinerary: { ...pkg.itinerary, days } };
}

function swapStop(pkg: TravelPackage, current: Stop, next: Stop): TravelPackage {
  return mapDay(pkg, current.id, (day) => {
    const index = day.stops.findIndex((stop) => stop.id === current.id);
    const placed: Stop = { ...next, start: current.start, end: shift(current.start, minutesBetween(next.start, next.end)) };
    const stops = day.stops.map((stop, at) => (at === index ? placed : stop));
    const legs = relink(day, stops);
    const before = legAfter(day.legs, current.id);
    const after = legAfter(legs, placed.id);
    const late = minutesBetween(current.end, placed.end) + (after?.minutes ?? 0) - (before?.minutes ?? 0);
    return { ...day, stops: stops.map((stop, at) => (at > index && VISITS.has(stop.kind) ? moveStop(stop, late) : stop)), legs };
  });
}

function dropStop(pkg: TravelPackage, stopId: string): TravelPackage {
  return mapDay(pkg, stopId, (day) => {
    const index = day.stops.findIndex((stop) => stop.id === stopId);
    const removed = day.stops[index];
    const stops = day.stops.filter((stop) => stop.id !== stopId);
    if (!stops.length) return { ...day, stops: [], legs: [] };
    const legs = relink(day, stops);
    const previous = stops[index - 1];
    const following = stops[index];
    if (!following || !VISITS.has(following.kind)) return { ...day, stops, legs };
    const bridge = previous ? legAfter(legs, previous.id) : undefined;
    const start = previous && bridge ? shift(previous.end, bridge.minutes + BUFFER_MIN) : removed.start;
    const early = Math.max(0, minutesBetween(start, following.start));
    return { ...day, stops: stops.map((stop, at) => (at >= index && VISITS.has(stop.kind) ? moveStop(stop, -early) : stop)), legs };
  });
}

function mapDay(pkg: TravelPackage, stopId: string, change: (day: ItineraryDay) => ItineraryDay): TravelPackage {
  const days = pkg.itinerary.days.map((day) => (day.stops.some((stop) => stop.id === stopId) ? change(day) : day));
  return { ...pkg, itinerary: { ...pkg.itinerary, days } };
}

function relink(day: ItineraryDay, stops: Stop[]): Leg[] {
  return stops.slice(1).map((stop, index) => {
    const from = stops[index];
    const kept = day.legs.find((leg) => leg.from_stop_id === from.id && leg.to_stop_id === stop.id);
    if (kept) return kept;
    const mode = day.legs.find((leg) => leg.from_stop_id === from.id)?.mode ?? "walk";
    return estimateLeg(from, stop, mode);
  });
}

function legAfter(legs: Leg[], stopId: string): Leg | undefined {
  return legs.find((leg) => leg.from_stop_id === stopId);
}

function estimateLeg(from: Stop, to: Stop, mode: TravelMode): Leg {
  const km = haversineKm(from.location.lat, from.location.lng, to.location.lat, to.location.lng);
  const minutes = Math.max(1, Math.round(((km * 1.3) / SPEED_KMH[mode]) * 60 + (mode === "transit" ? 8 : 0)));
  return { from_stop_id: from.id, to_stop_id: to.id, mode, minutes, distance_km: Math.round(km * 10) / 10, source: "estimate" };
}

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(a));
}

export function retotal(proposal: Proposal): Proposal {
  const pkg = proposal.package;
  const flights = [pkg.outbound, pkg.return].reduce((sum, offer) => sum + (offer ? Number(offer.price) : 0), 0);
  const hotels = pkg.hotels.reduce((sum, stay) => sum + Number(stay.offer.total), 0);
  const activities = pkg.itinerary.days.reduce(
    (sum, day) => sum + day.stops.reduce((inner, stop) => inner + (stop.quote ? Number(stop.quote.amount) : 0), 0),
    0,
  );
  const savings = pkg.hotels.reduce((sum, stay) => {
    const quote = stay.offer.quote;
    return sum + (quote?.viator_price ? Number(quote.viator_price) - Number(quote.amount) : 0);
  }, 0);
  const totals = {
    ...proposal.totals,
    flights: flights.toFixed(2),
    hotels: hotels.toFixed(2),
    activities: activities.toFixed(2),
    total: (flights + hotels + activities).toFixed(2),
    savings: savings.toFixed(2),
  };
  return { ...proposal, totals };
}

function moveStop(stop: Stop, minutes: number): Stop {
  if (!minutes) return stop;
  return { ...stop, start: shift(stop.start, minutes), end: shift(stop.end, minutes) };
}

function minutesBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 60000);
}

export function shift(iso: string, minutes: number): string {
  const suffix = iso.slice(19);
  const sign = suffix.startsWith("-") ? -1 : 1;
  const [hours, mins] = suffix === "Z" || !suffix ? [0, 0] : suffix.slice(1).split(":").map(Number);
  const offset = sign * (hours * 60 + mins);
  const local = new Date(Date.parse(iso) + (minutes + offset) * 60000).toISOString().slice(0, 19);
  return local + (suffix || "Z");
}
