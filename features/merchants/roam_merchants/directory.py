from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from nacl.signing import SigningKey

from roam_contracts.geo import haversine_km
from roam_contracts.models import CatalogItem, Category, GeoPoint, MerchantProfile, Quote
from roam_contracts.signing import quote_signing_bytes

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
SHARED_MCP_URL = "http://127.0.0.1:8001/mcp"


class ShopFlags(NamedTuple):
    indoor: bool
    refundable: bool


CATALOG_FLAGS = {
    "bamboo-bikes": ShopFlags(indoor=False, refundable=True),
    "kissa-matcha": ShopFlags(indoor=True, refundable=True),
    "ramen-tasting": ShopFlags(indoor=True, refundable=True),
    "lucky-souvenir": ShopFlags(indoor=True, refundable=True),
    "gion-tea": ShopFlags(indoor=True, refundable=True),
    "fushimi-sake": ShopFlags(indoor=True, refundable=True),
    "nishiki-walk": ShopFlags(indoor=True, refundable=True),
    "arashiyama-boat": ShopFlags(indoor=False, refundable=True),
}


def merchant_mcp_url() -> str:
    return os.environ.get("ROAM_MERCHANTS_MCP_URL", SHARED_MCP_URL)


def signing_key(merchant_id: str) -> SigningKey:
    seed = os.environ.get("MERCHANT_SIGNING_SEED", "swanavi-demo")
    return SigningKey(hashlib.sha256(f"{seed}|{merchant_id}".encode()).digest())


def _read_demo_city() -> dict | None:
    path = FIXTURES / "demo_city.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _catalog_flags(city: dict | None) -> dict[str, ShopFlags]:
    flags = dict(CATALOG_FLAGS)
    if city is None:
        return flags
    for row in city["merchants"]:
        flags[row["id"]] = ShopFlags(indoor=row["indoor"], refundable=row["refundable"])
    return flags


def _load() -> tuple[list[MerchantProfile], list[Quote]]:
    merchants = [MerchantProfile.model_validate(row) for row in json.loads((FIXTURES / "merchants.json").read_text())]
    quotes = [Quote.model_validate(row) for row in json.loads((FIXTURES / "quotes.json").read_text())]
    mcp_url = merchant_mcp_url()
    for merchant in merchants:
        merchant.pubkey_ed25519 = signing_key(merchant.merchant_id).verify_key.encode().hex()
        merchant.mcp_url = mcp_url
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
    signature = signing_key(quote.merchant_id).sign(quote_signing_bytes(body)).signature.hex()
    return body.model_copy(update={"merchant_signature": signature, "merchant_verified": quote.merchant_verified})


class Directory:
    def __init__(self) -> None:
        self.merchants, self.quotes = _load()
        city = _read_demo_city()
        self._demo_ids = {row["id"] for row in city["merchants"]} if city else set()
        self._window = (
            timedelta(hours=city["quote_valid_hours"]),
            timedelta(hours=city["escrow_cancel_after_hours"]),
        ) if city else None
        self._flags = _catalog_flags(city)
        self.issued: dict[tuple[str, str, datetime], Quote] = {}

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
            indoor, refundable = self._flags[merchant_id]
            items.append(CatalogItem(
                sku=quote.sku, merchant_id=quote.merchant_id, title=quote.title, description=quote.title,
                category=quote.category, price=quote.amount, currency=quote.currency,
                viator_price=quote.viator_price, slot_start=quote.slot_start, slot_end=quote.slot_end,
                indoor=indoor, refundable=refundable, available=True,
            ))
        return items

    def get_quote(self, merchant_id: str, sku: str, slot_start: datetime) -> Quote:
        key = (merchant_id, sku, slot_start)
        now = datetime.now(timezone.utc)
        cached = self.issued.get(key)
        if cached is not None and now <= cached.expires_at:
            return cached
        for quote in self.quotes:
            if quote.merchant_id == merchant_id and quote.sku == sku and quote.slot_start == slot_start:
                signed = sign_quote(self._stamp(quote, now))
                self.issued[key] = signed
                return signed
        raise KeyError(f"no quote for {merchant_id} {sku}")

    def _stamp(self, quote: Quote, now: datetime) -> Quote:
        if self._window is None or quote.merchant_id not in self._demo_ids:
            return quote
        valid, cancel = self._window
        return quote.model_copy(update={"expires_at": now + valid, "cancel_after": now + cancel})


class FakeMerchantDirectory(Directory):
    pass
