"""Hourly forecast. Open-Meteo when the network works, a clear empty summary when it does not."""

from __future__ import annotations

import httpx

GEOCODE = {
    "kyoto": (35.0116, 135.7681),
    "osaka": (34.6937, 135.5023),
    "tokyo": (35.6762, 139.6503),
}


def _point(place_or_point) -> tuple[float, float] | None:
    if isinstance(place_or_point, dict) and "lat" in place_or_point:
        return float(place_or_point["lat"]), float(place_or_point["lng"])
    text = str(place_or_point).lower()
    for name, coords in GEOCODE.items():
        if name in text:
            return coords
    return None


def get_weather(place_or_point, date: str) -> dict:
    point = _point(place_or_point)
    if point is None:
        return {"hourly": [], "summary": "no forecast"}
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": point[0],
                "longitude": point[1],
                "hourly": "precipitation,precipitation_probability,temperature_2m",
                "timezone": "Asia/Tokyo",
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
