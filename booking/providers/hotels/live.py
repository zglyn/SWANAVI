"""Optional live hotel adapter.

Not used unless ``HOTEL_BOOKING_PROVIDER=live``. Even then it refuses
production hosts, refuses redirects, and never puts a card on the request.
"""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.error import HTTPError, URLError

from .errors import HotelProviderError
from .safety import assert_safe_hotel_url, contains_payment_instrument
from .segment import HotelStay, traveler_names


class LiveHotelProvider:
    """POST a stay to a sandbox hotel endpoint. Never the default provider."""

    name = "live"

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = assert_safe_hotel_url(base_url).rstrip("/")
        self.api_key = api_key or None

    @classmethod
    def from_env(cls) -> LiveHotelProvider:
        base = os.environ.get("HOTEL_BOOKING_API_BASE", "").strip()
        if not base:
            raise HotelProviderError(
                "HOTEL_BOOKING_API_BASE is required when HOTEL_BOOKING_PROVIDER=live"
            )
        key = os.environ.get("HOTEL_BOOKING_API_KEY", "").strip() or None
        return cls(base, key)

    def book(
        self,
        stay: HotelStay,
        travelers: list,
        trip_id: str,
        fault: object = None,
    ) -> dict:
        # A sandbox fault must not be forwarded, and must not open a socket.
        if _fault_set(fault):
            raise HotelProviderError("sandboxFault is not sent to the live hotel provider")
        payload = {
            "segment": {
                "segmentId": stay.segment_id,
                "kind": "hotel",
                "city": stay.city,
                "checkIn": stay.check_in.isoformat(),
                "checkOut": stay.check_out.isoformat(),
                "rooms": stay.rooms,
                "guests": stay.guests,
            },
            "travelers": [{"name": name} for name in traveler_names(travelers)],
            "tripId": trip_id.strip(),
        }
        if contains_payment_instrument(payload):
            raise HotelProviderError("refusing to send card or payment details")
        url = assert_safe_hotel_url(f"{self.base_url}/bookings")
        return post_json(url, payload, self.api_key)


def post_json(url: str, payload: dict, api_key: str | None, timeout: float = 10.0) -> dict:
    """POST JSON and return an object. Redirects are refused."""
    safe_url = assert_safe_hotel_url(url)
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(safe_url, data=body, headers=headers, method="POST")
    opener = urllib.request.build_opener(_RefuseRedirects)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
    except HotelProviderError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HotelProviderError(f"live hotel request failed: {exc}") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HotelProviderError("live hotel response was not JSON") from exc
    if not isinstance(parsed, dict):
        raise HotelProviderError("live hotel response was not an object")
    return parsed


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HotelProviderError("refusing hotel API redirect")


def _fault_set(fault: object) -> bool:
    if fault is None or fault is False:
        return False
    if isinstance(fault, str) and not fault.strip():
        return False
    return True
