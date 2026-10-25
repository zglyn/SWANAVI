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
  settlement?: "sandbox";
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
  | "booking.confirmed" | "booking.cancelled" | "booking.failed" | "booking.needs_user"
  | "weather.alert" | "wallet.updated" | "system.reset"
  | "plan.tool_call" | "plan.candidates" | "plan.ready" | "plan.invalid" | "plan.failed"
  | "plan.flights_ready" | "plan.hotels_ready" | "plan.package_ready"
  | "chat.delta" | "chat.message" | "brief.updated" | "proposal.ready"
  | "suggestion.updated" | "itinerary.reflowed";

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
  me: "/api/me/profile",
  account: "/api/me",
  authMagic: "/api/auth/magic-link",
  authVerify: "/api/auth/verify",
  authDemo: "/api/auth/demo",
  tripRequest: "/api/trips/request",
  trips: "/api/trips",
  trip: (id: string) => `/api/trips/${id}`,
  tripMessages: (id: string) => `/api/trips/${id}/messages`,
  tripPlan: (id: string) => `/api/trips/${id}/plan`,
  tripAlternatives: (id: string, sid: string) => `/api/trips/${id}/suggestions/${sid}/alternatives`,
  tripSuggestion: (id: string, sid: string) => `/api/trips/${id}/suggestions/${sid}`,
  tripAcceptAll: (id: string) => `/api/trips/${id}/accept-all`,
  tripBook: (id: string) => `/api/trips/${id}/book`,
  planFlights: (id: string) => `/api/plans/${id}/flights`,
  planHotels: (id: string) => `/api/plans/${id}/hotels`,
  planChoices: (id: string) => `/api/plans/${id}/choices`,
  planAttractions: (id: string) => `/api/plans/${id}/attractions`,
  planPackage: (id: string) => `/api/plans/${id}/package`,
  swan: (id: string) => `/api/plans/${id}/swan`,
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

export type BudgetLevel = "budget" | "mid" | "premium" | "luxury";
export type Autonomy = "swan_decides" | "i_choose";
export type Cabin = "economy" | "premium_economy" | "business" | "first";
export type SeatPref = "window" | "aisle" | "any";
export type TimeOfDayWindow = "red_eye" | "early_morning" | "morning" | "afternoon" | "evening" | "any";
export type AmountLevel = "none" | "a_little" | "some" | "lots";
export type Density = "light" | "balanced" | "packed";
export type Priority = "must" | "nice";
export type HotelSource = "merchant_mcp" | "provider";
export type SwanPhase = "waiting_attractions" | "waiting_flights" | "waiting_hotels" | "ready";

export interface HomeBase { address: string; location: GeoPoint; airport_codes: string[] }
export interface LoyaltyProgram { program: string; number?: string | null }
export interface TravelPreferences {
  interests: string[];
  pace: Pace;
  budget_level: BudgetLevel;
  preferred_modes: TravelMode[];
  dietary: string[];
  accessibility: string[];
  avoid: string[];
}
export interface SleepSchedule { wake_time: string; sleep_time: string; jet_lag_buffer: boolean }
export interface HotelPreferences {
  favourite_brands: string[];
  min_stars?: number | null;
  must_have: string[];
  room_type?: string | null;
  loyalty: LoyaltyProgram[];
}
export interface FlightPreferences {
  favourite_airlines: string[];
  alliances: string[];
  cabin: Cabin;
  max_stops: number;
  seat: SeatPref;
  loyalty: LoyaltyProgram[];
  avoid_red_eye: boolean;
}
export interface AutonomyDefaults { attractions: Autonomy; hotels: Autonomy; flights: Autonomy }
export interface UserProfile {
  user_id: string;
  name: string;
  home: HomeBase;
  currency: string;
  travel: TravelPreferences;
  sleep: SleepSchedule;
  hotels: HotelPreferences;
  flights: FlightPreferences;
  autonomy: AutonomyDefaults;
}
export interface Destination {
  city: string;
  country_code: string;
  lat: number;
  lng: number;
  timezone: string;
  currency: string;
  airports: string[];
}
export interface TripOrigin { from_home: boolean; place?: string | null; airport_codes: string[] }
export interface TripRequest {
  destination: string;
  place?: Destination | null;
  origin: TripOrigin;
  start_date: string;
  end_date: string;
  outbound_window: TimeOfDayWindow;
  return_window: TimeOfDayWindow;
  travellers: number;
  budget?: Money | null;
  autonomy: AutonomyDefaults;
  notes?: string | null;
}
export interface AttractionPick { candidate_id: string; priority: Priority }
export interface CategoryAmount { category: string; level: AmountLevel }
export interface AttractionSelection extends PlanSelection {
  mode: Autonomy;
  picks: AttractionPick[];
  amounts: CategoryAmount[];
  daily_density: Density;
}
export interface FareConditions { refundable: boolean; changeable: boolean }
export interface FlightOffer {
  id: string;
  segments: TravelSegment[];
  carrier: string;
  cabin: Cabin;
  stops: number;
  duration_min: number;
  price: Money;
  currency: string;
  fare_conditions: FareConditions;
  score: number;
  why: string[];
  deep_link?: string | null;
  direction: "outbound" | "return";
}
export interface HotelOffer {
  id: string;
  name: string;
  brand?: string | null;
  stars?: number | null;
  location: GeoPoint;
  area?: string | null;
  price_per_night: Money;
  total: Money;
  currency: string;
  amenities: string[];
  refundable: boolean;
  avg_travel_min_to_attractions: number;
  score: number;
  why: string[];
  image_url?: string | null;
  source: HotelSource;
  quote?: Quote | null;
  deep_link?: string | null;
  check_in?: string | null;
  check_out?: string | null;
}
export interface HotelStay { offer: HotelOffer; check_in: string; check_out: string }
export interface PackageTotals {
  flights: Money;
  hotels: Money;
  activities: Money;
  total: Money;
  currency: string;
  savings: Money;
}
export interface TravelPackage {
  plan_id: string;
  outbound?: FlightOffer | null;
  return?: FlightOffer | null;
  hotels: HotelStay[];
  itinerary: Itinerary;
  totals: PackageTotals;
  reasons: string[];
}
export interface PackageChoices {
  outbound_id?: string | null;
  return_id?: string | null;
  hotel_ids?: string[];
}
export interface SwanView {
  plan_id: string;
  phase: SwanPhase;
  request: TripRequest;
  flights: FlightOffer[];
  hotels: HotelOffer[];
  package?: TravelPackage | null;
}

