"use client";

import type {
  Booking,
  CheckoutResult,
  EscrowRef,
  InspectorEvent,
  PolicyConfig,
  PolicyDecision,
  Quote,
  ScenarioName,
  WalletState,
} from "@contracts/api";
import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { getClient } from "./client";

export type QuoteStatus = "quoted" | "blocked" | "booked" | "refunded";
export type SignerState = "idle" | "pending" | "signed" | "refused";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  tone?: "warning";
}

interface State {
  events: InspectorEvent[];
  quotes: Quote[];
  status: Record<string, QuoteStatus>;
  confirmations: Record<string, string>;
  chat: ChatMessage[];
  signers: { agent: SignerState; guardrail: SignerState; ledger: SignerState };
  lastDecision: PolicyDecision | null;
  saved: number;
  wallet: WalletState | null;
  busy: boolean;
}

const initial: State = {
  events: [],
  quotes: [],
  status: {},
  confirmations: {},
  chat: [],
  signers: { agent: "idle", guardrail: "idle", ledger: "idle" },
  lastDecision: null,
  saved: 0,
  wallet: null,
  busy: false,
};

type Action =
  | { kind: "event"; event: InspectorEvent }
  | { kind: "user"; text: string }
  | { kind: "wallet"; wallet: WalletState }
  | { kind: "busy"; busy: boolean };

function applyEvent(s: State, e: InspectorEvent): State {
  const next: State = { ...s, events: [e, ...s.events].slice(0, 200) };
  const d = e.data as Record<string, unknown>;
  switch (e.type) {
    case "quote.received": {
      const q = d.quote as Quote;
      if (!s.quotes.some((x) => x.invoice_id === q.invoice_id)) next.quotes = [...s.quotes, q];
      next.status = { ...s.status, [q.invoice_id]: s.status[q.invoice_id] ?? "quoted" };
      break;
    }
    case "agent.message":
      next.chat = [...s.chat, { id: e.id, role: "agent", text: e.message, tone: e.level === "warning" ? "warning" : undefined }];
      break;
    case "agent.planning":
      next.signers = { agent: "idle", guardrail: "idle", ledger: "idle" };
      break;
    case "tx.signed.agent":
      next.signers = { agent: "signed", guardrail: "pending", ledger: "idle" };
      break;
    case "guardrail.approved":
      next.signers = { ...s.signers, guardrail: "signed", ledger: "pending" };
      next.lastDecision = d.decision as PolicyDecision;
      break;
    case "guardrail.blocked": {
      const decision = d.decision as PolicyDecision;
      next.signers = { ...s.signers, guardrail: "refused", ledger: "idle" };
      next.lastDecision = decision;
      const status = { ...s.status };
      decision.violations.forEach((v) => v.invoice_id && (status[v.invoice_id] = "blocked"));
      next.status = status;
      break;
    }
    case "batch.validated": {
      const c = d.checkout as CheckoutResult;
      next.signers = { ...s.signers, ledger: "signed" };
      next.saved = s.saved + Number(c.savings ?? 0);
      const status = { ...s.status };
      c.escrows.forEach((x) => (status[x.invoice_id] = "booked"));
      next.status = status;
      break;
    }
    case "batch.failed":
      next.signers = { ...s.signers, ledger: "refused" };
      break;
    case "booking.confirmed": {
      const b = d.booking as Booking;
      next.confirmations = { ...s.confirmations, [b.invoice_id]: b.confirmation_code };
      break;
    }
    case "escrow.cancelled": {
      const x = d.escrow as EscrowRef;
      next.status = { ...s.status, [x.invoice_id]: "refunded" };
      break;
    }
    case "wallet.updated":
      next.wallet = d.wallet as WalletState;
      break;
    case "system.reset":
      return { ...initial, events: [e], wallet: (d.wallet as WalletState) ?? s.wallet };
  }
  return next;
}

function reducer(s: State, a: Action): State {
  switch (a.kind) {
    case "event":
      return applyEvent(s, a.event);
    case "user":
      return { ...s, chat: [...s.chat, { id: `u-${Date.now()}`, role: "user", text: a.text }] };
    case "wallet":
      return { ...s, wallet: a.wallet };
    case "busy":
      return { ...s, busy: a.busy };
  }
}

const TERMINAL = new Set(["guardrail.blocked", "batch.validated", "batch.failed", "system.reset", "agent.message"]);

export function useDemo() {
  const client = useMemo(getClient, []);
  const [state, dispatch] = useReducer(reducer, initial);
  const busyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    client.getWallet().then((wallet) => dispatch({ kind: "wallet", wallet })).catch(() => {});
    return client.subscribe((event) => {
      dispatch({ kind: "event", event });
      // Real gateway: scenarios resolve immediately, so terminal events end the busy state.
      if (client.mode === "real" && TERMINAL.has(event.type)) dispatch({ kind: "busy", busy: false });
    });
  }, [client]);

  const run = useCallback(
    async (work: () => Promise<unknown>) => {
      dispatch({ kind: "busy", busy: true });
      if (busyTimer.current) clearTimeout(busyTimer.current);
      busyTimer.current = setTimeout(() => dispatch({ kind: "busy", busy: false }), 30_000);
      try {
        await work();
      } finally {
        if (client.mode === "mock") dispatch({ kind: "busy", busy: false });
      }
    },
    [client],
  );

  return {
    client,
    state,
    sendChat: (text: string) => {
      dispatch({ kind: "user", text });
      return run(() => client.chat(text));
    },
    checkout: (ids: string[]) => run(() => client.checkout(ids)),
    scenario: (name: ScenarioName) => run(() => client.runScenario(name)),
    getPolicy: () => client.getPolicy(),
    putPolicy: (p: PolicyConfig) => client.putPolicy(p),
    seedQuotes: (quotes: Quote[]) => {
      for (const quote of quotes) {
        dispatch({
          kind: "event",
          event: {
            id: `book-${quote.invoice_id}`,
            ts: new Date().toISOString(),
            source: "merchant",
            level: "info",
            type: "quote.received",
            message: quote.title,
            tx_hash: null,
            explorer_url: null,
            data: { quote },
          },
        });
      }
    },
  };
}
