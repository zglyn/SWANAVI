"""Shared data contracts. Frozen at Hour 2 — add optional fields only. Mirror changes in contracts/ts/api.ts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, model_validator

Currency = Literal["RLUSD", "XRP"]
Money = Decimal  # serialized as string, e.g. "15.00"
Hash256 = str  # 64-char uppercase hex


class Category(str, Enum):
    ACTIVITY = "activity"
    FOOD = "food"
    TRANSPORT = "transport"
    LODGING = "lodging"
    SHOPPING = "shopping"


class GeoPoint(BaseModel):
    lat: float
    lng: float


# --- merchants -------------------------------------------------------------


class MerchantProfile(BaseModel):
    merchant_id: str
    name: str
    category: Category
    location: GeoPoint
    xrpl_address: str
    mcp_url: str
    pubkey_ed25519: str  # hex; verifies Quote.merchant_signature
    city: str | None = None
    country: str | None = None


class CatalogItem(BaseModel):
    sku: str
    merchant_id: str
    title: str
    description: str
    category: Category
    price: Money
    currency: Currency
    viator_price: Money | None = None
    slot_start: datetime
    slot_end: datetime
    indoor: bool
    refundable: bool
    available: bool = True


class Quote(BaseModel):
    """Body of the merchant's HTTP 402 response. Signed; nothing moves money yet."""

    invoice_id: Hash256
    merchant_id: str
    merchant_name: str
    merchant_address: str
    sku: str
    title: str
    category: Category
    amount: Money
    currency: Currency
    viator_price: Money | None = None
    slot_start: datetime
    slot_end: datetime
    location: GeoPoint
    cancel_after: datetime  # latest time a refund (EscrowCancel) is possible
    expires_at: datetime
    merchant_signature: str  # hex ed25519 over canonical JSON of all other fields
    merchant_verified: bool | None = None  # set by the gateway via ledger.has_credential; not signed


class PaymentProof(BaseModel):
    """Sent base64-encoded in the X-PAYMENT header when retrying a 402 request."""

    invoice_id: Hash256
    batch_tx_hash: Hash256
    escrow_owner: str
    escrow_sequence: int


class Booking(BaseModel):
    invoice_id: Hash256
    merchant_id: str
    sku: str
    status: Literal["confirmed", "cancelled"]
    confirmation_code: str


# --- guardrail -------------------------------------------------------------


class Geofence(BaseModel):
    center: GeoPoint
    radius_km: float


class PolicyConfig(BaseModel):
    max_daily_budget: Money = Decimal("100")
    max_per_item: Money = Decimal("45")
    currency: Currency = "RLUSD"
    require_verified_credential: bool = True
    allowed_categories: list[Category] = Field(
        default_factory=lambda: [Category.ACTIVITY, Category.FOOD, Category.TRANSPORT, Category.LODGING]
    )
    date_window_start: datetime | None = None
    date_window_end: datetime | None = None
    geofence: Geofence | None = None


class ViolationRule(str, Enum):
    MAX_PER_ITEM = "max_per_item"
    MAX_DAILY_BUDGET = "max_daily_budget"
    VERIFIED_CREDENTIAL = "verified_credential"
    CATEGORY = "category"
    DATE_WINDOW = "date_window"
    GEOFENCE = "geofence"
    QUOTE_SIGNATURE = "quote_signature"
    QUOTE_EXPIRED = "quote_expired"
    TX_QUOTE_MISMATCH = "tx_quote_mismatch"


class Violation(BaseModel):
    rule: ViolationRule
    invoice_id: Hash256 | None = None
    detail: str
    expected: str | None = None
    actual: str | None = None


class PolicyDecision(BaseModel):
    approved: bool
    violations: list[Violation] = Field(default_factory=list)
    total: Money
    remaining_daily_budget: Money


class UnsignedTx(BaseModel):
    tx_json: dict[str, Any]  # autofilled XRPL tx (e.g. Batch), ready for multi-signing
    invoice_ids: list[Hash256]


