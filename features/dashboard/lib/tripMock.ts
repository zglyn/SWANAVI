import type {
  BookingLine,
  BookRequest,
  Candidate,
  CheckoutResult,
  EventLevel,
  EventSource,
  EventType,
  FlightOffer,
  HotelOffer,
  Proposal,
  Quote,
  Suggestion,
  SuggestionAction,
  SuggestionResult,
  TripConversation,
  TripView,
} from "@contracts/api";
import candidatesFx from "@fixtures/candidates_demo.json";
import fixture from "@fixtures/conversation_demo.json";
import flightsFx from "@fixtures/flight_offers.json";
import hotelsFx from "@fixtures/hotel_offers.json";
import { demoCity, flightsFor, freshenProposal, hotelsFor } from "./demoScope";
import { suggestionTitle } from "./format";
import { alternatives, apply, initialState, type Catalog, type Constraints, type TripState } from "./proposalOps";
import { channelOf, mergeLines, quoteOf, withBookings } from "./tripBooking";

export interface TripMockDeps {
  checkout: (quotes: Quote[]) => Promise<CheckoutResult>;
  emit: (source: EventSource, level: EventLevel, type: EventType, message: string, data?: Record<string, unknown>) => Promise<void>;
}

const SCRIPT = fixture as unknown as { conversation: TripConversation; proposal: Proposal };
const PROPOSAL = freshenProposal(structuredClone(SCRIPT.proposal));
const CATALOG: Catalog = {
  flights: flightsFor(flightsFx as FlightOffer[], demoCity.destination),
  hotels: hotelsFor(hotelsFx as HotelOffer[], demoCity.destination),
  candidates: (candidatesFx as { candidates: Candidate[] }).candidates,
};
const SEARCH_MS = 900;
const REPLY_MS = 250;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function read<T>(key: string, fallback: T): T {
  if (typeof sessionStorage === "undefined") return fallback;
  const raw = sessionStorage.getItem(key);
  return raw ? (JSON.parse(raw) as T) : fallback;
}

function write(key: string, value: unknown) {
  sessionStorage.setItem(key, JSON.stringify(value));
}

const store = {
  log: (id: string) => read<SuggestionAction[]>(`swan.trip.${id}.actions`, []),
  setLog: (id: string, log: SuggestionAction[]) => write(`swan.trip.${id}.actions`, log),
  lines: (id: string) => read<BookingLine[]>(`swan.trip.${id}.bookings`, []),
  setLines: (id: string, lines: BookingLine[]) => write(`swan.trip.${id}.bookings`, lines),
  travellers: (id: string) => read<string[]>(`swan.trip.${id}.travellers`, []),
  setTravellers: (id: string, names: string[]) => write(`swan.trip.${id}.travellers`, names),
  attempts: (id: string) => read<Record<string, number>>(`swan.trip.${id}.attempts`, {}),
  setAttempts: (id: string, attempts: Record<string, number>) => write(`swan.trip.${id}.attempts`, attempts),
};

function replay(id: string, log: SuggestionAction[]): TripState {
  const start = initialState(structuredClone({ ...PROPOSAL, trip_id: id }));
  const state = log.reduce((current, action) => apply(current, action, CATALOG), start);
  return { ...state, proposal: withBookings(state.proposal, store.lines(id)) };
}

function withoutLast(log: SuggestionAction[], sid: string): SuggestionAction[] {
  const index = log.map((action) => action.suggestion_id).lastIndexOf(sid);
  return index < 0 ? log : [...log.slice(0, index), ...log.slice(index + 1)];
}

