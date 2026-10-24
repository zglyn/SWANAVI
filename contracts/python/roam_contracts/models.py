"""Shared data contracts. Frozen at Hour 2 — add optional fields only. Mirror changes in contracts/ts/api.ts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

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
