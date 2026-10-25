import type {
  Candidate,
  FlightOffer,
  HotelOffer,
  Proposal,
  SuggestionAction,
  SuggestionResult,
  TripConversation,
  TripView,
} from "@contracts/api";
import candidatesFx from "@fixtures/candidates_kyoto.json";
import fixture from "@fixtures/conversation_kyoto.json";
import flightsFx from "@fixtures/flight_offers.json";
import hotelsFx from "@fixtures/hotel_offers.json";
import { alternatives, apply, initialState, type Catalog, type Constraints, type TripState } from "./proposalOps";

const SCRIPT = fixture as unknown as { conversation: TripConversation; proposal: Proposal };
const CATALOG: Catalog = {
  flights: flightsFx as FlightOffer[],
  hotels: hotelsFx as HotelOffer[],
  candidates: (candidatesFx as { candidates: Candidate[] }).candidates,
};
const SEARCH_MS = 900;
const REPLY_MS = 250;

const key = (id: string) => `swan.trip.${id}.actions`;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function readLog(id: string): SuggestionAction[] {
  if (typeof sessionStorage === "undefined") return [];
  const raw = sessionStorage.getItem(key(id));
  return raw ? (JSON.parse(raw) as SuggestionAction[]) : [];
}

function writeLog(id: string, log: SuggestionAction[]) {
  sessionStorage.setItem(key(id), JSON.stringify(log));
}

function replay(id: string, log: SuggestionAction[]): TripState {
  const start = initialState({ ...SCRIPT.proposal, trip_id: id });
  return log.reduce((state, action) => apply(state, action, CATALOG), start);
}

function withoutLast(log: SuggestionAction[], sid: string): SuggestionAction[] {
  const index = log.map((action) => action.suggestion_id).lastIndexOf(sid);
  return index < 0 ? log : [...log.slice(0, index), ...log.slice(index + 1)];
}

export const tripMock = {
  async getTrip(id: string): Promise<TripView> {
    return {
      conversation: { ...SCRIPT.conversation, trip_id: id },
      proposal: replay(id, readLog(id)).proposal,
    };
  },
  async suggestionAlternatives(id: string, sid: string, constraints: Constraints = {}) {
    await sleep(REPLY_MS);
    return alternatives(replay(id, readLog(id)), sid, constraints, CATALOG);
  },
  async actOnSuggestion(id: string, action: SuggestionAction): Promise<SuggestionResult> {
    const row = SCRIPT.proposal.suggestions.find((item) => item.id === action.suggestion_id);
    await sleep(action.action === "reject" && row?.required ? SEARCH_MS : REPLY_MS);
    const log = readLog(id);
    const before = replay(id, log);
    if (action.action === "modify" && !action.alternative_id) {
      const constraints = { ...(action.constraints as Constraints | null), text: action.text ?? undefined };
      return { proposal: before.proposal, alternatives: alternatives(before, action.suggestion_id, constraints, CATALOG) };
    }
    const next = action.action === "undo" ? withoutLast(log, action.suggestion_id) : [...log, action];
    const after = replay(id, next);
    if (JSON.stringify(after.proposal) !== JSON.stringify(before.proposal)) writeLog(id, next);
    return { proposal: after.proposal, alternatives: [] };
  },
  async acceptAll(id: string): Promise<Proposal> {
    await sleep(REPLY_MS);
    const log = readLog(id);
    const open = replay(id, log).proposal.suggestions.filter((row) => row.status === "proposed" || row.status === "replaced");
    const next = [...log, ...open.map((row): SuggestionAction => ({ suggestion_id: row.id, action: "accept" }))];
    writeLog(id, next);
    return replay(id, next).proposal;
  },
};
