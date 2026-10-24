import httpx

from roam_tools.flights import flight_call_count, lookup_flight, reset_flight_lookup

SAMPLE = [{
    "number": "JL3020",
    "status": "Expected",
    "airline": {"name": "Japan Airlines", "iata": "JL"},
    "departure": {
        "airport": {"iata": "HND", "name": "Tokyo Haneda", "location": {"lat": 35.5494, "lon": 139.7798}},
        "scheduledTime": {"local": "2026-11-14T09:20:00+09:00", "utc": "2026-11-14T00:20:00Z"},
        "terminal": "3",
    },
    "arrival": {
        "airport": {"iata": "KIX", "name": "Kansai International", "location": {"lat": 34.4347, "lon": 135.244}},
        "scheduledTime": {"local": "2026-11-14T10:35:00+09:00", "utc": "2026-11-14T01:35:00Z"},
        "terminal": "1",
    },
}]


class _Response:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_fixture_provider_returns_kansai(monkeypatch):
    monkeypatch.setenv("FLIGHT_API_PROVIDER", "fixture")
    monkeypatch.delenv("FLIGHT_API_KEY", raising=False)
    reset_flight_lookup()
    segment = lookup_flight("JL3020", "2026-11-14")
    assert segment.to_place.code == "KIX"
    assert segment.arrive_at.hour == 10
    assert segment.arrive_at.minute == 35
    assert flight_call_count() == 0


def test_paid_lookup_parses_airports_and_caches(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        assert "JL3020/2026-11-14" in url
        assert headers["X-RapidAPI-Host"] == "aerodatabox.p.rapidapi.com"
        return _Response(SAMPLE)

    monkeypatch.setenv("FLIGHT_API_PROVIDER", "aerodatabox")
    monkeypatch.setenv("FLIGHT_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "get", fake_get)
    reset_flight_lookup()
    first = lookup_flight("JL3020", "2026-11-14")
    second = lookup_flight("jl 3020", "2026-11-14")
    assert first.to_place.code == "KIX"
    assert first.from_place.location.lat == 35.5494
    assert first.arrive_at.hour == 10
    assert first.terminal == "1"
    assert first.source == "aerodatabox"
    assert second.number == first.number
    assert calls["n"] == 1
    assert flight_call_count() == 1


def test_missing_key_is_unverified_and_makes_no_call(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("paid lookup should not run")

    monkeypatch.setenv("FLIGHT_API_PROVIDER", "aerodatabox")
    monkeypatch.delenv("FLIGHT_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "get", boom)
    reset_flight_lookup()
    segment = lookup_flight("JL3020", "2026-11-14")
    assert segment.status.value == "unverified"


def test_provider_error_is_unverified(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setenv("FLIGHT_API_PROVIDER", "aerodatabox")
    monkeypatch.setenv("FLIGHT_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "get", fake_get)
    reset_flight_lookup()
    segment = lookup_flight("JL3020", "2026-11-14")
    assert segment.status.value == "unverified"
    assert flight_call_count() == 1


def test_call_cap_skips_the_network(monkeypatch):
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return _Response(SAMPLE)

    monkeypatch.setenv("FLIGHT_API_PROVIDER", "aerodatabox")
    monkeypatch.setenv("FLIGHT_API_KEY", "test-key")
    monkeypatch.setenv("FLIGHT_API_MAX_CALLS", "1")
    monkeypatch.setattr(httpx, "get", fake_get)
    reset_flight_lookup()
    lookup_flight("JL3020", "2026-11-14")
    blocked = lookup_flight("JL3025", "2026-11-16")
    assert calls["n"] == 1
    assert blocked.status.value == "unverified"
