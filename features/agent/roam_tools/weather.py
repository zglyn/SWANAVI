from __future__ import annotations

import httpx

from roam_contracts.models import Destination


def _coordinates(place_or_point) -> tuple[float, float] | None:
    if isinstance(place_or_point, Destination):
        return place_or_point.lat, place_or_point.lng
    if isinstance(place_or_point, dict) and "lat" in place_or_point and "lng" in place_or_point:
        return float(place_or_point["lat"]), float(place_or_point["lng"])
    lat = getattr(place_or_point, "lat", None)
    lng = getattr(place_or_point, "lng", None)
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)) and not isinstance(place_or_point, str):
        return float(lat), float(lng)
    return None


def _timezone_name(place_or_point) -> str:
    if isinstance(place_or_point, Destination):
        return place_or_point.timezone
    if isinstance(place_or_point, dict) and isinstance(place_or_point.get("timezone"), str):
        return place_or_point["timezone"]
    name = getattr(place_or_point, "timezone", None)
    if isinstance(name, str) and name and not isinstance(place_or_point, str):
        return name
    return "auto"


def get_weather(place_or_point, date: str) -> dict:
    point = _coordinates(place_or_point)
    if point is None:
        return {"hourly": [], "summary": "no forecast"}
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": point[0],
                "longitude": point[1],
                "hourly": "precipitation,precipitation_probability,temperature_2m",
                "timezone": _timezone_name(place_or_point),
                "start_date": date,
                "end_date": date,
            },
            timeout=8,
        )
        response.raise_for_status()
        hourly = response.json()["hourly"]
        rows = []
        for time, precip, prob, temp in zip(
            hourly["time"], hourly["precipitation"], hourly["precipitation_probability"], hourly["temperature_2m"]
        ):
            rows.append({"time": time, "precip_mm": precip, "precip_prob": prob, "temp_c": temp})
        wet = [row for row in rows if (row["precip_prob"] or 0) >= 50]
        summary = "Rain likely" if len(wet) >= 3 else "Mostly dry"
        return {"hourly": rows, "summary": summary}
    except Exception:
        return {"hourly": [], "summary": "no forecast"}
