import json
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from xrpl.core.binarycodec import encode_for_multisigning
from xrpl.core.keypairs import is_valid_message
from xrpl.wallet import Wallet

from roam_contracts.models import (
    INVOICE_MEMO_TYPE,
    Category,
    CosignRequest,
    Geofence,
    GeoPoint,
    PolicyConfig,
    Quote,
    UnsignedTx,
)
from roam_contracts.signing import quote_signing_bytes
from roam_guardrail import FakeGuardrail, HttpGuardrail, server
from roam_guardrail.client import FAKE_SIGNER
from roam_guardrail.cosigner import Cosigner
from roam_guardrail.sources import FIXTURES, OfflineCredentials, XrplCredentials, activity_policy, signer_blob

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
TRIP = "rTripAccount"
SHOP_KEY = SigningKey(bytes.fromhex("22" * 32))
KEYS = {row["merchant_id"]: SHOP_KEY.verify_key.encode().hex() for row in json.loads((FIXTURES / "merchants.json").read_text())}
DECISIONS = json.loads((FIXTURES / "policy_decisions.json").read_text())


def signed(quote: Quote, **changes) -> Quote:
    body = quote.model_copy(update={**changes, "merchant_signature": "00", "merchant_verified": None})
    return body.model_copy(update={"merchant_signature": SHOP_KEY.sign(quote_signing_bytes(body)).signature.hex()})


QUOTES = {q.merchant_id: signed(q) for q in (Quote.model_validate(row) for row in json.loads((FIXTURES / "quotes.json").read_text()))}
BIKE, MATCHA, SOUVENIR = QUOTES["bamboo-bikes"], QUOTES["kissa-matcha"], QUOTES["lucky-souvenir"]
PARK, WORKSHOP, TRAP = QUOTES["central-park-bikes"], QUOTES["midtown-food-workshop"], QUOTES["times-square-souvenir"]


def escrow(quote: Quote, sequence: int, **overrides) -> dict:
    body = {
        "TransactionType": "EscrowCreate", "Account": TRIP, "Destination": quote.merchant_address,
        "Amount": str(int(quote.amount * 1_000_000)), "CancelAfter": 900000000, "Sequence": sequence,
        "Memos": [{"Memo": {"MemoType": INVOICE_MEMO_TYPE.encode().hex().upper(), "MemoData": quote.invoice_id}}],
    }
    return {**body, **overrides}


def tx_for(quotes: list[Quote], inner: list[dict] | None = None) -> dict:
    inner = inner if inner is not None else [escrow(q, 11 + i) for i, q in enumerate(quotes)]
    if len(inner) == 1:
        return inner[0]
    return {"TransactionType": "Batch", "Account": TRIP, "Sequence": 10, "RawTransactions": [{"RawTransaction": t} for t in inner]}


def request(quotes: list[Quote], tx_json: dict | None = None, spent: str = "0", policy: PolicyConfig | None = None) -> CosignRequest:
    tx_json = tx_json if tx_json is not None else tx_for(quotes)
    return CosignRequest(tx=UnsignedTx(tx_json=tx_json, invoice_ids=[q.invoice_id for q in quotes]),
                         quotes=quotes, policy=policy or PolicyConfig(), spent_today=Decimal(spent))


@pytest.fixture
def guard():
    return FakeGuardrail(keys=lambda ids: KEYS, clock=lambda: NOW)


def rules_of(decision) -> list[str]:
    return [v.rule.value for v in decision.violations]


@pytest.fixture
def nyc(guard):
    guard.set_policy(activity_policy())
    return guard


# --- acceptance tests from SPEC.md §7 -------------------------------------


def test_bike_and_matcha_are_approved_and_signed(guard):
    response = guard.cosign(request([BIKE, MATCHA]))
    assert response.decision.model_dump(mode="json") == DECISIONS["approved_bike_matcha"]
    assert response.signer_blob == FAKE_SIGNER


