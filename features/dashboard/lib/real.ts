import {
  API,
  type InspectorEvent,
  type PlanRevision,
  type PlanSelection,
  type PlanView,
  type TravelSegment,
  type TripBrief,
} from "@contracts/api";
import type { RoamClient } from "./client";

const BASE = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}`);
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
};
