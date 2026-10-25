import {
  API,
  type AttractionSelection,
  type BookRequest,
  type InspectorEvent,
  type PackageChoices,
  type PlanRevision,
  type PlanSelection,
  type PlanView,
  type Proposal,
  type Suggestion,
  type SuggestionAction,
  type SuggestionResult,
  type SwanView,
  type TravelPackage,
  type TravelSegment,
  type TripBrief,
  type TripRequest,
  type TripView,
  type UserProfile,
} from "@contracts/api";
import type { RoamClient } from "./client";

const BASE = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("swan.token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...init?.headers },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}`);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const realClient: RoamClient = {
  mode: "real",
  getPolicy: () => call(API.policy),
  putPolicy: (policy) => call(API.policy, { method: "PUT", body: JSON.stringify(policy) }),
  chat: async (message) => {
    await call(API.chat, { method: "POST", body: JSON.stringify({ message }) });
  },
  checkout: (invoice_ids) => call(API.checkout, { method: "POST", body: JSON.stringify({ invoice_ids }) }),
  runScenario: async (name) => {
    await call(API.scenario(name), { method: "POST" });
  },
  getWallet: () => call(API.wallet),
  createPlan: (brief: TripBrief) => call(API.plans, { method: "POST", body: JSON.stringify(brief) }),
  getPlan: (id: string) => call<PlanView>(API.plan(id)),
  submitSelection: (id: string, selection: PlanSelection) =>
    call(API.planSelection(id), { method: "POST", body: JSON.stringify(selection) }),
  revisePlan: (id: string, revision: PlanRevision) =>
    call(API.planRevise(id), { method: "POST", body: JSON.stringify(revision) }),
  lookupFlight: (number: string, date: string) =>
    call<TravelSegment>(`${API.flightLookup}?number=${encodeURIComponent(number)}&date=${encodeURIComponent(date)}`),
  subscribe(onEvent, onStatus) {
    const seen = new Set<string>();
    let closed = false;
    let source: EventSource | null = null;
    const connect = () => {
      source = new EventSource(BASE + API.events);
      source.onopen = () => onStatus?.("live");
      source.onerror = () => {
        onStatus?.("down");
        source?.close();
        if (!closed) window.setTimeout(connect, 1500);
      };
      source.addEventListener("inspector", (msg) => {
        const event = JSON.parse((msg as MessageEvent).data) as InspectorEvent;
        if (seen.has(event.id)) return;
        seen.add(event.id);
        onEvent(event);
      });
    };
    connect();
    return () => {
      closed = true;
      source?.close();
    };
  },
  async demoSignIn() {
    const result = await call<{ token: string; user_id: string }>(API.authDemo, { method: "POST" });
    localStorage.setItem("swan.token", result.token);
    return result;
  },
  async magicLink(email: string) {
    const result = await call<{ token: string; user_id: string }>(API.authMagic, { method: "POST", body: JSON.stringify({ email }) });
    localStorage.setItem("swan.token", result.token);
    return result;
  },
  async getProfile() {
    try {
      return await call<UserProfile>(API.me);
    } catch {
      return null;
    }
  },
  putProfile: (profile: UserProfile) => call<UserProfile>(API.me, { method: "PUT", body: JSON.stringify(profile) }),
  async deleteAccount() {
    await call(API.account, { method: "DELETE" });
    localStorage.removeItem("swan.token");
    localStorage.removeItem("swan.profile");
  },
  requestTrip: (request: TripRequest) => call(API.tripRequest, { method: "POST", body: JSON.stringify(request) }),
  getSwan: (id: string) => call<SwanView>(API.swan(id)),
  submitAttractions: (id: string, selection: AttractionSelection) =>
    call(API.planAttractions(id), { method: "POST", body: JSON.stringify(selection) }),
  choosePackage: (id: string, choices: PackageChoices) =>
    call(API.planChoices(id), { method: "POST", body: JSON.stringify(choices) }),
  getPackage: (id: string) => call<TravelPackage>(API.planPackage(id)),
  createTrip: (message: string) => call(API.trips, { method: "POST", body: JSON.stringify({ message }) }),
  getTrip: (id: string) => call<TripView>(API.trip(id)),
  suggestionAlternatives: (id: string, sid: string, constraints = {}) =>
    call<Suggestion[]>(`${API.tripAlternatives(id, sid)}?constraints=${encodeURIComponent(JSON.stringify(constraints))}`),
  actOnSuggestion: (id: string, action: SuggestionAction) =>
    call<SuggestionResult>(API.tripSuggestion(id, action.suggestion_id), { method: "POST", body: JSON.stringify(action) }),
  acceptAll: (id: string) => call<Proposal>(API.tripAcceptAll(id), { method: "POST" }),
  bookTrip: (id: string, request: BookRequest) =>
    call<{ ok: boolean }>(API.tripBook(id), { method: "POST", body: JSON.stringify(request) }),
};
