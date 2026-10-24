"""Feature boundaries. Each owner ships a real and a Fake implementation; select with ROAM_FAKES."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from .models import (
    Booking,
    CatalogItem,
    CheckoutResult,
    CosignRequest,
    CosignResponse,
    EscrowRef,
    InspectorEvent,
    MerchantProfile,
    PaymentProof,
    PolicyConfig,
    Quote,
    TxResult,
    UnsignedTx,
    WalletState,
)

Emit = Callable[[InspectorEvent], None]


class MerchantDirectory(Protocol):
    """Owner A — features/merchants. Real impl talks MCP/HTTP to :8001."""

    def list_merchants(self) -> list[MerchantProfile]: ...
    def search(self, query: str | None = None, date: datetime | None = None) -> list[CatalogItem]: ...
    def request_quote(self, merchant_id: str, sku: str, slot_start: datetime) -> Quote: ...
    def confirm(self, merchant_id: str, proof: PaymentProof) -> Booking: ...
    def cancel(self, merchant_id: str, invoice_id: str) -> Booking: ...


class Guardrail(Protocol):
    """Owner A — features/guardrail. Real impl is POST :8002/cosign. Never runs in the agent process with Key 2."""

    def get_policy(self) -> PolicyConfig: ...
    def set_policy(self, policy: PolicyConfig) -> PolicyConfig: ...
    def cosign(self, request: CosignRequest) -> CosignResponse: ...


class Ledger(Protocol):
    """Owner C — features/ledger. Python library; the only code that talks to XRPL (guardrail reads credentials itself)."""

    def build_checkout(self, quotes: list[Quote], payers: list[str] | None = None) -> UnsignedTx: ...
    def sign_as_agent(self, tx: UnsignedTx) -> dict: ...
    def submit_multisigned(
        self, tx: UnsignedTx, signer_blobs: list[dict], quotes: list[Quote], emit: Emit
    ) -> CheckoutResult: ...
    def cancel_escrow(self, ref: EscrowRef, emit: Emit) -> TxResult: ...
    def finish_escrow(self, ref: EscrowRef, emit: Emit, fulfillment: str | None = None) -> TxResult: ...
    def has_credential(self, address: str, credential_type: str = "Local_Merchant_KYC") -> bool: ...
    def wallet_state(self) -> WalletState: ...
