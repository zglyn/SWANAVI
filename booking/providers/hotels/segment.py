"""Parse a hotel segment into a stay. Invalid input is a list of problems."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class HotelStay:
    segment_id: str
    city: str
    check_in: date
    check_out: date
    rooms: int
    guests: int
    city_code: str | None = None
    hotel_ids: tuple[str, ...] = ()
    city_code_rejected: bool = False
    hotel_id_rejected: bool = False

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


def read_segment_id(segment: object) -> str | None:
    if not isinstance(segment, dict):
        return None
    segment_id = segment.get("segmentId")
    if isinstance(segment_id, str) and segment_id.strip():
        return segment_id.strip()
    return None


def parse_hotel_request(
    segment: object, travelers: object, trip_id: object
) -> tuple[HotelStay | None, list[str]]:
    """Return a stay, or ``None`` plus the reasons the caller must fix."""
    problems: list[str] = []
    if not isinstance(trip_id, str) or not trip_id.strip():
        problems.append("trip_id is required")
    if not isinstance(segment, dict):
        problems.append("segment must be an object")
        return None, problems

    segment_id = segment.get("segmentId")
    if isinstance(segment_id, str) and segment_id.strip():
        clean_id = segment_id.strip()
    else:
        problems.append("segmentId is required")
        clean_id = ""

    if segment.get("kind") != "hotel":
        problems.append('kind must be "hotel"')

    city_raw = segment.get("city")
    if isinstance(city_raw, str) and city_raw.strip():
        city = " ".join(city_raw.strip().lower().split())
    else:
        problems.append("city is required")
        city = ""

    check_in = _parse_date(segment.get("checkIn"))
    check_out = _parse_date(segment.get("checkOut"))
    if check_in is None:
        problems.append("checkIn must be an ISO date (YYYY-MM-DD)")
    if check_out is None:
        problems.append("checkOut must be an ISO date (YYYY-MM-DD)")
    if check_in is not None and check_out is not None and check_out <= check_in:
        problems.append("checkOut must be after checkIn")

    rooms = _positive_int(segment.get("rooms"))
    guests = _positive_int(segment.get("guests"))
    if rooms is None:
        problems.append("rooms must be a positive integer")
    if guests is None:
        problems.append("guests must be a positive integer")

    if not isinstance(travelers, list):
        problems.append("travelers must be a list")
    else:
        for index, traveler in enumerate(travelers):
            if traveler_name(traveler) is None:
                problems.append(f"travelers[{index}] must be a name or an object with a name")

    if problems or check_in is None or check_out is None or rooms is None or guests is None:
        return None, problems

    city_code, city_code_rejected = _city_code(segment)
    hotel_ids, hotel_id_rejected = _hotel_ids(segment)
    return (
        HotelStay(
            segment_id=clean_id,
            city=city,
            check_in=check_in,
            check_out=check_out,
            rooms=rooms,
            guests=guests,
            city_code=city_code,
            hotel_ids=hotel_ids,
            city_code_rejected=city_code_rejected,
            hotel_id_rejected=hotel_id_rejected,
        ),
        [],
    )


def traveler_names(travelers: list) -> list[str]:
    names: list[str] = []
    for traveler in travelers:
        name = traveler_name(traveler)
        if name is not None:
            names.append(name)
    return names


def traveler_name(traveler: object) -> str | None:
    if isinstance(traveler, str):
        raw = traveler
    elif isinstance(traveler, dict):
        value = traveler.get("name", traveler.get("fullName"))
        if not isinstance(value, str):
            return None
        raw = value
    else:
        return None
    name = " ".join(raw.strip().lower().split())
    return name or None


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip().split("T", 1)[0].split(" ", 1)[0]
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def _city_code(segment: dict) -> tuple[str | None, bool]:
    if "cityCode" not in segment:
        return None, False
    raw = segment.get("cityCode")
    if isinstance(raw, str) and len(raw.strip()) == 3 and raw.strip().isalpha():
        return raw.strip().upper(), False
    return None, True


def _hotel_ids(segment: dict) -> tuple[tuple[str, ...], bool]:
    if "hotelId" not in segment and "hotelIds" not in segment:
        return (), False
    raw = segment.get("hotelIds", segment.get("hotelId"))
    parts: list[object]
    if isinstance(raw, str):
        parts = raw.split(",")
    elif isinstance(raw, list):
        parts = list(raw)
    else:
        return (), True
    ids: list[str] = []
    for part in parts:
        if not isinstance(part, str):
            continue
        text = part.strip()
        if text and text.isalnum() and len(text) <= 12:
            ids.append(text)
    if not ids:
        return (), True
    return tuple(ids), False


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        if number >= 1:
            return number
    return None