def test_souvenir_is_blocked_with_every_reason(guard):
    guard.record_spend(Decimal("45"))
    response = guard.cosign(request([SOUVENIR]))
    assert response.decision.model_dump(mode="json") == DECISIONS["blocked_souvenir"]
    assert response.signer_blob is None


def test_swapped_destination_is_caught_even_within_caps(guard):
    tx = tx_for([BIKE], [escrow(BIKE, 11, Destination="rAttackerAddress")])
    decision = guard.evaluate(request([BIKE], tx))
    assert rules_of(decision) == ["tx_quote_mismatch"]
    assert "rAttackerAddress" in decision.violations[0].detail


def test_lowering_the_per_item_cap_blocks_matcha(monkeypatch, guard):
    monkeypatch.setattr(server, "cosigner", guard)
    client = TestClient(server.http)
    assert client.put("/policy", json={**PolicyConfig().model_dump(mode="json"), "max_per_item": "20"}).status_code == 200
    body = client.post("/cosign", json=request([MATCHA]).model_dump(mode="json")).json()
    assert body["decision"]["approved"] is False
    assert [v["rule"] for v in body["decision"]["violations"]] == ["max_per_item"]
    assert body["signer_blob"] is None


# --- one test per rule -----------------------------------------------------


def test_tampered_quote_fails_signature(guard):
    cheaper = BIKE.model_copy(update={"amount": Decimal("1.00")})
    assert "quote_signature" in rules_of(guard.evaluate(request([cheaper])))


def test_unknown_merchant_key_fails_signature():
    guard = FakeGuardrail(keys=lambda ids: {}, clock=lambda: NOW)
    assert rules_of(guard.evaluate(request([BIKE]))) == ["quote_signature"]


def test_expired_quote(guard):
    late = FakeGuardrail(keys=lambda ids: KEYS, clock=lambda: BIKE.expires_at + timedelta(minutes=3))
    decision = late.evaluate(request([BIKE]))
    assert rules_of(decision) == ["quote_expired"]
    assert decision.violations[0].detail == "Quote expired 3 min ago"


@pytest.mark.parametrize("inner, needle", [
    (lambda: [escrow(BIKE, 11, Amount="1000000")], "locks 1 but quote says 15.00"),
    (lambda: [escrow(BIKE, 11, Memos=[])], "exactly one quoted invoice memo"),
    (lambda: [escrow(BIKE, 11), escrow(MATCHA, 12, Account="rSomeoneElse")], "spends from rSomeoneElse"),
    (lambda: [escrow(BIKE, 11), escrow(BIKE, 12)], "paid by 2 inner txs"),
    (lambda: [escrow(BIKE, 11), {"TransactionType": "Payment", "Account": TRIP, "Destination": "rX", "Amount": "5"}], "only EscrowCreate"),
    (lambda: [escrow(BIKE, 11, Amount={"currency": "USD", "issuer": "rI", "value": "15.00"})], "in USD but quote says RLUSD"),
])
def test_tx_mismatches(guard, inner, needle):
    decision = guard.evaluate(request([BIKE], tx_for([BIKE], inner())))
    assert "tx_quote_mismatch" in rules_of(decision)
    assert any(needle in v.detail for v in decision.violations)


def test_quote_without_a_matching_inner_tx(guard):
    decision = guard.evaluate(request([BIKE, MATCHA], tx_for([BIKE])))
    assert any("kissa-matcha is paid by 0" in v.detail for v in decision.violations)


def test_rlusd_amount_and_hex_text_memo_are_understood(guard):
    memo = BIKE.invoice_id.encode().hex().upper()
    inner = escrow(BIKE, 11, Amount={"currency": "RLUSD", "issuer": "rI", "value": "15"},
                   Memos=[{"Memo": {"MemoType": INVOICE_MEMO_TYPE.encode().hex(), "MemoData": memo}}])
    assert guard.evaluate(request([BIKE], inner)).approved


