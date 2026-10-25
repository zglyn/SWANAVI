from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from fastmcp import FastMCP

from roam_contracts.models import Category, GeoPoint
from roam_merchants.directory import Directory

directory = Directory()
mcp = FastMCP("merchant-directory")
http = FastAPI(title="Swanavi merchants")


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


@http.get("/registry")
def registry(city: str):
    return [merchant.model_dump(mode="json") for merchant in directory.find_merchants(city)]


def main() -> None:
    import uvicorn

    http.mount("/mcp", mcp.http_app())
    uvicorn.run(http, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