class CosignRequest(BaseModel):
    tx: UnsignedTx
    quotes: list[Quote]
    policy: PolicyConfig
    spent_today: Money = Decimal("0")


class CosignResponse(BaseModel):
    decision: PolicyDecision
    signer_blob: dict[str, Any] | None = None  # the Guardrail's Signer entry; None when blocked


# --- ledger ----------------------------------------------------------------


class EscrowRef(BaseModel):
    invoice_id: Hash256
    owner: str
    sequence: int
    destination: str
    amount: Money
    currency: Currency
    finish_after: datetime | None = None
    cancel_after: datetime


class TxResult(BaseModel):
    tx_hash: Hash256
    engine_result: str  # e.g. "tesSUCCESS"
    validated: bool
    explorer_url: str


class CheckoutResult(BaseModel):
    status: Literal["success", "blocked", "failed"]
    batch: TxResult | None = None
    escrows: list[EscrowRef] = Field(default_factory=list)
    decision: PolicyDecision | None = None
    total: Money
    viator_total: Money | None = None
    savings: Money | None = None
    bookings: list[Booking] = Field(default_factory=list)


class WalletState(BaseModel):
    trip_address: str
    balance: Money
    currency: Currency
    locked_in_escrow: Money
    spent_today: Money
    signers: list[dict[str, Any]]  # [{"role": "agent"|"guardrail", "address": ..., "weight": 1}]
    quorum: int


class TravelMode(str, Enum):
    WALK = "walk"
    BIKE = "bike"
    TRANSIT = "transit"
    TAXI = "taxi"
    CAR = "car"


