from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastmcp import FastMCP
from pydantic import BaseModel, ValidationError

from roam_contracts.models import Category, GeoPoint, PaymentProof
from roam_merchants.directory import Directory
from roam_merchants.payments import (
    BookingBook,
    EscrowEvidence,
    FakeLedgerVerifier,
    check_payment,
    decode_payment_header,
    make_verifier,
    merchant_by_id,
    payment_required_body,
    utc_now,
)

directory = Directory()
ledger = make_verifier()
bookings = BookingBook()
mcp = FastMCP("merchant-directory")


@mcp.tool(description="Find registered shops in a city. near is {lat, lng}. radius_km is kilometres from that point. Results are closest first. city is a name such as Kyoto.")
def find_merchants(city: str, category: str | None = None, near: dict | None = None, radius_km: float | None = None, open_at: str | None = None) -> list[dict]:
    point = GeoPoint.model_validate(near) if near else None
    cat = Category(category) if category else None
    moment = datetime.fromisoformat(open_at) if open_at else None
    return [merchant.model_dump(mode="json") for merchant in directory.find_merchants(city, cat, point, radius_km, moment)]


@mcp.tool(description="List bookable items for one merchant_id. date is optional ISO date. Nothing is charged.")
def search_catalog(merchant_id: str, date: str | None = None) -> list[dict]:
    moment = datetime.fromisoformat(date) if date else None
    return [item.model_dump(mode="json") for item in directory.search_catalog(merchant_id, moment)]


@mcp.tool(description="Sign a 402 quote for a SKU. slot_start is an ISO datetime. No money moves. The signature is ed25519 over the canonical quote.")
def get_quote(merchant_id: str, sku: str, slot_start: str) -> dict:
    quote = directory.get_quote(merchant_id, sku, datetime.fromisoformat(slot_start))
    return quote.model_dump(mode="json")


@mcp.tool(description=(
    "Book a SKU. Without payment_proof it returns status 'payment_required' with the signed quote and how to pay "
    "(an XRPL escrow to pay_to, carrying the invoice id as a memo). Pay through the guardrail, then call again with "
    "payment_proof = {invoice_id, batch_tx_hash, escrow_owner, escrow_sequence}. This tool never moves money."
))
def book(merchant_id: str, sku: str, slot_start: str, payment_proof: dict | None = None) -> dict:
    try:
        proof = PaymentProof.model_validate(payment_proof) if payment_proof else None
        status, body = _book(merchant_id, sku, slot_start, proof)
    except ValidationError:
        return {"status": "error", "error": "payment_proof needs invoice_id, batch_tx_hash, escrow_owner, escrow_sequence"}
    except HTTPException as exc:
        return {"status": "error", "error": exc.detail}
    return {"status": "confirmed" if status == 200 else "payment_required", **body}


# The MCP app's lifespan starts its session manager; without it every MCP request fails with
# "Task group is not initialized". Mounted at the root so the endpoint is /mcp (ROAM_MERCHANTS_MCP_URL).
mcp_app = mcp.http_app()
http = FastAPI(title="Swanavi merchants", lifespan=mcp_app.lifespan)


class BookRequest(BaseModel):
    sku: str
    slot_start: datetime


class CancelRequest(BaseModel):
    invoice_id: str


@http.get("/registry")
def registry(city: str):
    return [merchant.model_dump(mode="json") for merchant in directory.find_merchants(city)]


@http.get("/merchants")
def all_merchants():
    """Every shop with its quote-signing key; the guardrail verifies quote signatures against these."""
    return [merchant.model_dump(mode="json") for merchant in directory.list_merchants()]


@http.post("/m/{merchant_id}/book")
def book_http(merchant_id: str, body: BookRequest, x_payment: str | None = Header(default=None)):
    """No X-PAYMENT header → 402 with payment instructions. With a valid one → 200 and the booking."""
    proof = None
    if x_payment:
        try:
            proof = decode_payment_header(x_payment)
        except (ValueError, ValidationError):
            raise HTTPException(status_code=400, detail="X-PAYMENT is not a valid payment proof")
    status, payload = _book(merchant_id, body.sku, body.slot_start.isoformat(), proof)
    headers = {}
    if status == 200:
        receipt = json.dumps({"success": True, "invoice_id": payload["invoice_id"], "transaction": proof.batch_tx_hash})
        headers["X-PAYMENT-RESPONSE"] = base64.b64encode(receipt.encode()).decode()
    return JSONResponse(status_code=status, content=payload, headers=headers)


@http.post("/m/{merchant_id}/cancel")
def cancel(merchant_id: str, body: CancelRequest):
    """Releases the slot. The refund itself happens on the ledger (EscrowCancel), not here."""
    booking = bookings.cancel(body.invoice_id)
    if booking is None or booking.merchant_id != merchant_id:
        raise HTTPException(status_code=404, detail="no such booking")
    return booking.model_dump(mode="json")


@http.get("/m/{merchant_id}/bookings/{invoice_id}")
def get_booking(merchant_id: str, invoice_id: str):
    booking = bookings.by_invoice.get(invoice_id)
    if booking is None or booking.merchant_id != merchant_id:
        raise HTTPException(status_code=404, detail="no such booking")
    return booking.model_dump(mode="json")


class FakeEscrow(BaseModel):
    tx_hash: str
    owner: str
    sequence: int
    destination: str
    amount: Decimal
    currency: str = "XRP"
    invoice_id: str


@http.post("/dev/escrows")
def add_fake_escrow(body: FakeEscrow):
    """Only with MERCHANTS_LEDGER=fake: pretend an escrow landed on the ledger, so the flow can be tried end to end."""
    if not isinstance(ledger, FakeLedgerVerifier):
        raise HTTPException(status_code=404, detail="only available with MERCHANTS_LEDGER=fake")
    ledger.record(body.tx_hash, EscrowEvidence(
        owner=body.owner, sequence=body.sequence, destination=body.destination,
        amount=body.amount, currency=body.currency, memo_invoice_ids=[body.invoice_id.upper()],
    ))
    return {"ok": True}


@http.get("/dev/demo", response_class=HTMLResponse)
def payment_demo():
    """A click-through page for the 402 flow against the fake ledger."""
    return (Path(__file__).parent / "demo.html").read_text(encoding="utf-8")


def _book(merchant_id: str, sku: str, slot_start: str, proof: PaymentProof | None) -> tuple[int, dict]:
    if merchant_by_id(directory.merchants, merchant_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown merchant {merchant_id}")
    try:
        quote = directory.get_quote(merchant_id, sku, datetime.fromisoformat(slot_start))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{merchant_id} has no {sku} at {slot_start}")
    if proof is None:
        return 402, payment_required_body(quote)
    if bookings.escrow_used_elsewhere(quote, proof):
        return 402, payment_required_body(quote, "this escrow already paid for a different booking")
    errors = check_payment(quote, proof, ledger.lookup(proof), utc_now())
    if errors:
        return 402, payment_required_body(quote, "; ".join(errors))
    return 200, bookings.confirm(quote, proof).model_dump(mode="json")


http.mount("/", mcp_app)


def main() -> None:
    import uvicorn

    uvicorn.run(http, host="0.0.0.0", port=int(os.environ.get("MERCHANTS_PORT", "8001")))


if __name__ == "__main__":
    main()
