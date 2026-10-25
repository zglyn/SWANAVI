from __future__ import annotations

from fastmcp import FastMCP

from roam_tools.attractions import search_attractions
from roam_tools.flight_search import search_flights
from roam_tools.flights import lookup_flight
from roam_tools.hotel_search import search_hotels
from roam_tools.routing import get_travel_matrix, optimize_route
from roam_tools.transport import get_transport_profile
from roam_tools.weather import get_weather

mcp = FastMCP("roam-tools")


@mcp.tool(description="How people usually get around a city, including airport and station transfers. Place is a city name such as 'Kyoto, Japan'. Minutes and costs are typical, not a live timetable.")
def transport_profile(place: str) -> dict:
    return get_transport_profile(place).model_dump(mode="json")


@mcp.tool(description="Travel minutes and kilometres between every pair of points, for each mode. Modes are walk, bike, transit, taxi, car. Distance is kilometres.")
def travel_matrix(points: list[dict], modes: list[str]) -> dict:
    return get_travel_matrix(points, modes)


@mcp.tool(description="Order stops inside a time window. start and end are {lat, lng} for the day's lodging or hub. Required stops are never dropped. Times are ISO datetimes.")
def route(stops: list[dict], start: dict, mode: str, window_start: str, window_end: str, end: dict | None = None) -> dict:
    from datetime import datetime

    return optimize_route(
        stops, start, mode,
        datetime.fromisoformat(window_start),
        datetime.fromisoformat(window_end),
        end,
    )


@mcp.tool(description="Sights near a place. interests use words such as temples, nature, museums, food. near is {lat, lng}. radius_km limits the circle. Every result has a description and, for the curated list, an image URL.")
def attractions(place: str, interests: list[str] | None = None, near: dict | None = None, radius_km: float | None = None, limit: int = 20) -> list[dict]:
    return [item.model_dump(mode="json") for item in search_attractions(place, interests, near, radius_km, limit)]


@mcp.tool(description="Hourly rain and temperature for one date (YYYY-MM-DD). place_or_point is a city name or {lat, lng}.")
def weather(place_or_point: dict | str, date: str) -> dict:
    return get_weather(place_or_point, date)


@mcp.tool(description="Look up a flight number on a date. AeroDataBox when FLIGHT_API_PROVIDER=aerodatabox and FLIGHT_API_KEY is set. The fixture table otherwise. Unverified when the schedule cannot be confirmed.")
def flight(number: str, date: str) -> dict:
    return lookup_flight(number, date).model_dump(mode="json")


@mcp.tool(description="Search flights between airport codes for a depart date and an optional return date. Windows are red_eye, early_morning, morning, afternoon, evening, or any. Fixture data unless FLIGHT_SEARCH_PROVIDER=duffel.")
def flight_search(origin_codes: list[str], destination_codes: list[str], depart_date: str, return_date: str | None = None, outbound_window: str = "any", return_window: str = "any", cabin: str = "economy", max_stops: int = 1, travellers: int = 1, favourite_airlines: list[str] | None = None, avoid_red_eye: bool = False) -> list[dict]:
    offers = search_flights(origin_codes, destination_codes, depart_date, return_date, outbound_window, return_window, cabin, max_stops, travellers, favourite_airlines, avoid_red_eye)
    return [item.model_dump(mode="json") for item in offers]


@mcp.tool(description="Rank hotels by travel time to attraction points. Each point is {id, lat, lng, day?, weight?}. Fixture catalog unless HOTEL_SEARCH_PROVIDER=amadeus.")
def hotel_search(attraction_points: list[dict], check_in: str, check_out: str, budget_level: str = "mid", brands: list[str] | None = None, min_stars: float | None = None, must_have: list[str] | None = None, travellers: int = 1, modes: list[str] | None = None) -> list[dict]:
    offers = search_hotels(attraction_points, check_in, check_out, budget_level, brands, min_stars, must_have, travellers, modes)
    return [item.model_dump(mode="json") for item in offers]


def main() -> None:
    mcp.run(transport="http", host="0.0.0.0", port=8003)


if __name__ == "__main__":
    main()
