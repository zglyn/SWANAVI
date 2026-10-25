from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from nacl.signing import SigningKey

from roam_contracts.geo import haversine_km
from roam_contracts.models import CatalogItem, Category, GeoPoint, MerchantProfile, Quote
from roam_contracts.signing import quote_signing_bytes

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
DEMO_SIGNING_KEY = SigningKey(bytes.fromhex("11" * 32))
PUBLIC_KEY = DEMO_SIGNING_KEY.verify_key.encode().hex()


def _load() -> tuple[list[MerchantProfile], list[Quote]]:
    merchants = [MerchantProfile.model_validate(row) for row in json.loads((FIXTURES / "merchants.json").read_text())]
    quotes = [Quote.model_validate(row) for row in json.loads((FIXTURES / "quotes.json").read_text())]
    for merchant in merchants:
        merchant.pubkey_ed25519 = PUBLIC_KEY
        # Real XRPL addresses from the ledger setup replace the fixture placeholders, e.g.
        # MERCHANT_BAMBOO_BIKES_ADDRESS=r... (features/ledger writes these into .env.ledger).
        address = os.environ.get(f"MERCHANT_{merchant.merchant_id.upper().replace('-', '_')}_ADDRESS")
        if address:
            merchant.xrpl_address = address
    addresses = {merchant.merchant_id: merchant.xrpl_address for merchant in merchants}
    quotes = [quote.model_copy(update={"merchant_address": addresses.get(quote.merchant_id, quote.merchant_address)})
              for quote in quotes]
    return merchants, quotes


def sign_quote(quote: Quote) -> Quote:
    body = quote.model_copy(update={"merchant_signature": "00", "merchant_verified": None})
    signature = DEMO_SIGNING_KEY.sign(quote_signing_bytes(body)).signature.hex()
    return body.model_copy(update={"merchant_signature": signature, "merchant_verified": quote.merchant_verified})


class Directory:
    def __init__(self) -> None:
        self.merchants, self.quotes = _load()

    def list_merchants(self) -> list[MerchantProfile]:
        return list(self.merchants)

    def find_merchants(
        self,
        city: str,
        category: Category | None = None,
        near: GeoPoint | None = None,
        radius_km: float | None = None,
        open_at: datetime | None = None,
    ) -> list[MerchantProfile]:
        found = []
        for merchant in self.merchants:
            if (merchant.city or "").lower() != city.lower():
                continue
            if category is not None and merchant.category != category:
                continue
            distance = None
            if near is not None:
                distance = haversine_km(near.lat, near.lng, merchant.location.lat, merchant.location.lng)
                if radius_km is not None and distance > radius_km:
                    continue
            if open_at is not None:
                slots = [quote for quote in self.quotes if quote.merchant_id == merchant.merchant_id]
                if slots and not any(quote.slot_start <= open_at <= quote.slot_end for quote in slots):
                    continue
            found.append((distance if distance is not None else 0, merchant))
        found.sort(key=lambda row: row[0])
        return [merchant for _, merchant in found]

    def search_catalog(self, merchant_id: str, date: datetime | None = None) -> list[CatalogItem]:
        items = []
        for quote in self.quotes:
            if quote.merchant_id != merchant_id:
                continue
            if date is not None and quote.slot_start.date() != date.date():
                continue
            items.append(CatalogItem(
                sku=quote.sku, merchant_id=quote.merchant_id, title=quote.title, description=quote.title,
                category=quote.category, price=quote.amount, currency=quote.currency,
                viator_price=quote.viator_price, slot_start=quote.slot_start, slot_end=quote.slot_end,
                indoor=quote.category != Category.ACTIVITY, refundable=True, available=True,
            ))
        return items

    def get_quote(self, merchant_id: str, sku: str, slot_start: datetime) -> Quote:
        for quote in self.quotes:
            if quote.merchant_id == merchant_id and quote.sku == sku and quote.slot_start == slot_start:
                return sign_quote(quote)
        raise KeyError(f"no quote for {merchant_id} {sku}")


class FakeMerchantDirectory(Directory):
    pass
