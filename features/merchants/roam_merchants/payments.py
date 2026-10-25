"""HTTP 402 payment step for the shop server.

Flow: the buyer asks to book → the shop answers 402 with the signed quote and payment instructions →
the buyer pays into an XRPL escrow (through the guardrail, outside this server) → the buyer retries with
an X-PAYMENT header → the shop checks the escrow on the ledger itself → booking confirmed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

import httpx

from roam_contracts.models import INVOICE_MEMO_TYPE, Booking, MerchantProfile, PaymentProof, Quote, source_tag_for

X402_VERSION = 1
SCHEME = "xrpl_escrow"
DEVNET_RPC = "https://s.devnet.rippletest.net:51234"
DROPS_PER_XRP = Decimal(1_000_000)


def _hex(text: str) -> str:
    return text.encode().hex().upper()


def payment_requirements(quote: Quote) -> dict[str, Any]:
    """What the buyer must put on the ledger for this quote."""
    return {
        "scheme": SCHEME,
        "network": os.environ.get("XRPL_NETWORK", "devnet"),
        "amount": str(quote.amount),
        "currency": quote.currency,
        "pay_to": quote.merchant_address,
        "memo_type": _hex(INVOICE_MEMO_TYPE),
        "memo_data": quote.invoice_id,
        "source_tag": source_tag_for(quote.invoice_id),
        "cancel_after": quote.cancel_after.isoformat(),
        "expires_at": quote.expires_at.isoformat(),
    }


def payment_required_body(quote: Quote, error: str = "payment required") -> dict[str, Any]:
    return {
        "x402Version": X402_VERSION,
        "error": error,
        "quote": quote.model_dump(mode="json"),
        "accepts": [payment_requirements(quote)],
    }


def encode_payment_header(proof: PaymentProof) -> str:
    return base64.b64encode(proof.model_dump_json().encode()).decode()


def decode_payment_header(value: str) -> PaymentProof:
    """X-PAYMENT is base64-encoded JSON (the x402 convention). Plain JSON is accepted too, for curl."""
    text = value.strip()
    if not text.startswith("{"):
        text = base64.b64decode(text).decode()
    return PaymentProof.model_validate_json(text)


@dataclass
class EscrowEvidence:
    """What the ledger says about the escrow named in a payment proof."""

    owner: str
    sequence: int
    destination: str
    amount: Decimal
    currency: str
    memo_invoice_ids: list[str] = field(default_factory=list)
    validated: bool = True
    still_locked: bool = True  # False once the escrow was cancelled or finished


class LedgerVerifier(Protocol):
    def lookup(self, proof: PaymentProof) -> EscrowEvidence | None: ...


class FakeLedgerVerifier:
    """In-memory stand-in until the real ledger exists. Tests and the /dev/escrows route add escrows here."""

    def __init__(self) -> None:
        self.escrows: dict[tuple[str, int], tuple[str, EscrowEvidence]] = {}

    def record(self, tx_hash: str, evidence: EscrowEvidence) -> None:
        self.escrows[(evidence.owner, evidence.sequence)] = (tx_hash.upper(), evidence)

    def lookup(self, proof: PaymentProof) -> EscrowEvidence | None:
        found = self.escrows.get((proof.escrow_owner, proof.escrow_sequence))
        if found is None or found[0] != proof.batch_tx_hash.upper():
            return None
        return found[1]


class XrplLedgerVerifier:
    """Reads the escrow straight from an XRPL node over JSON-RPC: the creating transaction for the memo,
    and the live escrow object to confirm it hasn't been cancelled or finished."""

    def __init__(self, rpc_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.rpc_url = rpc_url or os.environ.get("XRPL_RPC_URL", DEVNET_RPC)
        self.client = client or httpx.Client(timeout=10)

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(self.rpc_url, json={"method": method, "params": [params]})
        response.raise_for_status()
        return response.json().get("result", {})

    def lookup(self, proof: PaymentProof) -> EscrowEvidence | None:
        tx = self._rpc("tx", {"transaction": proof.batch_tx_hash})
        if tx.get("error"):
            return None
        validated = bool(tx.get("validated")) and tx.get("meta", {}).get("TransactionResult") == "tesSUCCESS"
        # A Batch carries its escrows as inner transactions; a lone EscrowCreate is the transaction itself.
        body = tx.get("tx_json", tx)
        if body.get("TransactionType") == "Batch":
            candidates = [row.get("RawTransaction", {}) for row in body.get("RawTransactions", [])]
        else:
            candidates = [body]
        create = next(
            (c for c in candidates
             if c.get("TransactionType") == "EscrowCreate"
             and c.get("Account") == proof.escrow_owner
             and c.get("Sequence") == proof.escrow_sequence),
            None,
        )
        if create is None:
            return None
        amount, currency = _parse_amount(create.get("Amount"))
        memos = [
            bytes.fromhex(m["Memo"]["MemoData"]).decode(errors="replace").upper()
            if _looks_like_hex_text(m["Memo"].get("MemoData", "")) else m["Memo"].get("MemoData", "").upper()
            for m in create.get("Memos", [])
            if m.get("Memo", {}).get("MemoType", "").upper() == _hex(INVOICE_MEMO_TYPE)
        ]
        entry = self._rpc("ledger_entry", {"escrow": {"owner": proof.escrow_owner, "seq": proof.escrow_sequence}})
        return EscrowEvidence(
            owner=proof.escrow_owner,
            sequence=proof.escrow_sequence,
            destination=create.get("Destination", ""),
            amount=amount,
            currency=currency,
            memo_invoice_ids=memos,
            validated=validated,
            still_locked="node" in entry,
        )


def _looks_like_hex_text(value: str) -> bool:
    """MemoData is hex. It holds either the 64-char invoice id itself or that id hex-encoded as text."""
    return len(value) == 128 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def _parse_amount(raw: Any) -> tuple[Decimal, str]:
    if isinstance(raw, dict):  # issued currency, e.g. RLUSD
        return Decimal(str(raw.get("value", "0"))), str(raw.get("currency", ""))
    return Decimal(str(raw or "0")) / DROPS_PER_XRP, "XRP"


def _currency_ok(quoted: str, on_ledger: str) -> bool:
    if quoted == on_ledger:
        return True
    # Until RLUSD trust lines exist, the demo settles in XRP shown as RLUSD 1:1 (features/ledger/SPEC.md §6).
    return quoted == "RLUSD" and on_ledger == "XRP" and os.environ.get("MERCHANTS_XRP_AS_RLUSD", "1") == "1"


def check_payment(quote: Quote, proof: PaymentProof, evidence: EscrowEvidence | None, now: datetime) -> list[str]:
    """Every reason this payment doesn't settle the quote. An empty list means it does."""
    if proof.invoice_id.upper() != quote.invoice_id.upper():
        return ["payment proof is for a different invoice"]
    if evidence is None:
        return ["no escrow found on the ledger for this proof"]
    errors = []
    if not evidence.validated:
        errors.append("escrow transaction is not validated")
    if not evidence.still_locked:
        errors.append("escrow was already cancelled or finished")
    if evidence.destination != quote.merchant_address:
        errors.append(f"escrow pays {evidence.destination}, not this shop ({quote.merchant_address})")
    if evidence.amount != quote.amount:
        errors.append(f"escrow holds {evidence.amount}, quote is {quote.amount}")
    if not _currency_ok(quote.currency, evidence.currency):
        errors.append(f"escrow is in {evidence.currency}, quote is in {quote.currency}")
    if quote.invoice_id.upper() not in evidence.memo_invoice_ids:
        errors.append("escrow memo doesn't carry this invoice id")
    if now > quote.expires_at:
        errors.append("quote has expired")
    return errors


class BookingBook:
    """The shop's bookings, in memory. One escrow can settle one invoice only."""

    def __init__(self) -> None:
        self.by_invoice: dict[str, Booking] = {}
        self.used_escrows: dict[tuple[str, int], str] = {}

    def confirm(self, quote: Quote, proof: PaymentProof) -> Booking:
        existing = self.by_invoice.get(quote.invoice_id)
        if existing is not None and existing.status == "confirmed":
            return existing  # a retry with the same proof gets the same booking
        code = hashlib.sha256(f"{quote.invoice_id}|{proof.batch_tx_hash}".encode()).hexdigest()[:6].upper()
        booking = Booking(invoice_id=quote.invoice_id, merchant_id=quote.merchant_id, sku=quote.sku,
                          status="confirmed", confirmation_code=code)
        self.by_invoice[quote.invoice_id] = booking
        self.used_escrows[(proof.escrow_owner, proof.escrow_sequence)] = quote.invoice_id
        return booking

    def escrow_used_elsewhere(self, quote: Quote, proof: PaymentProof) -> bool:
        used_for = self.used_escrows.get((proof.escrow_owner, proof.escrow_sequence))
        return used_for is not None and used_for != quote.invoice_id

    def cancel(self, invoice_id: str) -> Booking | None:
        booking = self.by_invoice.get(invoice_id)
        if booking is None:
            return None
        cancelled = booking.model_copy(update={"status": "cancelled"})
        self.by_invoice[invoice_id] = cancelled
        return cancelled


def make_verifier() -> LedgerVerifier:
    """MERCHANTS_LEDGER=fake (default, until features/ledger exists) or xrpl (reads XRPL_RPC_URL)."""
    return XrplLedgerVerifier() if os.environ.get("MERCHANTS_LEDGER", "fake") == "xrpl" else FakeLedgerVerifier()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def merchant_by_id(merchants: list[MerchantProfile], merchant_id: str) -> MerchantProfile | None:
    return next((m for m in merchants if m.merchant_id == merchant_id), None)
