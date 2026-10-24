import { API, type InspectorEvent } from "@contracts/api";
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
  subscribe(onEvent) {
    const es = new EventSource(BASE + API.events);
    const handler = (msg: MessageEvent) => onEvent(JSON.parse(msg.data) as InspectorEvent);
    es.addEventListener("inspector", handler);
    return () => {
      es.removeEventListener("inspector", handler);
      es.close();
    };
  },
};