class SegmentMode(str, Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    CAR = "car"


class SegmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    DELAYED = "delayed"
    CANCELLED = "cancelled"
    UNVERIFIED = "unverified"


class PlaceRef(BaseModel):
    code: str | None = None
    name: str
    location: GeoPoint | None = None


class TravelSegment(BaseModel):
    mode: SegmentMode
    carrier: str | None = None
    number: str | None = None
    from_place: PlaceRef
    to_place: PlaceRef
    depart_at: datetime
    arrive_at: datetime
    status: SegmentStatus = SegmentStatus.SCHEDULED
    source: str = "user"
    terminal: str | None = None


class Lodging(BaseModel):
    name: str
    address: str | None = None
    location: GeoPoint | None = None
    check_in: datetime
    check_out: datetime


class Pace(str, Enum):
    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class TripBrief(BaseModel):
    destination: str
    timezone: str
    arrival: TravelSegment | None = None
    departure: TravelSegment | None = None
    lodging: list[Lodging] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget: Money = Decimal("200")
    interests: list[str] = Field(default_factory=list)
    pace: Pace = Pace.BALANCED
    preferred_modes: list[TravelMode] = Field(default_factory=lambda: [TravelMode.WALK, TravelMode.TRANSIT])
    daily_start: str = "09:00"
    daily_end: str = "21:00"


class Attraction(BaseModel):
    id: str
    name: str
    category: str
    location: GeoPoint
    area: str | None = None
    description: str
    image_url: str | None = None
    popularity: float = Field(ge=0, le=1)
    typical_duration_min: int
    opening_hours: str | None = None
    price: Money | None = None
    free: bool = True
    source: Literal["curated", "osm", "llm"] = "curated"


class CandidateKind(str, Enum):
    ATTRACTION = "attraction"
    MERCHANT = "merchant"


class Candidate(BaseModel):
    id: str
    kind: CandidateKind
    attraction: Attraction | None = None
    merchant: MerchantProfile | None = None
    item: CatalogItem | None = None
    quote: Quote | None = None


class CandidateSet(BaseModel):
    plan_id: str
    candidates: list[Candidate]
    available_hours: float


class PlanSelection(BaseModel):
    must_visit: list[str] = Field(default_factory=list)
    maybe: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class LegSource(str, Enum):
    ORS = "ors"
    GOOGLE = "google"
    ESTIMATE = "estimate"


class Leg(BaseModel):
    from_stop_id: str
    to_stop_id: str
    mode: TravelMode
    minutes: int
    distance_km: float
    cost: Money | None = None
    source: LegSource = LegSource.ESTIMATE


class StopKind(str, Enum):
    ATTRACTION = "attraction"
    MERCHANT = "merchant"
    ARRIVAL = "arrival"
    DEPARTURE = "departure"
    LODGING = "lodging"


class StopStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REMOVED = "removed"


class Stop(BaseModel):
    id: str
    kind: StopKind
    start: datetime
    end: datetime
    location: GeoPoint
    title: str
    attraction: Attraction | None = None
    quote: Quote | None = None
    required: bool = False
    status: StopStatus = StopStatus.PROPOSED


class ItineraryDay(BaseModel):
    date: str
    stops: list[Stop]
    legs: list[Leg]


class Itinerary(BaseModel):
    plan_id: str
    brief: TripBrief
    selection: PlanSelection
    days: list[ItineraryDay]
    transport_summary: str
    estimated_total: Money
    bookable_total: Money
    warnings: list[str] = Field(default_factory=list)


class PlanStatus(str, Enum):
    COLLECTING = "collecting_candidates"
    CANDIDATES_READY = "candidates_ready"
    PLANNING = "planning"
    READY = "ready"
    FAILED = "failed"


class RevisionAction(str, Enum):
    ACCEPT = "accept"
    SWAP = "swap"
    REMOVE = "remove"


class StopRevision(BaseModel):
    stop_id: str
    action: RevisionAction


class PlanRevision(BaseModel):
    actions: list[StopRevision] = Field(default_factory=list)
    feedback: str | None = None


class PlanView(BaseModel):
    status: PlanStatus
    candidates: CandidateSet | None = None
    itinerary: Itinerary | None = None
    error: str | None = None


# --- inspector events (gateway -> dashboard via SSE) ----------------------


class EventSource(str, Enum):
    AGENT = "agent"
    MERCHANT = "merchant"
    GUARDRAIL = "guardrail"
    LEDGER = "ledger"
    SYSTEM = "system"


class EventLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    BLOCKED = "blocked"
    ERROR = "error"


# Every InspectorEvent.type the gateway may emit. Dashboard renders unknown types generically.
EVENT_TYPES = (
    "agent.message",       # free-form chat reply / reasoning summary
    "agent.planning",
    "quote.received",      # data: {quote: Quote}
    "guardrail.approved",  # data: {decision: PolicyDecision}
    "guardrail.blocked",   # data: {decision: PolicyDecision}
    "tx.signed.agent",     # data: {signer: "agent"}
    "batch.submitted",
    "batch.validated",     # data: {checkout: CheckoutResult}
    "batch.failed",        # data: {engine_result: str}
    "escrow.cancelled",    # data: {escrow: EscrowRef}
    "escrow.finished",     # data: {escrow: EscrowRef}
    "booking.confirmed",   # data: {booking: Booking}
    "booking.cancelled",   # data: {booking: Booking}
    "weather.alert",
    "wallet.updated",      # data: {wallet: WalletState}
    "system.reset",
    "plan.tool_call",      # data: {plan_id, tool, summary}
    "plan.candidates",     # data: {candidates: CandidateSet}
    "plan.ready",          # data: {itinerary: Itinerary}
    "plan.invalid",        # data: {plan_id, errors: list[str]}
    "plan.failed",         # data: {plan_id, error}
    "plan.flights_ready",
    "plan.hotels_ready",
    "plan.package_ready",
    "chat.delta",
    "chat.message",
    "brief.updated",
    "proposal.ready",
    "suggestion.updated",
    "itinerary.reflowed",
)

# On-ledger conventions shared by ledger (writes), merchants and guardrail (read/verify).
INVOICE_MEMO_TYPE = "roam402/invoice"  # EscrowCreate Memo: MemoType=hex(this), MemoData=invoice_id
CREDENTIAL_TYPE = "Local_Merchant_KYC"  # CredentialType = hex(this)


def source_tag_for(invoice_id: Hash256) -> int:
    """Unique per-booking SourceTag receipt: first 4 bytes of the invoice id."""
    return int(invoice_id[:8], 16)


class InspectorEvent(BaseModel):
    id: str
    ts: datetime
    source: EventSource
    level: EventLevel
    type: str  # e.g. "quote.received", "guardrail.blocked", "batch.validated", "escrow.cancelled"
    message: str
    tx_hash: Hash256 | None = None
    explorer_url: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class BudgetLevel(str, Enum):
    BUDGET = "budget"
    MID = "mid"
    PREMIUM = "premium"
    LUXURY = "luxury"


class Autonomy(str, Enum):
    SWAN_DECIDES = "swan_decides"
    I_CHOOSE = "i_choose"


class Cabin(str, Enum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class SeatPref(str, Enum):
    WINDOW = "window"
    AISLE = "aisle"
    ANY = "any"


class TimeOfDayWindow(str, Enum):
    RED_EYE = "red_eye"
    EARLY_MORNING = "early_morning"
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    ANY = "any"


class AmountLevel(str, Enum):
    NONE = "none"
    A_LITTLE = "a_little"
    SOME = "some"
    LOTS = "lots"


class Density(str, Enum):
    LIGHT = "light"
    BALANCED = "balanced"
    PACKED = "packed"


class Priority(str, Enum):
    MUST = "must"
    NICE = "nice"


class HotelSource(str, Enum):
    MERCHANT = "merchant_mcp"
    PROVIDER = "provider"


class HomeBase(BaseModel):
    address: str
    location: GeoPoint
    airport_codes: list[str] = Field(default_factory=list)


class LoyaltyProgram(BaseModel):
    program: str
    number: str | None = None


class TravelPreferences(BaseModel):
    interests: list[str] = Field(default_factory=list)
    pace: Pace = Pace.BALANCED
    budget_level: BudgetLevel = BudgetLevel.MID
    preferred_modes: list[TravelMode] = Field(default_factory=lambda: [TravelMode.WALK, TravelMode.TRANSIT])
    dietary: list[str] = Field(default_factory=list)
    accessibility: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class SleepSchedule(BaseModel):
    wake_time: str = "07:30"
    sleep_time: str = "23:00"
    jet_lag_buffer: bool = True


class HotelPreferences(BaseModel):
    favourite_brands: list[str] = Field(default_factory=list)
    min_stars: float | None = None
    must_have: list[str] = Field(default_factory=list)
    room_type: str | None = None
    loyalty: list[LoyaltyProgram] = Field(default_factory=list)


class FlightPreferences(BaseModel):
    favourite_airlines: list[str] = Field(default_factory=list)
    alliances: list[str] = Field(default_factory=list)
    cabin: Cabin = Cabin.ECONOMY
    max_stops: int = 1
    seat: SeatPref = SeatPref.ANY
    loyalty: list[LoyaltyProgram] = Field(default_factory=list)
    avoid_red_eye: bool = False


class AutonomyDefaults(BaseModel):
    attractions: Autonomy = Autonomy.SWAN_DECIDES
    hotels: Autonomy = Autonomy.SWAN_DECIDES
    flights: Autonomy = Autonomy.SWAN_DECIDES


class UserProfile(BaseModel):
    user_id: str
    name: str
    home: HomeBase
    currency: str = "USD"
    travel: TravelPreferences = Field(default_factory=TravelPreferences)
    sleep: SleepSchedule = Field(default_factory=SleepSchedule)
    hotels: HotelPreferences = Field(default_factory=HotelPreferences)
    flights: FlightPreferences = Field(default_factory=FlightPreferences)
    autonomy: AutonomyDefaults = Field(default_factory=AutonomyDefaults)


class TripOrigin(BaseModel):
    from_home: bool = True
    place: str | None = None
    airport_codes: list[str] = Field(default_factory=list)


class TripRequest(BaseModel):
    destination: str
    origin: TripOrigin
    start_date: str
    end_date: str
    outbound_window: TimeOfDayWindow = TimeOfDayWindow.ANY
    return_window: TimeOfDayWindow = TimeOfDayWindow.ANY
    travellers: int = 1
    budget: Money | None = None
    autonomy: AutonomyDefaults = Field(default_factory=AutonomyDefaults)
    notes: str | None = None


class AttractionPick(BaseModel):
    candidate_id: str
    priority: Priority


class CategoryAmount(BaseModel):
    category: str
    level: AmountLevel


class AttractionSelection(PlanSelection):
    mode: Autonomy = Autonomy.SWAN_DECIDES
    picks: list[AttractionPick] = Field(default_factory=list)
    amounts: list[CategoryAmount] = Field(default_factory=list)
    daily_density: Density = Density.BALANCED


class FareConditions(BaseModel):
    refundable: bool = False
    changeable: bool = False


class FlightOffer(BaseModel):
    id: str
    segments: list[TravelSegment]
    carrier: str
    cabin: Cabin = Cabin.ECONOMY
    stops: int = 0
    duration_min: int
    price: Money
    currency: str = "USD"
    fare_conditions: FareConditions = Field(default_factory=FareConditions)
    score: float = 0
    why: list[str] = Field(default_factory=list)
    deep_link: str | None = None
    direction: Literal["outbound", "return"] = "outbound"


class HotelOffer(BaseModel):
    id: str
    name: str
    brand: str | None = None
    stars: float | None = None
    location: GeoPoint
    area: str | None = None
    price_per_night: Money
    total: Money
    currency: str = "USD"
    amenities: list[str] = Field(default_factory=list)
    refundable: bool = False
    avg_travel_min_to_attractions: int = 0
    score: float = 0
    why: list[str] = Field(default_factory=list)
    image_url: str | None = None
    source: HotelSource = HotelSource.PROVIDER
    quote: Quote | None = None
    deep_link: str | None = None
    check_in: str | None = None
    check_out: str | None = None


class HotelStay(BaseModel):
    offer: HotelOffer
    check_in: str
    check_out: str


class PackageTotals(BaseModel):
    flights: Money = Decimal("0")
    hotels: Money = Decimal("0")
    activities: Money = Decimal("0")
    total: Money = Decimal("0")
    currency: str = "USD"
    savings: Money = Decimal("0")


class TravelPackage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plan_id: str
    outbound: FlightOffer | None = None
    return_flight: FlightOffer | None = Field(
        default=None,
        validation_alias=AliasChoices("return_flight", "return"),
        serialization_alias="return",
    )
    hotels: list[HotelStay] = Field(default_factory=list)
    itinerary: Itinerary
    totals: PackageTotals = Field(default_factory=PackageTotals)
    reasons: list[str] = Field(default_factory=list)


class PackageChoices(BaseModel):
    outbound_id: str | None = None
    return_id: str | None = None
    hotel_ids: list[str] = Field(default_factory=list)


class SwanPhase(str, Enum):
    ATTRACTIONS = "waiting_attractions"
    FLIGHTS = "waiting_flights"
    HOTELS = "waiting_hotels"
    READY = "ready"


class SwanView(BaseModel):
    plan_id: str
    phase: SwanPhase
    request: TripRequest
    flights: list[FlightOffer] = Field(default_factory=list)
    hotels: list[HotelOffer] = Field(default_factory=list)
    package: TravelPackage | None = None


class ConversationPhase(str, Enum):
    CHATTING = "chatting"
    PLANNING = "planning"
    PROPOSAL = "proposal"
    REVIEW = "review"
    BOOKED = "booked"


class TripFacts(BaseModel):
    destination: str | None = None
    origin: TripOrigin | None = None
    start_date: str | None = None
    end_date: str | None = None
    outbound_window: TimeOfDayWindow | None = None
    return_window: TimeOfDayWindow | None = None
    travellers: int | None = Field(default=None, ge=1)
    budget: Money | None = None
    pace: Pace | None = None
    interests: list[str] = Field(default_factory=list)
    notes: str | None = None

    def missing_required(self) -> list[str]:
        missing: list[str] = []
        if not self.destination:
            missing.append("destination")
        if not self.start_date or not self.end_date:
            missing.append("dates")
        origin = self.origin
        if origin is None or not (origin.airport_codes or origin.place):
            missing.append("origin")
        if self.travellers is None:
            missing.append("travellers")
        return missing

    def to_request(self) -> TripRequest:
        missing = self.missing_required()
        if missing:
            raise ValueError("missing " + ", ".join(missing))
        assert self.destination and self.origin and self.start_date and self.end_date
        assert self.travellers is not None
        return TripRequest(
            destination=self.destination,
            origin=self.origin,
            start_date=self.start_date,
            end_date=self.end_date,
            outbound_window=self.outbound_window or TimeOfDayWindow.ANY,
            return_window=self.return_window or TimeOfDayWindow.ANY,
            travellers=self.travellers,
            budget=self.budget,
            notes=self.notes,
        )


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ControlType(str, Enum):
    CHIPS = "chips"
    DATE_RANGE = "date_range"
    STEPPER = "stepper"
    SLIDER = "slider"
    AIRPORT = "airport"
    TILES = "tiles"


class Control(BaseModel):
    slot: str
    type: ControlType
    options: list[str] | None = None
    min: float | None = None
    max: float | None = None
    value: Any | None = None


class ChatAnswer(BaseModel):
    slot: str
    value: Any


class ChatMessage(BaseModel):
    id: str
    role: ChatRole
    text: str
    controls: list[Control] = Field(default_factory=list)
    answers: list[ChatAnswer] | None = None
    created_at: datetime


class TripConversation(BaseModel):
    trip_id: str
    phase: ConversationPhase
    messages: list[ChatMessage] = Field(default_factory=list)
    brief: TripFacts = Field(default_factory=TripFacts)

    @computed_field
    @property
    def missing(self) -> list[str]:
        return self.brief.missing_required()


class SuggestionKind(str, Enum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    ATTRACTION = "attraction"
    TRANSFER = "transfer"


class SuggestionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    MODIFYING = "modifying"
    REJECTED = "rejected"
    REPLACED = "replaced"
    BOOKED = "booked"


class Suggestion(BaseModel):
    id: str
    kind: SuggestionKind
    status: SuggestionStatus = SuggestionStatus.PROPOSED
    item: FlightOffer | HotelStay | Stop
    why: list[str] = Field(default_factory=list)
    alternatives_available: bool = False
    required: bool = False

    @model_validator(mode="after")
    def item_matches_kind(self) -> Suggestion:
        expected: type[BaseModel] = {
            SuggestionKind.FLIGHT: FlightOffer,
            SuggestionKind.HOTEL: HotelStay,
            SuggestionKind.ATTRACTION: Stop,
            SuggestionKind.TRANSFER: Stop,
        }[self.kind]
        if not isinstance(self.item, expected):
            raise ValueError(f"{self.kind.value} suggestion item must be {expected.__name__}")
        return self


class Proposal(BaseModel):
    trip_id: str
    package: TravelPackage
    suggestions: list[Suggestion]
    totals: PackageTotals


class SuggestionActionName(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"
    UNDO = "undo"


class SuggestionAction(BaseModel):
    suggestion_id: str
    action: SuggestionActionName
    reason: str | None = None
    alternative_id: str | None = None
    constraints: dict[str, Any] | None = None
    text: str | None = None


class TripView(BaseModel):
    conversation: TripConversation
    proposal: Proposal | None = None


class SuggestionResult(BaseModel):
    proposal: Proposal
    alternatives: list[Suggestion] = Field(default_factory=list)


class ScriptedChange(BaseModel):
    action: SuggestionAction
    proposal: Proposal


class ConversationFixture(BaseModel):
    conversation: TripConversation
    proposal: Proposal
    accept: ScriptedChange
    modify: ScriptedChange
    reject: ScriptedChange
