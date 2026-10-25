"""The policy rules. Pure functions with no I/O: everything they need (merchant keys, credential results, the clock)
is passed in, so the fake and the real co-signer run exactly the same checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from roam_contracts.geo import haversine_km
from roam_contracts.models import (
    CREDENTIAL_TYPE,
    INVOICE_MEMO_TYPE,
    PolicyConfig,
    PolicyDecision,
    Quote,
    Violation,
    ViolationRule,
)
from roam_contracts.signing import quote_signing_bytes

DROPS_PER_XRP = Decimal(1_000_000)
CENTS = Decimal("0.01")
INVOICE_MEMO_TYPE_HEX = INVOICE_MEMO_TYPE.encode().hex().upper()


@dataclass
class Facts:
    """What the rules know about the world beyond the request itself."""

    now: datetime
    merchant_keys: dict[str, str] | None = None  # merchant_id -> ed25519 pubkey hex; None skips the signature rule
    verified: dict[str, bool] = field(default_factory=dict)  # merchant address -> holds our credential
    trip_account: str | None = None  # when set, the tx must spend from this account
    xrp_as_rlusd: bool = True  # demo: XRP escrows stand in for RLUSD 1:1 until trust lines exist


@dataclass
class InnerPayment:
    index: int
    account: str
    destination: str
    amount: Decimal
    currency: str
    invoice_ids: list[str]
    tx_type: str


def evaluate(quotes: list[Quote], tx_json: dict[str, Any], policy: PolicyConfig, spent_today: Decimal, facts: Facts) -> PolicyDecision:
    """Runs every rule and returns every violation, so the dashboard can show the full list."""
    violations: list[Violation] = []
    for quote in quotes:
        violations += check_signature(quote, facts.merchant_keys)
        violations += check_expiry(quote, facts.now)
    violations += check_tx_matches(quotes, tx_json, facts)
    total = sum((quote.amount for quote in quotes), Decimal("0"))
    remaining = policy.max_daily_budget - spent_today
    for quote in quotes:
        if quote.amount > policy.max_per_item:
            violations.append(Violation(
                rule=ViolationRule.MAX_PER_ITEM, invoice_id=quote.invoice_id, detail="Item exceeds per-item cap",
                expected=f"<= {policy.max_per_item}", actual=str(quote.amount),
            ))
    if total > remaining:
        violations.append(Violation(
            rule=ViolationRule.MAX_DAILY_BUDGET, invoice_id=quotes[0].invoice_id if len(quotes) == 1 else None,
            detail="Exceeds remaining daily budget", expected=f"<= {remaining:.2f}", actual=f"{total:.2f}",
        ))
    for quote in quotes:
        violations += check_credential(quote, policy, facts.verified)
        violations += check_category(quote, policy)
        violations += check_date_window(quote, policy)
        violations += check_geofence(quote, policy)
    approved = not violations
    # What's left after this decision: the purchase counts only if it goes through.
    left = (remaining - total if approved else remaining).quantize(CENTS)
    return PolicyDecision(approved=approved, violations=violations, total=total, remaining_daily_budget=left)


def check_signature(quote: Quote, merchant_keys: dict[str, str] | None) -> list[Violation]:
    if merchant_keys is None:
        return []
    key = merchant_keys.get(quote.merchant_id)
    if key is None:
        return [_v(ViolationRule.QUOTE_SIGNATURE, quote, f"No public key known for {quote.merchant_id}")]
    try:
        VerifyKey(bytes.fromhex(key)).verify(quote_signing_bytes(quote), bytes.fromhex(quote.merchant_signature))
    except (BadSignatureError, ValueError):
        return [_v(ViolationRule.QUOTE_SIGNATURE, quote, f"Quote signature invalid for {quote.merchant_id}")]
    return []


def check_expiry(quote: Quote, now: datetime) -> list[Violation]:
    if now < quote.expires_at:
        return []
    minutes = int((now - quote.expires_at).total_seconds() // 60)
    return [_v(ViolationRule.QUOTE_EXPIRED, quote, f"Quote expired {minutes} min ago",
               expected=f"before {quote.expires_at.isoformat()}", actual=now.isoformat())]


def check_tx_matches(quotes: list[Quote], tx_json: dict[str, Any], facts: Facts) -> list[Violation]:
    """Recomputes what the transaction actually does from the raw tx. Never trusts the agent's summary."""
    rule = ViolationRule.TX_QUOTE_MISMATCH
    payments, problems = inner_payments(tx_json)
    out = [Violation(rule=rule, detail=p) for p in problems]
    outer = tx_json.get("Account", "")
    if facts.trip_account and outer != facts.trip_account:
        out.append(Violation(rule=rule, detail=f"Transaction spends from {outer}, not the trip account",
                             expected=facts.trip_account, actual=outer))
    by_invoice = {quote.invoice_id.upper(): quote for quote in quotes}
    covered: dict[str, int] = {}
    for p in payments:
        n = p.index + 1
        if p.tx_type != "EscrowCreate":
            out.append(Violation(rule=rule, detail=f"Inner tx #{n} is a {p.tx_type}, only EscrowCreate is allowed"))
            continue
        if p.account != outer:
            out.append(Violation(rule=rule, detail=f"Inner tx #{n} spends from {p.account}, not {outer}"))
        matches = [by_invoice[i] for i in p.invoice_ids if i in by_invoice]
        if len(matches) != 1:
            out.append(Violation(rule=rule, detail=f"Inner tx #{n} doesn't carry exactly one quoted invoice memo",
                                 expected="1 invoice", actual=",".join(p.invoice_ids) or "none"))
            continue
        quote = matches[0]
        covered[quote.invoice_id.upper()] = covered.get(quote.invoice_id.upper(), 0) + 1
        if p.destination != quote.merchant_address:
            out.append(_v(rule, quote, f"Inner tx #{n} pays {p.destination} but quote says {quote.merchant_address}",
                          expected=quote.merchant_address, actual=p.destination))
        if p.amount != quote.amount:
            out.append(_v(rule, quote, f"Inner tx #{n} locks {p.amount} but quote says {quote.amount}",
                          expected=str(quote.amount), actual=str(p.amount)))
        if not _currency_ok(quote.currency, p.currency, facts.xrp_as_rlusd):
            out.append(_v(rule, quote, f"Inner tx #{n} is in {p.currency} but quote says {quote.currency}",
                          expected=quote.currency, actual=p.currency))
    for quote in quotes:
        count = covered.get(quote.invoice_id.upper(), 0)
        if count != 1:
            out.append(_v(rule, quote, f"{quote.merchant_id} is paid by {count} inner txs, expected exactly 1",
                          expected="1", actual=str(count)))
    return out