def test_xrp_needs_the_demo_switch_to_count_as_rlusd():
    strict = Cosigner(OfflineCredentials(), sign=lambda tx: {}, keys=lambda ids: KEYS, xrp_as_rlusd=False, clock=lambda: NOW)
    assert rules_of(strict.evaluate(request([BIKE]))) == ["tx_quote_mismatch"]


def test_wrong_trip_account():
    guard = Cosigner(OfflineCredentials(), sign=lambda tx: {}, keys=lambda ids: KEYS, trip_account="rRealTrip", clock=lambda: NOW)
    assert rules_of(guard.evaluate(request([BIKE]))) == ["tx_quote_mismatch"]


def test_not_a_payment_transaction(guard):
    decision = guard.evaluate(request([BIKE], {"TransactionType": "AccountSet", "Account": TRIP}))
    assert "expected a Batch or EscrowCreate" in decision.violations[0].detail


def test_daily_budget(guard):
    guard.record_spend(Decimal("90"))
    decision = guard.evaluate(request([BIKE]))
    assert rules_of(decision) == ["max_daily_budget"]
    assert (decision.violations[0].expected, decision.violations[0].actual) == ("<= 10.00", "15.00")


def test_category(guard):
    guard.set_policy(PolicyConfig(allowed_categories=[Category.FOOD]))
    assert rules_of(guard.evaluate(request([BIKE]))) == ["category"]


def test_credential_not_required(guard):
    guard.set_policy(PolicyConfig(require_verified_credential=False, max_per_item=Decimal("600"), max_daily_budget=Decimal("600"),
                                  allowed_categories=list(Category)))
    assert guard.evaluate(request([SOUVENIR])).approved


def test_date_window(guard):
    guard.set_policy(PolicyConfig(date_window_start=datetime(2026, 11, 15, tzinfo=timezone.utc)))
    assert rules_of(guard.evaluate(request([BIKE]))) == ["date_window"]


def test_geofence(guard):
    guard.set_policy(PolicyConfig(geofence=Geofence(center=GeoPoint(lat=35.0116, lng=135.7681), radius_km=5)))
    decision = guard.evaluate(request([BIKE]))  # Arashiyama is ~9 km from central Kyoto
    assert rules_of(decision) == ["geofence"]
    guard.set_policy(PolicyConfig(geofence=Geofence(center=GeoPoint(lat=35.0116, lng=135.7681), radius_km=15)))
    assert guard.evaluate(request([BIKE])).approved


# --- what the guardrail refuses to trust -----------------------------------


def test_client_spent_today_is_not_the_budget(guard):
    decision = guard.evaluate(request([BIKE], spent="90"))
    assert decision.approved
    assert "max_daily_budget" not in rules_of(decision)


def test_reset_clears_recorded_spend(guard):
    guard.record_spend(Decimal("90"))
    assert not guard.evaluate(request([BIKE])).approved
    guard.reset()
    assert guard.evaluate(request([BIKE])).approved


def test_request_policy_is_ignored(guard):
    permissive = PolicyConfig(max_per_item=Decimal("1000"), max_daily_budget=Decimal("1000"),
                              require_verified_credential=False, allowed_categories=list(Category))
    assert not guard.cosign(request([SOUVENIR], policy=permissive)).decision.approved


def test_spending_is_counted_even_if_the_agent_says_zero(guard):
    assert guard.cosign(request([BIKE, MATCHA])).decision.approved
    assert guard.cosign(request([BIKE, MATCHA])).decision.approved
    third = guard.cosign(request([BIKE]))  # 90 already co-signed today; the agent claims 0
    assert rules_of(third.decision) == ["max_daily_budget"]


def test_evaluate_never_counts_spend(guard):
    for _ in range(5):
        assert guard.evaluate(request([BIKE, MATCHA])).approved


