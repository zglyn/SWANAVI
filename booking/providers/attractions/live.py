"""Amadeus Tours and Activities client for the test host.

Used only when ``ROAM_ATTRACTION_PROVIDER=live``. Unit tests must not call it.
Requests go to ``https://test.api.amadeus.com`` only after ``AMADEUS_HOSTNAME=test``.
Search, then retrieve the activity. The provider ``bookingLink`` is not opened
and no card is sent or charged.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

from .errors import AttractionProviderError
from .result import booking_result

HOSTNAME_ENV = "AMADEUS_HOSTNAME"
CLIENT_ID_ENV = "AMADEUS_CLIENT_ID"
CLIENT_SECRET_ENV = "AMADEUS_CLIENT_SECRET"
_TEST_HOST = "test.api.amadeus.com"
_TEST_ORIGIN = "https://test.api.amadeus.com"
_ACTIVITY_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_PAYMENT_KEYS = {
    "card",
    "cardnumber",
    "ccnumber",
    "cid",
    "creditcard",
    "cvc",
    "cvv",
    "expiry",
    "expmonth",
    "expyear",
    "pan",
    "payment",
    "paymentmethod",
}


class AmadeusToursActivitiesClient:
    """Search and book on the Amadeus test host without charging a card."""

    def book(self, segment: dict, travelers: list, trip_id: str) -> dict:
        del trip_id  # The test booking call has no trip field and must not echo secrets.
        segment_id = segment.get("segmentId") if isinstance(segment, dict) else None
        if _contains_payment(segment) or _contains_payment(travelers):
            return booking_result(
                segment_id,
                "needs_user",
                error="card details were refused; no request was sent and no card was charged",
            )
        _require_test_host()
        credentials = _credentials()
        if credentials is None:
            return booking_result(
                segment_id,
                "needs_user",
                error=(
                    f"{CLIENT_ID_ENV} and {CLIENT_SECRET_ENV} are required; "
                    "no request was sent and no card was charged"
                ),
            )
        client_id, client_secret = credentials
        token = _access_token(client_id, client_secret)
        coordinates = _city_coordinates(token, segment["city"])
        matches = _search_activities(token, coordinates, segment["name"])
        if not matches:
            return booking_result(
                segment_id,
                "needs_user",
                error=(
                    "Amadeus test search returned no matching activity; "
                    "no booking was submitted and no card was charged"
                ),
            )
        confirmed = _retrieve_activity(token, matches[0])
        return _book_on_test_host(segment_id, confirmed)


def _require_test_host() -> None:
    hostname = os.environ.get(HOSTNAME_ENV, "").strip().lower()
    if hostname != "test":
        raise AttractionProviderError(
            f"{HOSTNAME_ENV} must be test; no request was sent and no card was charged"
        )
    if urlparse(_TEST_ORIGIN).hostname != _TEST_HOST:
        raise AttractionProviderError("refused non-test Amadeus origin; no card was charged")


def _credentials() -> tuple[str, str] | None:
    client_id = os.environ.get(CLIENT_ID_ENV, "").strip()
    client_secret = os.environ.get(CLIENT_SECRET_ENV, "").strip()
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def _access_token(client_id: str, client_secret: str) -> str:
    payload = _request(
        "POST",
        "/v1/security/oauth2/token",
        form={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise AttractionProviderError("Amadeus test token was missing; no card was charged")
    return token


def _city_coordinates(token: str, city: str) -> tuple[str, str]:
    payload = _request(
        "GET",
        "/v1/reference-data/locations",
        query={"subType": "CITY", "keyword": city.strip(), "page[limit]": "5"},
        token=token,
    )
    for location in _data_list(payload):
        coordinates = _coordinates(location)
        if coordinates is not None:
            return coordinates
    raise AttractionProviderError(
        "Amadeus test city search returned no coordinates; no card was charged"
    )


def _search_activities(token: str, coordinates: tuple[str, str], name: str) -> list[dict]:
    latitude, longitude = coordinates
    payload = _request(
        "GET",
        "/v1/shopping/activities",
        query={"latitude": latitude, "longitude": longitude, "radius": "20"},
        token=token,
    )
    return [activity for activity in _data_list(payload) if _name_matches(activity, name)]


def _retrieve_activity(token: str, activity: dict) -> dict:
    activity_id = str(activity.get("id", "")).strip()
    if _ACTIVITY_ID.fullmatch(activity_id) is None:
        raise AttractionProviderError("refused invalid activity id; no card was charged")
    payload = _request("GET", f"/v1/shopping/activities/{activity_id}", token=token)
    confirmed = _data_object(payload)
    return confirmed or activity


def _book_on_test_host(segment_id: str | None, activity: dict) -> dict:
    """Finish on the test host. Never open the provider booking link or send a card."""
    link = activity.get("bookingLink")
    if isinstance(link, str) and link.strip():
        host = urlparse(link).hostname
        if host != _TEST_HOST:
            quote = _quote(activity)
            return booking_result(
                segment_id,
                "needs_user",
                error=(
                    f"Amadeus test activity {activity.get('id')} was retrieved.{quote} "
                    "The provider booking link was not opened and no card was charged."
                ),
            )
    quote = _quote(activity)
    return booking_result(
        segment_id,
        "needs_user",
        error=(
            f"Amadeus test activity {activity.get('id')} was retrieved.{quote} "
            "No order was submitted and no card was charged."
        ),
    )


def _request(method: str, path: str, *, query: dict | None = None, form: dict | None = None, token: str | None = None) -> dict:
    _require_test_host()
    url = _url(path, query)
    headers = {
        "Accept": "application/json, application/vnd.amadeus+json",
        "User-Agent": "swanavi-attractions/test",
    }
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_RefuseRedirects, urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read()
    except AttractionProviderError:
        raise
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc.read())
        raise AttractionProviderError(
            f"Amadeus test API returned {exc.code}: {detail}; no card was charged"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AttractionProviderError("Amadeus test request failed; no card was charged") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttractionProviderError("Amadeus test response was not JSON; no card was charged") from exc
    if not isinstance(payload, dict):
        raise AttractionProviderError("Amadeus test response was not an object; no card was charged")
    return payload


def _url(path: str, query: dict | None) -> str:
    if not path.startswith("/v1/") or ".." in path:
        raise AttractionProviderError("refused non-test Amadeus path; no card was charged")
    url = _TEST_ORIGIN + path
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != _TEST_HOST:
        raise AttractionProviderError(
            f"refused Amadeus host {parsed.hostname!r}; no card was charged"
        )
    return url


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AttractionProviderError("refused Amadeus redirect; no card was charged")


def _data_list(payload: dict) -> list[dict]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _data_object(payload: dict) -> dict | None:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    items = _data_list(payload)
    return items[0] if items else None


def _coordinates(location: dict) -> tuple[str, str] | None:
    geo = location.get("geoCode")
    if not isinstance(geo, dict):
        return None
    try:
        latitude = float(geo.get("latitude"))
        longitude = float(geo.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return (f"{latitude:.6f}", f"{longitude:.6f}")


def _name_matches(activity: dict, requested: str) -> bool:
    found = str(activity.get("name", "")).casefold().strip()
    target = requested.casefold().strip()
    if not found or not target:
        return False
    if found == target:
        return True
    if len(target) >= 4 and target in found:
        return True
    return len(found) >= 4 and found in target


def _quote(activity: dict) -> str:
    price = activity.get("price")
    if not isinstance(price, dict):
        return ""
    amount = price.get("amount")
    currency = price.get("currencyCode")
    if not isinstance(amount, str) or not isinstance(currency, str):
        return ""
    if len(amount) > 20 or not re.fullmatch(r"[A-Z]{3}", currency):
        return ""
    return f" Quoted {amount} {currency}."


def _error_detail(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "request failed"
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            title = errors[0].get("title") or errors[0].get("detail")
            if isinstance(title, str) and title.strip():
                return title.strip()[:180]
        description = payload.get("error_description")
        if isinstance(description, str) and description.strip():
            return description.strip()[:180]
    return "request failed"


def _contains_payment(value: object, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_payment_key(key) or _contains_payment(item, depth + 1):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_payment(item, depth + 1) for item in value)
    return False


def _is_payment_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in _PAYMENT_KEYS
