// Mirror of contracts/python/roam_contracts/models.py. Money is a decimal string ("15.00"); datetimes are ISO strings.

export type Currency = "RLUSD" | "XRP";
export type Money = string;
export type Hash256 = string;
export type Category = "activity" | "food" | "transport" | "lodging" | "shopping";

export interface GeoPoint { lat: number; lng: number }

export interface MerchantProfile {
  merchant_id: string;
  name: string;
  category: Category;
  location: GeoPoint;
  xrpl_address: string;
  mcp_url: string;
  pubkey_ed25519: string;
  city?: string | null;
  country?: string | null;
}

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
  merchant_verified?: boolean | null; // set by the gateway; not part of the signed quote
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
  | "weather.alert" | "wallet.updated" | "system.reset"
  | "plan.tool_call" | "plan.candidates" | "plan.ready" | "plan.invalid" | "plan.failed";

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
  plans: "/api/plans",            // POST TripBrief -> {plan_id}
  plan: (id: string) => `/api/plans/${id}`, // GET PlanView
  planSelection: (id: string) => `/api/plans/${id}/selection`, // POST PlanSelection -> {ok}
  planRevise: (id: string) => `/api/plans/${id}/revise`, // POST PlanRevision -> {ok}
  flightLookup: "/api/flights/lookup", // GET ?number=&date= -> TravelSegment
} as const;

export type TravelMode = "walk" | "bike" | "transit" | "taxi" | "car";
export type SegmentMode = "flight" | "train" | "bus" | "car";
export type SegmentStatus = "scheduled" | "delayed" | "cancelled" | "unverified";
export type Pace = "relaxed" | "balanced" | "packed";
export type CandidateKind = "attraction" | "merchant";
export type LegSource = "ors" | "google" | "estimate";
export type StopKind = "attraction" | "merchant" | "arrival" | "departure" | "lodging";
export type StopStatus = "proposed" | "accepted" | "removed";
export type PlanStatus = "collecting_candidates" | "candidates_ready" | "planning" | "ready" | "failed";
export type RevisionAction = "accept" | "swap" | "remove";

export interface PlaceRef { code?: string | null; name: string; location?: GeoPoint | null }
export interface TravelSegment {
  mode: SegmentMode;
  carrier?: string | null;
  number?: string | null;
  from_place: PlaceRef;
  to_place: PlaceRef;
  depart_at: string;
  arrive_at: string;
  status: SegmentStatus;
  source: string;
  terminal?: string | null;
}
export interface Lodging {
  name: string;
  address?: string | null;
  location?: GeoPoint | null;
  check_in: string;
  check_out: string;
}
export interface TripBrief {
  destination: string;
  timezone: string;
  arrival?: TravelSegment | null;
  departure?: TravelSegment | null;
  lodging?: Lodging[];
  start_date?: string | null;
  end_date?: string | null;
  budget: Money;
  interests: string[];
  pace: Pace;
  preferred_modes: TravelMode[];
  daily_start: string;
  daily_end: string;
}
export interface Attraction {
  id: string;
  name: string;
  category: string;
  location: GeoPoint;
  area?: string | null;
  description: string;
  image_url?: string | null;
  popularity: number;
  typical_duration_min: number;
  opening_hours?: string | null;
  price?: Money | null;
  free: boolean;
  source: "curated" | "osm" | "llm";
}
export interface CatalogItem {
  sku: string;
  merchant_id: string;
  title: string;
  description: string;
  category: Category;
  price: Money;
  currency: Currency;
  viator_price?: Money | null;
  slot_start: string;
  slot_end: string;
  indoor: boolean;
  refundable: boolean;
  available?: boolean;
}
export interface Candidate {
  id: string;
  kind: CandidateKind;
  attraction?: Attraction | null;
  merchant?: MerchantProfile | null;
  item?: CatalogItem | null;
  quote?: Quote | null;
}
export interface CandidateSet { plan_id: string; candidates: Candidate[]; available_hours: number }
export interface PlanSelection { must_visit: string[]; maybe: string[]; excluded: string[] }
export interface Leg {
  from_stop_id: string;
  to_stop_id: string;
  mode: TravelMode;
  minutes: number;
  distance_km: number;
  cost?: Money | null;
  source: LegSource;
}
export interface Stop {
  id: string;
  kind: StopKind;
  start: string;
  end: string;
  location: GeoPoint;
  title: string;
  attraction?: Attraction | null;
  quote?: Quote | null;
  required: boolean;
  status: StopStatus;
}
export interface ItineraryDay { date: string; stops: Stop[]; legs: Leg[] }
export interface Itinerary {
  plan_id: string;
  brief: TripBrief;
  selection: PlanSelection;
  days: ItineraryDay[];
  transport_summary: string;
  estimated_total: Money;
  bookable_total: Money;
  warnings: string[];
}
export interface StopRevision { stop_id: string; action: RevisionAction }
export interface PlanRevision { actions: StopRevision[]; feedback?: string | null }
export interface PlanView {
  status: PlanStatus;
  candidates?: CandidateSet | null;
  itinerary?: Itinerary | null;
  error?: string | null;
}
export interface PlanCreated { plan_id: string }
