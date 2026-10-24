"""Uber Rides API client for the sandbox host.

Used only when ``ROAM_RIDE_PROVIDER=live`` and ``UBER_ACCESS_TOKEN`` is set.
Unit tests must not call this module. Requests go to
``https://sandbox-api.uber.com`` only. ``https://api.uber.com`` is never
requested.

The call order matches the Uber Rides API ride-request flow:

1. ``POST /v1.2/requests/estimate`` from ``pickupName`` to ``dropoffName``.
2. ``POST /v1.2/requests`` to create that trip at ``pickupAt``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

_SANDBOX_HOST = "sandbox-api.uber.com"
_SANDBOX_ORIGIN = f"https://{_SANDBOX_HOST}"
_PRODUCTION_HOSTS = frozenset({"api.uber.com", "www.uber.com"})
_ESTIMATE_PATH = "/v1.2/requests/estimate"
_REQUEST_PATH = "/v1.2/requests"
_ALLOWED_PATHS = frozenset({_ESTIMATE_PATH, _REQUEST_PATH})


class RideProviderError(Exception):
    """The Uber sandbox call did not request a ride. Production was not called."""


class UberRidesClient:
    """Estimate a ride, then create it on the Uber sandbox host."""

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    def request(self, pickup_name: str, dropoff_name: str, pickup_at: str, party_size: int | None) -> dict:
        estimate = _post(
            self._access_token,
            _ESTIMATE_PATH,
            _estimate_body(pickup_name, dropoff_name, party_size),
        )
        fare_id = _fare_id(estimate)
        if fare_id is None:
            raise RideProviderError(
                "Uber Rides API estimate did not return a fare_id; the trip was not created"
            )
        created = _post(
            self._access_token,
            _REQUEST_PATH,
            _trip_body(pickup_name, dropoff_name, pickup_at, party_size, fare_id, _product_id(estimate)),
        )
        request_id = created.get("request_id") if isinstance(created, dict) else None
        if not isinstance(request_id, str) or not request_id.strip():
            raise RideProviderError("Uber Rides API did not return a request_id; production was not called")
        return {
            "status": "requested",
            "rideCode": request_id.strip(),
            "pickupAt": pickup_at,
            "dropoffName": dropoff_name,
            "partySize": party_size,
            "reason": None,
        }


def _estimate_body(pickup_name: str, dropoff_name: str, party_size: int | None) -> dict:
    """Uber Rides API ``POST /v1.2/requests/estimate`` body.

    Place names from the trip plan fill the documented pickup and dropoff
    address fields. The plan does not carry coordinates.
    """
    body = {
        "start_nickname": pickup_name,
        "start_address": pickup_name,
        "end_nickname": dropoff_name,
        "end_address": dropoff_name,
    }
    if party_size is not None:
        body["seat_count"] = party_size
    return body


def _trip_body(
    pickup_name: str,
    dropoff_name: str,
    pickup_at: str,
    party_size: int | None,
    fare_id: str,
    product_id: str | None,
) -> dict:
    """Uber Rides API ``POST /v1.2/requests`` body for one trip at ``pickup_at``."""
    body = {
        "fare_id": fare_id,
        "start_nickname": pickup_name,
        "start_address": pickup_name,
        "end_nickname": dropoff_name,
        "end_address": dropoff_name,
        "scheduling": {"pickup_time": pickup_at},
    }
    if product_id is not None:
        body["product_id"] = product_id
    if party_size is not None:
        body["seat_count"] = party_size
    return body


def _post(token: str, path: str, body: dict) -> dict:
    url = _url(path)
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "swanavi-ride/sandbox",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(_RefuseRedirects, urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read()
            final_url = response.geturl()
    except RideProviderError:
        raise
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc.read(), token)
        raise RideProviderError(
            f"Uber Rides API sandbox returned {exc.code}: {detail}; production was not called"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RideProviderError("Uber Rides API sandbox request failed; production was not called") from exc
    _require_sandbox_url(final_url)
    return _json_object(raw)


def _url(path: str) -> str:
    if path not in _ALLOWED_PATHS or ".." in path:
        raise RideProviderError("refused Uber path; production was not called")
    url = _SANDBOX_ORIGIN + path
    _require_sandbox_url(url)
    return url


def _require_sandbox_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme != "https" or host != _SANDBOX_HOST or host in _PRODUCTION_HOSTS:
        raise RideProviderError("refused non-sandbox Uber host; production was not called")


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RideProviderError("refused Uber redirect; production was not called")


def _json_object(raw: bytes) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RideProviderError("Uber Rides API sandbox response was not JSON; production was not called") from exc
    if not isinstance(payload, dict):
        raise RideProviderError("Uber Rides API sandbox response was not an object; production was not called")
    return payload


def _fare_id(payload: dict) -> str | None:
    fare = payload.get("fare")
    if not isinstance(fare, dict):
        return None
    fare_id = fare.get("fare_id")
    if not isinstance(fare_id, str) or not fare_id.strip():
        return None
    return fare_id.strip()


def _product_id(payload: dict) -> str | None:
    product_id = payload.get("product_id")
    if isinstance(product_id, str) and product_id.strip():
        return product_id.strip()
    fare = payload.get("fare")
    if isinstance(fare, dict):
        nested = fare.get("product_id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def _error_detail(raw: bytes, token: str) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "request failed"
    detail = "request failed"
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            title = errors[0].get("title") or errors[0].get("code")
            if isinstance(title, str) and title.strip():
                detail = title.strip()
        elif isinstance(payload.get("title"), str) and payload["title"].strip():
            detail = payload["title"].strip()
        elif isinstance(payload.get("message"), str) and payload["message"].strip():
            detail = payload["message"].strip()
    if token and token in detail:
        detail = detail.replace(token, "[redacted]")
    return detail[:180]
