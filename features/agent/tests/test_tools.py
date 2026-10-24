import asyncio
import os
from datetime import datetime, timedelta, timezone

from fastmcp import Client

from roam_tools.routing import get_travel_matrix, optimize_route
from roam_tools.server import mcp
from roam_tools.transport import get_transport_profile

JST = timezone(timedelta(hours=9))
KYOTO = [
    {"id": "a", "lat": 35.017, "lng": 135.672},
    {"id": "b", "lat": 35.039, "lng": 135.729},
    {"id": "c", "lat": 34.967, "lng": 135.773},
    {"id": "d", "lat": 34.995, "lng": 135.785},
    {"id": "e", "lat": 35.025, "lng": 135.762},
    {"id": "f", "lat": 35.004, "lng": 135.776},
]


def test_kyoto_profile_includes_haruka_and_is_fast():
    import time

    started = time.perf_counter()
    profile = get_transport_profile("Kyoto, Japan")
    assert time.perf_counter() - started < 0.01
    assert profile.source == "curated"
    haruka = profile.transfers[0].options[0]
    assert haruka.name.startswith("Haruka")
    assert haruka.minutes == 75


def test_unknown_place_is_an_unverified_llm_profile(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    profile = get_transport_profile("Reykjavik, Iceland")
    assert profile.source == "llm"
    assert "not checked" in profile.tips[0]


def test_matrix_diagonal_is_zero():
    grid = get_travel_matrix(KYOTO, ["walk"])
    for point in KYOTO:
        cell = grid["walk"][point["id"]][point["id"]]
        assert cell["minutes"] == 0
        assert cell["distance_km"] == 0


def test_optimizer_beats_a_shuffled_order():
    window_start = datetime(2026, 11, 14, 9, tzinfo=JST)
    window_end = datetime(2026, 11, 14, 21, tzinfo=JST)
    stops = [{"id": p["id"], "lat": p["lat"], "lng": p["lng"], "duration_min": 30} for p in KYOTO]
    shuffled = ["c", "b", "f", "a", "d", "e"]
    points = [{"id": "__start__", "lat": 34.9858, "lng": 135.7588}, *KYOTO]
    matrix = get_travel_matrix(points, ["walk"])

    def cost(order):
        total = 0
        prev = "__start__"
        for stop_id in order:
            total += matrix["walk"][prev][stop_id]["minutes"]
            prev = stop_id
        return total

    result = optimize_route(stops, {"lat": 34.9858, "lng": 135.7588}, "walk", window_start, window_end)
    assert cost(result["order"]) < cost(shuffled)


def test_fixed_start_and_window_and_required():
    window_start = datetime(2026, 11, 14, 9, tzinfo=JST)
    window_end = datetime(2026, 11, 14, 12, tzinfo=JST)
    stops = [
        {"id": "early", "lat": 35.01, "lng": 135.76, "duration_min": 30, "fixed_start": datetime(2026, 11, 14, 14, tzinfo=JST), "required": True},
        {"id": "late", "lat": 35.02, "lng": 135.77, "duration_min": 180, "required": True},
        {"id": "optional", "lat": 35.03, "lng": 135.78, "duration_min": 180, "required": False},
    ]
    result = optimize_route(stops, {"lat": 35.0, "lng": 135.75}, "walk", window_start, window_end)
    assert "early" not in result["unscheduled"]
    assert "late" not in result["unscheduled"]
    assert result["starts"]["early"].startswith("2026-11-14T14:00:00")
    assert result["warnings"]
    assert all(datetime.fromisoformat(value) >= window_start for value in result["starts"].values())


def test_ors_failure_falls_back(monkeypatch):
    monkeypatch.setenv("ROAM_ROUTING", "ors")
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    from roam_tools import routing

    routing._CACHE.clear()
    grid = get_travel_matrix(KYOTO[:2], ["walk"])
    assert grid["walk"]["a"]["b"]["source"] == "estimate"


def test_tools_are_on_the_mcp_server():
    async def inner():
        async with Client(mcp) as client:
            result = await client.call_tool("transport_profile", {"place": "Kyoto, Japan"})
            text = str(result)
            assert "Haruka" in text

    asyncio.run(inner())


def test_attractions_near_arashiyama():
    from roam_tools.attractions import search_attractions

    found = search_attractions("Kyoto", ["temples", "nature"], {"lat": 35.017, "lng": 135.6713}, 2)
    names = {item.name for item in found}
    assert "Arashiyama Bamboo Grove" in names
    assert "Tenryū-ji" in names
    assert all(item.image_url for item in found)
    assert all(item.description for item in found)


def test_weather_offline(monkeypatch):
    from roam_tools import weather

    def boom(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(weather.httpx, "get", boom)
    report = weather.get_weather("Kyoto", "2026-11-14")
    assert report["summary"] == "no forecast"
    assert report["hourly"] == []
