"""Where the guardrail gets facts the request can't be trusted for: merchant signing keys, on-ledger credentials,
and its own Key 2. All XRPL access here is read-only; signing happens locally."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
from xrpl.models.transactions import Transaction
from xrpl.transaction import sign
from xrpl.wallet import Wallet

from roam_contracts.geo import haversine_km
from roam_contracts.models import CREDENTIAL_TYPE, Category, Geofence, GeoPoint, MerchantProfile, PolicyConfig

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
DEVNET_RPC = "https://s.devnet.rippletest.net:51234"
LSF_ACCEPTED = 0x00010000
RIPPLE_EPOCH = 946684800
# Matches features/ledger bootstrap: every fixture shop gets the credential except the scam souvenir shop.
UNVERIFIED_BY_DEFAULT = {"lucky-souvenir"}


def load_env_file(path: Path) -> None:
    """Reads KEY=value lines (e.g. .env.guardrail) into os.environ without overriding what's already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def merchant_address(merchant: MerchantProfile) -> str:
    return os.environ.get(f"MERCHANT_{merchant.merchant_id.upper().replace('-', '_')}_ADDRESS", merchant.xrpl_address)


def fixture_merchants() -> list[MerchantProfile]:
    return [MerchantProfile.model_validate(row) for row in json.loads((FIXTURES / "merchants.json").read_text())]


class Credentials(Protocol):
    def verified(self, addresses: list[str], now: datetime) -> dict[str, bool]: ...


class OfflineCredentials:
    """No XRPL node: a static allowlist of shop addresses (GUARDRAIL_OFFLINE=1, and the fake)."""

    def __init__(self, addresses: set[str] | None = None) -> None:
        if addresses is None:
            listed = os.environ.get("GUARDRAIL_VERIFIED_MERCHANTS")
            ids = set(listed.split(",")) if listed else None
            blocked = unverified_merchant_ids()
            addresses = {
                merchant_address(m) for m in fixture_merchants()
                if (m.merchant_id in ids if ids is not None else m.merchant_id not in blocked)
            }
        self.addresses = addresses

    def verified(self, addresses: list[str], now: datetime) -> dict[str, bool]:
        return {address: address in self.addresses for address in addresses}


class XrplCredentials:
    """Looks up the Credential ledger entry our issuer gave each shop, and checks it was accepted and hasn't expired."""

    def __init__(self, issuer: str, rpc_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.issuer = issuer
        self.rpc_url = rpc_url or os.environ.get("XRPL_RPC_URL", DEVNET_RPC)
        self.client = client or httpx.Client(timeout=10)

    def verified(self, addresses: list[str], now: datetime) -> dict[str, bool]:
        return {address: self._has_credential(address, now) for address in set(addresses)}

    def _has_credential(self, subject: str, now: datetime) -> bool:
        params = {"credential": {"subject": subject, "issuer": self.issuer, "credential_type": CREDENTIAL_TYPE.encode().hex().upper()},
                  "ledger_index": "validated"}
        try:
            response = self.client.post(self.rpc_url, json={"method": "ledger_entry", "params": [params]})
            response.raise_for_status()
        except httpx.HTTPError:
            return False  # can't prove it, so it doesn't count
        node = response.json().get("result", {}).get("node")
        if not node or not int(node.get("Flags", 0)) & LSF_ACCEPTED:
            return False
        expiration = node.get("Expiration")
        return expiration is None or RIPPLE_EPOCH + int(expiration) > now.timestamp()


class MerchantKeys:
    """Shop signing keys from the merchant server's registry, fetched once and refreshed when a new shop shows up."""

    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.base_url = (base_url or os.environ.get("MERCHANTS_URL", "http://localhost:8001")).rstrip("/")
        self.client = client or httpx.Client(timeout=5)
        self.keys: dict[str, str] = {}

    def for_merchants(self, merchant_ids: list[str]) -> dict[str, str]:
        if any(m not in self.keys for m in merchant_ids):
            try:
                response = self.client.get(f"{self.base_url}/merchants")
                response.raise_for_status()
                self.keys = {row["merchant_id"]: row["pubkey_ed25519"] for row in response.json()}
            except (httpx.HTTPError, KeyError, ValueError):
                pass  # an unknown key fails the quote_signature rule, which is the safe outcome
        return self.keys


def load_wallet() -> tuple[Wallet, bool]:
    """Key 2. Returns (wallet, from_seed); without GUARDRAIL_SEED a throwaway wallet keeps local testing working."""
    seed = os.environ.get("GUARDRAIL_SEED")
    if seed:
        return Wallet.from_seed(seed), True
    return Wallet.create(), False


def signer_blob(tx_json: dict[str, Any], wallet: Wallet) -> dict[str, Any]:
    """The guardrail's Signer entry, which the ledger combines with the agent's to reach quorum 2."""
    signed = sign(Transaction.from_xrpl(tx_json), wallet, multisign=True)
    return signed.to_xrpl()["Signers"][0]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def unverified_merchant_ids() -> set[str]:
    ids = set(UNVERIFIED_BY_DEFAULT)
    path = FIXTURES / "demo_city.json"
    if not path.exists():
        return ids
    for row in json.loads(path.read_text())["merchants"]:
        if not row["verified"]:
            ids.add(row["id"])
    return ids


def activity_policy() -> PolicyConfig:
    """New York activity policy. Per-item cap 50.00, daily cap 100.00, categories activity and food.
    Dates and center come from demo_city.json. The geofence radius is the farthest demo merchant plus 1 km."""
    city = json.loads((FIXTURES / "demo_city.json").read_text())
    zone = ZoneInfo(city["timezone"])
    start = datetime.fromisoformat(city["dates"]["start"]).replace(tzinfo=zone)
    end = datetime.fromisoformat(city["dates"]["end"]).replace(tzinfo=zone) + timedelta(days=1)
    center = city["center"]
    farthest = max(
        haversine_km(center["lat"], center["lng"], row["lat"], row["lng"])
        for row in city["merchants"]
    )
    return PolicyConfig(
        max_daily_budget=Decimal("100.00"),
        max_per_item=Decimal("50.00"),
        require_verified_credential=True,
        allowed_categories=[Category.ACTIVITY, Category.FOOD],
        date_window_start=start,
        date_window_end=end,
        geofence=Geofence(
            center=GeoPoint(lat=center["lat"], lng=center["lng"]),
            radius_km=farthest + 1,
        ),
    )
