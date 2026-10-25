import base64
import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from roam_contracts.models import INVOICE_MEMO_TYPE, PaymentProof
from roam_merchants import server
from roam_merchants.payments import (
    EscrowEvidence,
    FakeLedgerVerifier,
    XrplLedgerVerifier,
    encode_payment_header,
)

BIKE = {"sku": "BIKE-2H", "slot_start": "2026-11-14T14:00:00+09:00"}
TX = "A" * 64
OWNER = "rTripAccount"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(server, "ledger", FakeLedgerVerifier())
    monkeypatch.setattr(server, "bookings", server.BookingBook())


@pytest.fixture
def client():
    return TestClient(server.http)


def ask(client, headers=None):
    return client.post("/m/bamboo-bikes/book", json=BIKE, headers=headers or {})


def pay(quote, *, amount=None, destination=None, invoice=None, sequence=101, still_locked=True):
    server.ledger.record(TX, EscrowEvidence(
        owner=OWNER, sequence=sequence,
        destination=destination or quote["merchant_address"],
        amount=Decimal(amount or quote["amount"]), currency="XRP",
        memo_invoice_ids=[(invoice or quote["invoice_id"]).upper()], still_locked=still_locked,
    ))
    return PaymentProof(invoice_id=quote["invoice_id"], batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=sequence)


def test_no_payment_returns_402_with_quote_and_instructions(client):
    response = ask(client)
    assert response.status_code == 402
    body = response.json()
    assert body["x402Version"] == 1
    assert body["quote"]["sku"] == "BIKE-2H"
    requirement = body["accepts"][0]
    assert requirement["scheme"] == "xrpl_escrow"
    assert requirement["pay_to"] == body["quote"]["merchant_address"]
    assert requirement["amount"] == body["quote"]["amount"]
    assert requirement["memo_data"] == body["quote"]["invoice_id"]
    assert requirement["memo_type"] == INVOICE_MEMO_TYPE.encode().hex().upper()


def test_valid_payment_confirms_booking(client):
    quote = ask(client).json()["quote"]
    proof = pay(quote)
    response = ask(client, {"X-PAYMENT": encode_payment_header(proof)})
    assert response.status_code == 200
    booking = response.json()
    assert booking["status"] == "confirmed"
    assert booking["invoice_id"] == quote["invoice_id"]
    assert len(booking["confirmation_code"]) == 6
    receipt = json.loads(base64.b64decode(response.headers["X-PAYMENT-RESPONSE"]))
    assert receipt == {"success": True, "invoice_id": quote["invoice_id"], "transaction": TX}


def test_retry_with_same_proof_returns_same_booking(client):
    quote = ask(client).json()["quote"]
    header = {"X-PAYMENT": encode_payment_header(pay(quote))}
    first, second = ask(client, header).json(), ask(client, header).json()
    assert first == second


def test_plain_json_header_is_accepted(client):
    quote = ask(client).json()["quote"]
    response = ask(client, {"X-PAYMENT": pay(quote).model_dump_json()})
    assert response.status_code == 200


@pytest.mark.parametrize("tamper, message", [
    ({"amount": "1.00"}, "escrow holds 1.00"),
    ({"destination": "rScammer"}, "escrow pays rScammer"),
    ({"invoice": "B" * 64}, "memo doesn't carry this invoice id"),
    ({"still_locked": False}, "already cancelled or finished"),
])
def test_bad_payments_are_refused(client, tamper, message):
    quote = ask(client).json()["quote"]
    response = ask(client, {"X-PAYMENT": encode_payment_header(pay(quote, **tamper))})
    assert response.status_code == 402
    assert message in response.json()["error"]


def test_unknown_escrow_is_refused(client):
    quote = ask(client).json()["quote"]
    proof = PaymentProof(invoice_id=quote["invoice_id"], batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=999)
    response = ask(client, {"X-PAYMENT": encode_payment_header(proof)})
    assert response.status_code == 402
    assert "no escrow found" in response.json()["error"]


