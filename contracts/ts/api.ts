// Mirror of contracts/python/roam_contracts/models.py. Money is a decimal string ("15.00"); datetimes are ISO strings.

export type Currency = "RLUSD" | "XRP";
export type Money = string;
export type Hash256 = string;
export type Category = "activity" | "food" | "transport" | "lodging" | "shopping";

export interface GeoPoint { lat: number; lng: number }

export interface Quote {
  invoice_id: Hash256;
  merchant_id: string;
  merchant_name: string;
  merchant_address: string;
  sku: string;
  title: string;
  category: Category;
  amount: Money;
  currency: Currency;
  viator_price: Money | null;
  slot_start: string;
  slot_end: string;
  location: GeoPoint;
  cancel_after: string;
  expires_at: string;
  merchant_signature: string;
}

export interface Geofence { center: GeoPoint; radius_km: number }

export interface PolicyConfig {
  max_daily_budget: Money;
  max_per_item: Money;
  currency: Currency;
  require_verified_credential: boolean;
  allowed_categories: Category[];
  date_window_start: string | null;
  date_window_end: string | null;
  geofence: Geofence | null;
}

export type ViolationRule =
  | "max_per_item" | "max_daily_budget" | "verified_credential" | "category"
  | "date_window" | "geofence" | "quote_signature" | "quote_expired" | "tx_quote_mismatch";

export interface Violation {
  rule: ViolationRule;
  invoice_id: Hash256 | null;
  detail: string;
  expected: string | null;
  actual: string | null;
}

export interface PolicyDecision {
  approved: boolean;
  violations: Violation[];
  total: Money;
  remaining_daily_budget: Money;
}

export interface EscrowRef {
  invoice_id: Hash256;
  owner: string;
  sequence: number;
  destination: string;
  amount: Money;
  currency: Currency;
  finish_after: string | null;
  cancel_after: string;
}

export interface TxResult { tx_hash: Hash256; engine_result: string; validated: boolean; explorer_url: string }

export interface Booking {
  invoice_id: Hash256;
  merchant_id: string;
  sku: string;
  status: "confirmed" | "cancelled";
  confirmation_code: string;
}

export interface CheckoutResult {
  status: "success" | "blocked" | "failed";
  batch: TxResult | null;
  escrows: EscrowRef[];
  decision: PolicyDecision | null;
  total: Money;
  viator_total: Money | null;
  savings: Money | null;
  bookings: Booking[];
}

export interface WalletState {
  trip_address: string;
  balance: Money;
  currency: Currency;
  locked_in_escrow: Money;
  spent_today: Money;
  signers: { role: "agent" | "guardrail"; address: string; weight: number }[];
  quorum: number;
}

export type EventSource = "agent" | "merchant" | "guardrail" | "ledger" | "system";
export type EventLevel = "info" | "success" | "warning" | "blocked" | "error";

export type EventType =
  | "agent.message" | "agent.planning" | "quote.received"
  | "guardrail.approved" | "guardrail.blocked" | "tx.signed.agent"
  | "batch.submitted" | "batch.validated" | "batch.failed"
  | "escrow.cancelled" | "escrow.finished"
  | "booking.confirmed" | "booking.cancelled"
  | "weather.alert" | "wallet.updated" | "system.reset";

export interface InspectorEvent {
  id: string;
  ts: string;
  source: EventSource;
  level: EventLevel;
  type: EventType | string;
  message: string;
  tx_hash: Hash256 | null;
  explorer_url: string | null;
  data: Record<string, unknown>;
}

// Gateway API (features/agent, :8000)
export type ScenarioName = "happy-path" | "malicious-upsell" | "rainstorm" | "reset";
export interface ChatRequest { message: string }
export interface ChatResponse { reply: string; quotes: Quote[] }
export interface CheckoutRequest { invoice_ids: Hash256[] }

export const API = {
  policy: "/api/policy",          // GET, PUT PolicyConfig
  chat: "/api/chat",              // POST ChatRequest -> ChatResponse
  checkout: "/api/checkout",      // POST CheckoutRequest -> CheckoutResult
  scenario: (n: ScenarioName) => `/api/scenarios/${n}`, // POST -> {ok: true}
  wallet: "/api/wallet",          // GET WalletState
  events: "/api/events",          // GET SSE stream of InspectorEvent
} as const;
