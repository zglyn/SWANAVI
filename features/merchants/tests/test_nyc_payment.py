import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from roam_contracts.models import Quote
from roam_contracts.signing import quote_signing_bytes
from roam_merchants import server
from roam_merchants.directory import Directory
from roam_merchants.payments import EscrowEvidence, FakeLedgerVerifier, PaymentProof, encode_payment_header

ROOT = Path(__file__).resolve().parents[3]
CITY = json.loads((ROOT / "contracts" / "fixtures" / "demo_city.json").read_text())
NYC = (
    "central-park-bikes",
    "midtown-food-workshop",
    "midtown-food-tasting",
    "times-square-souvenir",
)
TX = "B" * 64
OWNER = "rNycTrip"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(server, "ledger", FakeLedgerVerifier())
    monkeypatch.setattr(server, "bookings", server.BookingBook())
    monkeypatch.setattr(server, "directory", Directory())


@pytest.fixture
def client():
    return TestClient(server.http)


def shops_by_id(client):
    return {row["merchant_id"]: row for row in client.get("/merchants").json()}


def catalog(merchant_id):
    rows = server.search_catalog(merchant_id)
    assert len(rows) == 1
    return rows[0]


def book(client, merchant_id, item, headers=None):
    return client.post(
        f"/m/{merchant_id}/book",
        json={"sku": item["sku"], "slot_start": item["slot_start"]},
        headers=headers or {},
    )


def quote_for(client, merchant_id):
    response = book(client, merchant_id, catalog(merchant_id))
    assert response.status_code == 402
    body = response.json()
    assert body["quote"]["merchant_id"] == merchant_id
    return body["quote"]


def verify(quote, pubkey):
    parsed = Quote.model_validate(quote)
    VerifyKey(bytes.fromhex(pubkey)).verify(quote_signing_bytes(parsed), bytes.fromhex(parsed.merchant_signature))


def remember(quote, sequence, **overrides):
    invoice = overrides.pop("invoice", quote["invoice_id"])
    proof_invoice = overrides.pop("proof_invoice", quote["invoice_id"])
    amount = Decimal(str(overrides.pop("amount", quote["amount"])))
    server.ledger.record(TX, EscrowEvidence(
        owner=OWNER,
        sequence=sequence,
        destination=overrides.pop("destination", quote["merchant_address"]),
        amount=amount,
        currency=overrides.pop("currency", "XRP"),
        memo_invoice_ids=[str(invoice).upper()],
        validated=overrides.pop("validated", True),
        still_locked=overrides.pop("still_locked", True),
    ))
    return PaymentProof(
        invoice_id=proof_invoice,
        batch_tx_hash=TX,
        escrow_owner=OWNER,
        escrow_sequence=sequence,
    )


def pay(client, merchant_id, quote, proof):
    item = catalog(merchant_id)
    return book(client, merchant_id, item, {"X-PAYMENT": encode_payment_header(proof)})


def test_new_york_discovery_lists_the_four_demo_shops(client):
    found = client.get("/registry", params={"city": "New York"}).json()
    assert {row["merchant_id"] for row in found} == set(NYC)
    tool_rows = server.find_merchants("New York")
    assert {row["merchant_id"] for row in tool_rows} == set(NYC)


def test_catalog_keeps_each_shops_indoor_and_refundable_flags():
    flags = {row["id"]: row for row in CITY["merchants"]}
    assert set(flags) == set(NYC)
    for merchant_id, row in flags.items():
        item = catalog(merchant_id)
        assert item["indoor"] is row["indoor"]
        assert item["refundable"] is row["refundable"]
        assert item["price"] == row["amount"]