def test_one_escrow_cannot_pay_for_two_bookings(client):
    bike = ask(client).json()["quote"]
    proof = pay(bike)
    assert ask(client, {"X-PAYMENT": encode_payment_header(proof)}).status_code == 200
    matcha = client.post("/m/kissa-matcha/book", json={"sku": "MATCHA-WS", "slot_start": "2026-11-14T16:00:00+09:00"}).json()["quote"]
    reused = PaymentProof(invoice_id=matcha["invoice_id"], batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=101)
    response = client.post("/m/kissa-matcha/book", json={"sku": "MATCHA-WS", "slot_start": "2026-11-14T16:00:00+09:00"},
                           headers={"X-PAYMENT": encode_payment_header(reused)})
    assert response.status_code == 402
    assert "different booking" in response.json()["error"]


def test_garbage_header_is_400(client):
    assert ask(client, {"X-PAYMENT": "not-a-proof"}).status_code == 400


def test_unknown_shop_or_item_is_404(client):
    assert client.post("/m/nope/book", json=BIKE).status_code == 404
    assert client.post("/m/bamboo-bikes/book", json={"sku": "NOPE", "slot_start": BIKE["slot_start"]}).status_code == 404


def test_cancel_and_lookup(client):
    quote = ask(client).json()["quote"]
    ask(client, {"X-PAYMENT": encode_payment_header(pay(quote))})
    found = client.get(f"/m/bamboo-bikes/bookings/{quote['invoice_id']}").json()
    assert found["status"] == "confirmed"
    cancelled = client.post("/m/bamboo-bikes/cancel", json={"invoice_id": quote["invoice_id"]}).json()
    assert cancelled["status"] == "cancelled"


def test_dev_escrow_route_then_book(client):
    quote = ask(client).json()["quote"]
    client.post("/dev/escrows", json={"tx_hash": TX, "owner": OWNER, "sequence": 7, "destination": quote["merchant_address"],
                                      "amount": quote["amount"], "invoice_id": quote["invoice_id"]})
    proof = PaymentProof(invoice_id=quote["invoice_id"], batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=7)
    assert ask(client, {"X-PAYMENT": encode_payment_header(proof)}).status_code == 200


def test_mcp_book_tool_follows_the_same_rules():
    first = server.book("bamboo-bikes", BIKE["sku"], BIKE["slot_start"])
    assert first["status"] == "payment_required"
    proof = pay(first["quote"])
    second = server.book("bamboo-bikes", BIKE["sku"], BIKE["slot_start"], proof.model_dump())
    assert second["status"] == "confirmed"
    assert server.book("nope", "X", BIKE["slot_start"])["status"] == "error"


def test_xrpl_verifier_reads_a_batch_from_the_node():
    invoice = "C" * 64
    memo = {"Memo": {"MemoType": INVOICE_MEMO_TYPE.encode().hex().upper(), "MemoData": invoice}}
    tx_result = {"validated": True, "meta": {"TransactionResult": "tesSUCCESS"}, "tx_json": {
        "TransactionType": "Batch",
        "RawTransactions": [
            {"RawTransaction": {"TransactionType": "EscrowCreate", "Account": OWNER, "Sequence": 100,
                                "Destination": "rOther", "Amount": "30000000"}},
            {"RawTransaction": {"TransactionType": "EscrowCreate", "Account": OWNER, "Sequence": 101,
                                "Destination": "rBike", "Amount": "15000000", "Memos": [memo]}},
        ],
    }}

    def node(request: httpx.Request) -> httpx.Response:
        method = json.loads(request.content)["method"]
        result = tx_result if method == "tx" else {"node": {"LedgerEntryType": "Escrow"}}
        return httpx.Response(200, json={"result": result})

    verifier = XrplLedgerVerifier("http://node", httpx.Client(transport=httpx.MockTransport(node)))
    evidence = verifier.lookup(PaymentProof(invoice_id=invoice, batch_tx_hash=TX, escrow_owner=OWNER, escrow_sequence=101))
    assert evidence is not None
    assert (evidence.destination, evidence.amount, evidence.currency) == ("rBike", Decimal("15"), "XRP")
    assert evidence.memo_invoice_ids == [invoice]
    assert evidence.validated and evidence.still_locked