def test_unsignable_tx_is_refused():
    def broken(tx):
        raise ValueError("bad tx")
    guard = Cosigner(OfflineCredentials(), sign=broken, keys=lambda ids: KEYS, clock=lambda: NOW)
    response = guard.cosign(request([BIKE]))
    assert response.signer_blob is None and not response.decision.approved
    assert response.decision.remaining_daily_budget == Decimal("100")


def test_policy_validation(monkeypatch, guard):
    monkeypatch.setattr(server, "cosigner", guard)
    client = TestClient(server.http)
    bad = {**PolicyConfig().model_dump(mode="json"), "max_per_item": "200"}
    assert client.put("/policy", json=bad).status_code == 422
    assert client.post("/reset").json()["max_per_item"] == "45"


def test_http_client_round_trip(monkeypatch, guard):
    monkeypatch.setattr(server, "cosigner", guard)
    remote = HttpGuardrail("http://testserver", client=TestClient(server.http))
    assert remote.get_policy().max_per_item == Decimal("45")
    assert remote.cosign(request([BIKE])).decision.approved
    assert not remote.evaluate(request([SOUVENIR])).approved


# --- real signing and credential lookups -----------------------------------


def test_signer_blob_is_a_valid_multisig_signature():
    guardrail, trip, shop1, shop2 = Wallet.create(), Wallet.create(), Wallet.create(), Wallet.create()
    quotes = [signed(BIKE, merchant_address=shop1.classic_address), signed(MATCHA, merchant_address=shop2.classic_address)]
    inner = [escrow(q, 11 + i, Account=trip.classic_address, Flags=0x40000000, Fee="0", SigningPubKey="") for i, q in enumerate(quotes)]
    tx = {**tx_for(quotes, inner), "Account": trip.classic_address, "Flags": 0x00010000, "Fee": "40", "SigningPubKey": ""}
    real = Cosigner(OfflineCredentials({shop1.classic_address, shop2.classic_address}),
                    sign=lambda t: signer_blob(t, guardrail), keys=lambda ids: KEYS, trip_account=trip.classic_address, clock=lambda: NOW)
    blob = real.cosign(request(quotes, tx)).signer_blob["Signer"]
    assert blob["Account"] == guardrail.classic_address
    message = bytes.fromhex(encode_for_multisigning(tx, guardrail.classic_address))
    assert is_valid_message(message, bytes.fromhex(blob["TxnSignature"]), blob["SigningPubKey"])


def credential_node(flags=0x00010000, expiration=None):
    node = {"LedgerEntryType": "Credential", "Flags": flags}
    if expiration is not None:
        node["Expiration"] = expiration
    return {"result": {"node": node}}