def test_new_york_quote_is_a_real_402_signed_by_that_shop_and_fresh(client):
    keys = shops_by_id(client)
    assert len({keys[merchant_id]["pubkey_ed25519"] for merchant_id in NYC}) == len(NYC)
    valid = timedelta(hours=CITY["quote_valid_hours"])
    escrow = timedelta(hours=CITY["escrow_cancel_after_hours"])
    for merchant_id in NYC:
        item = catalog(merchant_id)
        before = datetime.now(timezone.utc)
        response = book(client, merchant_id, item)
        after = datetime.now(timezone.utc)
        assert response.status_code == 402
        body = response.json()
        quote = body["quote"]
        assert body["x402Version"] == 1
        assert body["accepts"][0]["pay_to"] == quote["merchant_address"]
        assert body["accepts"][0]["amount"] == quote["amount"]
        verify(quote, keys[merchant_id]["pubkey_ed25519"])
        other = next(shop for shop in NYC if shop != merchant_id)
        with pytest.raises(BadSignatureError):
            verify(quote, keys[other]["pubkey_ed25519"])
        expires = datetime.fromisoformat(quote["expires_at"])
        cancel = datetime.fromisoformat(quote["cancel_after"])
        assert before + valid <= expires <= after + valid
        assert before + escrow <= cancel <= after + escrow
        again = book(client, merchant_id, item).json()["quote"]
        assert again["expires_at"] == quote["expires_at"]
        assert again["merchant_signature"] == quote["merchant_signature"]
        tool_quote = server.get_quote(merchant_id, item["sku"], item["slot_start"])
        assert tool_quote["merchant_signature"] == quote["merchant_signature"]


def test_matching_sandbox_proof_confirms_and_a_repeat_matches(client):
    quote = quote_for(client, "central-park-bikes")
    proof = remember(quote, 11)
    header = {"X-PAYMENT": encode_payment_header(proof)}
    item = catalog("central-park-bikes")
    first = book(client, "central-park-bikes", item, header)
    second = book(client, "central-park-bikes", item, header)
    assert first.status_code == 200
    assert first.json() == second.json()
    booking = first.json()
    assert booking["status"] == "confirmed"
    assert booking["settlement"] == "sandbox"
    assert booking["invoice_id"] == quote["invoice_id"]
    assert len(booking["confirmation_code"]) == 6
    listed = client.get(f"/m/central-park-bikes/bookings/{quote['invoice_id']}").json()
    assert listed == booking
    tool = server.book("central-park-bikes", item["sku"], item["slot_start"], proof.model_dump())
    assert tool["status"] == "confirmed"
    assert tool["settlement"] == "sandbox"
    assert tool["confirmation_code"] == booking["confirmation_code"]


def test_invalid_proofs_do_not_create_bookings(client):
    quote = quote_for(client, "midtown-food-tasting")
    cases = [
        remember(quote, 21, amount="1.00"),
        remember(quote, 22, validated=False),
        PaymentProof(invoice_id=quote["invoice_id"], batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=99),
    ]
    for proof in cases:
        response = pay(client, "midtown-food-tasting", quote, proof)
        assert response.status_code == 402
        assert client.get(f"/m/midtown-food-tasting/bookings/{quote['invoice_id']}").status_code == 404


def test_one_escrow_cannot_confirm_another_new_york_booking(client):
    bike = quote_for(client, "central-park-bikes")
    workshop = quote_for(client, "midtown-food-workshop")
    proof = remember(bike, 31)
    assert pay(client, "central-park-bikes", bike, proof).status_code == 200
    reused = PaymentProof(
        invoice_id=workshop["invoice_id"], batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=31,
    )
    response = pay(client, "midtown-food-workshop", workshop, reused)
    assert response.status_code == 402
    assert "different booking" in response.json()["error"]
    assert client.get(f"/m/midtown-food-workshop/bookings/{workshop['invoice_id']}").status_code == 404
    kept = client.get(f"/m/central-park-bikes/bookings/{bike['invoice_id']}").json()
    assert kept["status"] == "confirmed"
    assert kept["settlement"] == "sandbox"


def test_discovery_tools_and_readme_share_one_mcp_mount(client):
    found = client.get("/registry", params={"city": "New York"}).json()
    urls = {row["mcp_url"] for row in found}
    assert len(urls) == 1
    url = urls.pop()
    assert urlparse(url).path == "/mcp"
    tool_urls = {row["mcp_url"] for row in server.find_merchants("New York")}
    assert tool_urls == {url}
    readme = (ROOT / "features/merchants/README.md").read_text()
    assert url in readme
    assert "/m/{merchant_id}/mcp" not in readme
    assert client.get("/m/central-park-bikes/mcp").status_code == 404
    with TestClient(server.http) as live:
        mounted = live.get("/mcp")
    assert mounted.status_code == 400
    assert mounted.json()["jsonrpc"] == "2.0"