export type ConversationPhase = "chatting" | "planning" | "proposal" | "review" | "booked";
export type ChatRole = "user" | "assistant";
export type ControlType = "chips" | "date_range" | "stepper" | "slider" | "airport" | "tiles";
export type SuggestionKind = "flight" | "hotel" | "attraction" | "transfer";
export type SuggestionStatus = "proposed" | "accepted" | "modifying" | "rejected" | "replaced" | "booked";
export type SuggestionActionName = "accept" | "reject" | "modify" | "undo";

export interface Control {
  slot: string;
  type: ControlType;
  options?: string[] | null;
  min?: number | null;
  max?: number | null;
  value?: unknown;
}
export interface ChatAnswer { slot: string; value: unknown }
export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  controls: Control[];
  answers?: ChatAnswer[] | null;
  created_at: string;
}
export interface TripFacts {
  destination?: string | null;
  place?: Destination | null;
  origin?: TripOrigin | null;
  start_date?: string | null;
  end_date?: string | null;
  outbound_window?: TimeOfDayWindow | null;
  return_window?: TimeOfDayWindow | null;
  travellers?: number | null;
  budget?: Money | null;
  pace?: Pace | null;
  interests?: string[];
  notes?: string | null;
}
export interface TripConversation {
  trip_id: string;
  phase: ConversationPhase;
  messages: ChatMessage[];
  brief: TripFacts;
  missing: string[];
}
interface SuggestionBase {
  id: string;
  status: SuggestionStatus;
  why: string[];
  alternatives_available: boolean;
  required: boolean;
}
export type Suggestion = SuggestionBase & (
  | { kind: "flight"; item: FlightOffer }
  | { kind: "hotel"; item: HotelStay }
  | { kind: "attraction" | "transfer"; item: Stop }
);
export interface Proposal {
  trip_id: string;
  package: TravelPackage;
  suggestions: Suggestion[];
  totals: PackageTotals;
}
export interface SuggestionAction {
  suggestion_id: string;
  action: SuggestionActionName;
  reason?: string | null;
  alternative_id?: string | null;
  constraints?: Record<string, unknown> | null;
  text?: string | null;
}
export type BookingChannel = "wallet" | "external";
interface BookingBase {
  suggestion_id: string;
  confirmation_code: string | null;
  error: string | null;
}
export type BookingLine = BookingBase & (
  | { channel: "wallet"; status: "booked" | "blocked" | "failed"; violations: Violation[] }
  | { channel: "external"; status: "booked" | "failed" | "needs_user" }
);
export interface BookRequest {
  channel: BookingChannel;
  travellers?: string[];
}
export interface TripView {
  conversation: TripConversation;
  proposal?: Proposal | null;
  bookings: BookingLine[];
}
export interface SuggestionResult {
  proposal: Proposal;
  alternatives: Suggestion[];
}