function confirmation(row: Suggestion): string {
  let hash = 7;
  for (const char of row.id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash.toString(36).toUpperCase().padStart(6, "0").slice(-6);
}

export function createTripMock({ checkout, emit }: TripMockDeps) {
  async function payFromWallet(rows: Suggestion[]): Promise<BookingLine[]> {
    const quotes = rows.flatMap((row) => quoteOf(row) ?? []);
    if (!quotes.length) return [];
    const result = await checkout(quotes);
    return rows.map((row): BookingLine => {
      const invoice = quoteOf(row)?.invoice_id;
      const base = { suggestion_id: row.id, channel: "wallet" as const, error: null, violations: [] };
      if (result.status === "success") {
        const booking = result.bookings.find((item) => item.invoice_id === invoice);
        return { ...base, status: "booked", confirmation_code: booking?.confirmation_code ?? null };
      }
      if (result.status === "blocked") {
        const violations = (result.decision?.violations ?? []).filter((item) => item.invoice_id === null || item.invoice_id === invoice);
        return { ...base, status: "blocked", confirmation_code: null, violations };
      }
      return { ...base, status: "failed", confirmation_code: null, error: "The ledger did not settle the payment. Nothing was charged." };
    });
  }

  async function bookWithProviders(id: string, rows: Suggestion[]): Promise<BookingLine[]> {
    const party = SCRIPT.conversation.brief.travellers ?? 1;
    const names = store.travellers(id);
    const attempts = store.attempts(id);
    const flaky = rows.find((row) => row.kind === "attraction")?.id;
    const lines: BookingLine[] = [];
    for (const row of rows) {
      const title = suggestionTitle(row);
      attempts[row.id] = (attempts[row.id] ?? 0) + 1;
      const base = { suggestion_id: row.id, channel: "external" as const, confirmation_code: null };
      const line: BookingLine =
        row.kind === "flight" && names.length < party
          ? { ...base, status: "needs_user", error: `The airline needs the names of ${party === 2 ? "both" : `all ${party}`} travellers.` }
          : row.id === flaky && attempts[row.id] === 1
            ? { ...base, status: "failed", error: `${title}'s ticket site did not answer.` }
            : { ...base, status: "booked", confirmation_code: confirmation(row), error: null };
      lines.push(line);
      store.setLines(id, mergeLines(store.lines(id), [line]));
      store.setAttempts(id, attempts);
      if (line.status === "needs_user") await emit("agent", "warning", "booking.needs_user", `${title} needs traveller names`, { line });
      else if (line.status === "failed") await emit("agent", "error", "booking.failed", `${title} could not be booked`, { line });
      else await emit("agent", "success", "booking.confirmed", `${title} booked, code ${line.confirmation_code}`, { line });
    }
    return lines;
  }

  return {
    async getTrip(id: string): Promise<TripView> {
      return {
        conversation: { ...SCRIPT.conversation, trip_id: id },
        proposal: replay(id, store.log(id)).proposal,
        bookings: store.lines(id),
      };
    },
    async suggestionAlternatives(id: string, sid: string, constraints: Constraints = {}) {
      await sleep(REPLY_MS);
      return alternatives(replay(id, store.log(id)), sid, constraints, CATALOG);
    },
    async actOnSuggestion(id: string, action: SuggestionAction): Promise<SuggestionResult> {
      const required = SCRIPT.proposal.suggestions.find((item) => item.id === action.suggestion_id)?.required;
      await sleep(action.action === "reject" && required ? SEARCH_MS : REPLY_MS);
      const log = store.log(id);
      const before = replay(id, log);
      const row = before.proposal.suggestions.find((item) => item.id === action.suggestion_id);
      if (!row || row.status === "booked") return { proposal: before.proposal, alternatives: [] };
      if (action.action === "modify" && !action.alternative_id) {
        const constraints = { ...(action.constraints as Constraints | null), text: action.text ?? undefined };
        return { proposal: before.proposal, alternatives: alternatives(before, action.suggestion_id, constraints, CATALOG) };
      }
      const next = action.action === "undo" ? withoutLast(log, action.suggestion_id) : [...log, action];
      const after = replay(id, next);
      if (JSON.stringify(after.proposal) !== JSON.stringify(before.proposal)) store.setLog(id, next);
      return { proposal: after.proposal, alternatives: [] };
    },
    async acceptAll(id: string): Promise<Proposal> {
      await sleep(REPLY_MS);
      const log = store.log(id);
      const open = replay(id, log).proposal.suggestions.filter((row) => row.status === "proposed" || row.status === "replaced");
      const next = [...log, ...open.map((row): SuggestionAction => ({ suggestion_id: row.id, action: "accept" }))];
      store.setLog(id, next);
      return replay(id, next).proposal;
    },
    async bookTrip(id: string, request: BookRequest) {
      if (request.travellers?.length) store.setTravellers(id, request.travellers);
      const rows = replay(id, store.log(id)).proposal.suggestions.filter(
        (row) => row.status === "accepted" && channelOf(row) === request.channel,
      );
      const lines = request.channel === "wallet" ? await payFromWallet(rows) : await bookWithProviders(id, rows);
      store.setLines(id, mergeLines(store.lines(id), lines));
      return { ok: true };
    },
  };
}