def check_credential(quote: Quote, policy: PolicyConfig, verified: dict[str, bool]) -> list[Violation]:
    if not policy.require_verified_credential or verified.get(quote.merchant_address):
        return []
    return [_v(ViolationRule.VERIFIED_CREDENTIAL, quote, f"Destination holds no {CREDENTIAL_TYPE} credential",
               expected="credential", actual="none")]


def check_category(quote: Quote, policy: PolicyConfig) -> list[Violation]:
    if quote.category in policy.allowed_categories:
        return []
    return [_v(ViolationRule.CATEGORY, quote, "Category not allowed",
               expected=",".join(c.value for c in policy.allowed_categories), actual=quote.category.value)]


def check_date_window(quote: Quote, policy: PolicyConfig) -> list[Violation]:
    start, end = policy.date_window_start, policy.date_window_end
    if (start is None or quote.slot_start >= start) and (end is None or quote.slot_end <= end):
        return []
    window = f"{start.isoformat() if start else '…'} to {end.isoformat() if end else '…'}"
    return [_v(ViolationRule.DATE_WINDOW, quote, "Slot is outside the trip dates", expected=window,
               actual=f"{quote.slot_start.isoformat()} to {quote.slot_end.isoformat()}")]


def check_geofence(quote: Quote, policy: PolicyConfig) -> list[Violation]:
    fence = policy.geofence
    if fence is None:
        return []
    km = haversine_km(fence.center.lat, fence.center.lng, quote.location.lat, quote.location.lng)
    if km <= fence.radius_km:
        return []
    return [_v(ViolationRule.GEOFENCE, quote, f"{quote.merchant_name} is {km:.1f} km from the trip area",
               expected=f"<= {fence.radius_km} km", actual=f"{km:.1f} km")]


def inner_payments(tx_json: dict[str, Any]) -> tuple[list[InnerPayment], list[str]]:
    """A Batch carries its escrows as RawTransactions; a single purchase is a lone EscrowCreate."""
    tx_type = tx_json.get("TransactionType")
    if tx_type == "Batch":
        bodies = [row.get("RawTransaction", {}) for row in tx_json.get("RawTransactions", [])]
    elif tx_type == "EscrowCreate":
        bodies = [tx_json]
    else:
        return [], [f"Transaction is a {tx_type}, expected a Batch or EscrowCreate"]
    payments = []
    for index, body in enumerate(bodies):
        amount, currency = parse_amount(body.get("Amount"))
        payments.append(InnerPayment(
            index=index, account=body.get("Account", ""), destination=body.get("Destination", ""),
            amount=amount, currency=currency, invoice_ids=memo_invoice_ids(body), tx_type=body.get("TransactionType", ""),
        ))
    return payments, []


def parse_amount(raw: Any) -> tuple[Decimal, str]:
    if isinstance(raw, dict):  # issued currency, e.g. RLUSD
        return Decimal(str(raw.get("value", "0"))), str(raw.get("currency", ""))
    return Decimal(str(raw or "0")) / DROPS_PER_XRP, "XRP"


def memo_invoice_ids(body: dict[str, Any]) -> list[str]:
    ids = []
    for row in body.get("Memos", []):
        memo = row.get("Memo", {})
        if memo.get("MemoType", "").upper() != INVOICE_MEMO_TYPE_HEX:
            continue
        data = memo.get("MemoData", "")
        # MemoData is hex: either the 64-char invoice id itself, or that id hex-encoded as text.
        if len(data) == 128:
            try:
                data = bytes.fromhex(data).decode()
            except ValueError:
                pass
        ids.append(data.upper())
    return ids


def _currency_ok(quoted: str, on_ledger: str, xrp_as_rlusd: bool) -> bool:
    return quoted == on_ledger or (xrp_as_rlusd and quoted == "RLUSD" and on_ledger == "XRP")


def _v(rule: ViolationRule, quote: Quote, detail: str, expected: str | None = None, actual: str | None = None) -> Violation:
    return Violation(rule=rule, invoice_id=quote.invoice_id, detail=detail, expected=expected, actual=actual)
