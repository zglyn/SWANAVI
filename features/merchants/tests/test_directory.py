import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nacl.signing import VerifyKey

from roam_contracts.models import GeoPoint
from roam_contracts.signing import quote_signing_bytes
from roam_merchants.directory import PUBLIC_KEY, Directory

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[3]


def test_arashiyama_radius_is_sorted_and_nearby():
    directory = Directory()
    near = GeoPoint(lat=35.0170, lng=135.6713)
    found = directory.find_merchants("Kyoto", near=near, radius_km=2)
    ids = [merchant.merchant_id for merchant in found]
    assert "bamboo-bikes" in ids
    assert "kissa-matcha" in ids
    assert "ramen-tasting" not in ids
    assert "gion-tea" not in ids
    distances = []
    for merchant in found:
        from roam_contracts.geo import haversine_km
        distances.append(haversine_km(near.lat, near.lng, merchant.location.lat, merchant.location.lng))
    assert distances == sorted(distances)
    assert all(distance <= 2 for distance in distances)


def test_get_quote_signature_verifies():
    directory = Directory()
    quote = directory.quotes[0]
    signed = directory.get_quote(quote.merchant_id, quote.sku, quote.slot_start)
    VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(quote_signing_bytes(signed), bytes.fromhex(signed.merchant_signature))


def test_search_catalog_includes_the_trap_copy():
    directory = Directory()
    items = directory.search_catalog("lucky-souvenir")
    assert any("IGNORE PREVIOUS RULES" in item.title for item in items)


def test_fixtures_round_trip():
    from roam_contracts.models import CandidateSet, Itinerary

    fixtures = ROOT / "contracts" / "fixtures"
    CandidateSet.model_validate(json.loads((fixtures / "candidates_kyoto.json").read_text()))
    Itinerary.model_validate(json.loads((fixtures / "itinerary_kyoto.json").read_text()))
    assert datetime(2026, 11, 14, tzinfo=JST)