@pytest.mark.parametrize("reply, expected", [
    (credential_node(), True),
    (credential_node(flags=0), False),  # issued but never accepted
    (credential_node(expiration=1), False),  # expired in 2000
    ({"result": {"error": "entryNotFound"}}, False),
])
def test_xrpl_credential_lookup(reply, expected):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=reply)

    creds = XrplCredentials("rIssuer", rpc_url="http://node", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert creds.verified(["rShop"], NOW) == {"rShop": expected}
    params = seen[0]["params"][0]["credential"]
    assert params == {"subject": "rShop", "issuer": "rIssuer", "credential_type": b"Local_Merchant_KYC".hex().upper()}


def test_offline_allowlist_leaves_out_the_souvenir_shop():
    creds = OfflineCredentials()
    result = creds.verified([BIKE.merchant_address, SOUVENIR.merchant_address], NOW)
    assert result == {BIKE.merchant_address: True, SOUVENIR.merchant_address: False}


# --- New York activity checkout --------------------------------------------


def test_server_boots_the_activity_policy():
    policy = server.cosigner.get_policy()
    assert policy.max_per_item == Decimal("50.00")
    assert policy.max_daily_budget == Decimal("100.00")
    assert policy.allowed_categories == [Category.ACTIVITY, Category.FOOD]
    assert policy.require_verified_credential is True
    assert policy.geofence is not None
    assert policy.geofence.center.lat == 40.758
    assert policy.date_window_start is not None and policy.date_window_end is not None


def test_new_york_activity_checkout_is_approved(nyc):
    response = nyc.cosign(request([PARK, WORKSHOP]))
    assert response.decision.approved
    assert response.decision.violations == []
    assert response.decision.total == Decimal("45.00")
    assert response.signer_blob == FAKE_SIGNER


def test_times_square_souvenir_fails_amount_and_credential(nyc):
    response = nyc.cosign(request([TRAP]))
    assert response.signer_blob is None
    by_rule = {v.rule.value: v for v in response.decision.violations}
    assert by_rule["max_per_item"].expected == "<= 50.00"
    assert by_rule["max_per_item"].actual == "500.00"
    assert by_rule["max_daily_budget"].actual == "500.00"
    assert by_rule["verified_credential"].actual == "none"
    assert by_rule["category"].detail == "Category not allowed"
    assert by_rule["category"].actual == "shopping"
    assert "geofence" not in by_rule
    assert "date_window" not in by_rule


@pytest.mark.parametrize("category, actual", [
    (Category.TRANSPORT, "flight"),
    (Category.LODGING, "hotel"),
])
def test_activity_policy_names_flights_and_hotels(nyc, category, actual):
    quote = signed(PARK, category=category, amount=Decimal("15.00"))
    decision = nyc.evaluate(request([quote]))
    assert rules_of(decision) == ["category"]
    violation = decision.violations[0]
    assert violation.detail == "Activity policy excludes flights and hotels"
    assert violation.actual == actual
    assert violation.expected == "activity,food"
    assert nyc.cosign(request([quote])).signer_blob is None


def test_excluded_flight_still_hits_the_amount_cap(nyc):
    quote = signed(PARK, category=Category.TRANSPORT, amount=Decimal("500.00"))
    decision = nyc.evaluate(request([quote]))
    rules = rules_of(decision)
    assert "max_per_item" in rules
    assert "max_daily_budget" in rules
    assert "category" in rules
    named = next(v for v in decision.violations if v.actual == "flight")
    assert named.detail == "Activity policy excludes flights and hotels"


def test_default_policy_allows_a_flight(guard):
    quote = signed(PARK, category=Category.TRANSPORT, amount=Decimal("15.00"))
    assert guard.evaluate(request([quote])).approved


def test_tampered_new_york_quote_is_not_signed(nyc):
    cheaper = PARK.model_copy(update={"amount": Decimal("1.00")})
    response = nyc.cosign(request([cheaper]))
    assert "quote_signature" in rules_of(response.decision)
    assert response.signer_blob is None


def test_expired_new_york_quote_is_not_signed():
    late = FakeGuardrail(keys=lambda ids: KEYS, clock=lambda: PARK.expires_at + timedelta(minutes=3))
    late.set_policy(activity_policy())
    response = late.cosign(request([PARK]))
    assert rules_of(response.decision) == ["quote_expired"]
    assert response.decision.violations[0].detail == "Quote expired 3 min ago"
    assert response.signer_blob is None


@pytest.mark.parametrize("overrides, needle", [
    ({"Destination": "rAttackerAddress"}, "rAttackerAddress"),
    ({"Amount": "1000000"}, "locks 1 but quote says 15.00"),
    ({"Amount": {"currency": "USD", "issuer": "rI", "value": "15.00"}}, "in USD but quote says RLUSD"),
    ({"Memos": []}, "exactly one quoted invoice memo"),
])
def test_new_york_quote_must_match_the_transaction(nyc, overrides, needle):
    tx = tx_for([PARK], [escrow(PARK, 11, **overrides)])
    response = nyc.cosign(request([PARK], tx))
    assert response.signer_blob is None
    assert "tx_quote_mismatch" in rules_of(response.decision)
    assert any(needle in v.detail for v in response.decision.violations)


def test_unmatched_payment_is_rejected(nyc):
    extra = {"TransactionType": "Payment", "Account": TRIP, "Destination": "rX", "Amount": "5"}
    tx = tx_for([PARK], [escrow(PARK, 11), extra])
    response = nyc.cosign(request([PARK], tx))
    assert response.signer_blob is None
    assert any("only EscrowCreate" in v.detail for v in response.decision.violations)


def test_recorded_spend_blocks_the_activity_checkout(nyc):
    nyc.record_spend(Decimal("60.00"))
    response = nyc.cosign(request([PARK, WORKSHOP], spent="0"))
    assert response.signer_blob is None
    assert rules_of(response.decision) == ["max_daily_budget"]
    assert response.decision.violations[0].expected == "<= 40.00"
    assert response.decision.violations[0].actual == "45.00"


def test_client_total_does_not_shrink_the_activity_budget(nyc):
    response = nyc.cosign(request([PARK, WORKSHOP], spent="90"))
    assert response.decision.approved
    assert response.decision.total == Decimal("45.00")
    assert response.decision.remaining_daily_budget == Decimal("55.00")
    assert response.signer_blob == FAKE_SIGNER


def test_new_york_geofence_rejects_the_airport(nyc):
    city = json.loads((FIXTURES / "demo_city.json").read_text())
    airport = city["destination_airport"]
    away = signed(PARK, location=GeoPoint(lat=airport["lat"], lng=airport["lng"]))
    assert rules_of(nyc.evaluate(request([away]))) == ["geofence"]


def test_activity_checkout_outside_the_trip_dates(nyc):
    start = datetime(2026, 11, 20, 14, 0, tzinfo=PARK.slot_start.tzinfo)
    late = signed(PARK, slot_start=start, slot_end=start + timedelta(hours=2))
    assert rules_of(nyc.evaluate(request([late]))) == ["date_window"]


def test_http_activity_policy_round_trip(monkeypatch, guard):
    monkeypatch.setattr(server, "cosigner", guard)
    client = TestClient(server.http)
    put = client.put("/policy", json=activity_policy().model_dump(mode="json"))
    assert put.status_code == 200
    assert put.json()["max_per_item"] == "50.00"
    assert put.json()["max_daily_budget"] == "100.00"
    assert client.get("/policy").json()["max_per_item"] == "50.00"
    checkout = client.post("/cosign", json=request([PARK, WORKSHOP]).model_dump(mode="json")).json()
    assert checkout["decision"]["approved"] is True
    assert checkout["decision"]["total"] == "45.00"
    assert checkout["signer_blob"] is not None
    trap = client.post("/cosign", json=request([TRAP]).model_dump(mode="json")).json()
    assert trap["signer_blob"] is None
    rules = [row["rule"] for row in trap["decision"]["violations"]]
    assert "max_per_item" in rules and "verified_credential" in rules


def test_concurrent_budget_decisions_serialize():
    entered = []
    release = threading.Event()

    def sign(tx):
        entered.append(threading.get_ident())
        release.wait(timeout=3)
        return dict(FAKE_SIGNER)

    guard = Cosigner(OfflineCredentials(), sign=sign, keys=lambda ids: KEYS, clock=lambda: NOW)
    guard.set_policy(activity_policy().model_copy(update={"max_daily_budget": Decimal("60.00")}))
    quote = signed(PARK, amount=Decimal("50.00"))
    req = request([quote])
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        results.append(guard.cosign(req))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 2
    while len(entered) < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    settle = time.monotonic() + 0.5
    while time.monotonic() < settle and len(entered) < 2:
        time.sleep(0.01)
    observed = len(entered)
    release.set()
    for thread in threads:
        thread.join(timeout=3)
    assert observed == 1
    assert [row.decision.approved for row in results].count(True) == 1
    assert sum(row.signer_blob is None for row in results) == 1
    assert not guard.evaluate(request([signed(PARK, amount=Decimal("50.00"))])).approved
    assert guard.evaluate(request([signed(PARK, amount=Decimal("10.00"))])).approved
