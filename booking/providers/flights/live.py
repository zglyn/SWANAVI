"""Amadeus test client for Flight Offers Search and Flight Create Orders.

Used only when `ROAM_FLIGHT_PROVIDER=live` and `AMADEUS_HOSTNAME=test` with
`AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`. The host is fixed to
`test.api.amadeus.com`. Production is never called. No card data is sent.
Unit tests must not call this module.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse

from .errors import FlightProviderError
from .result import booking_result

_TEST_HOST = "test.api.amadeus.com"
_TEST_ORIGIN = f"https://{_TEST_HOST}"
_TOKEN_PATH = "/v1/security/oauth2/token"
_SEARCH_PATH = "/v2/shopping/flight-offers"
_ORDER_PATH = "/v1/booking/flight-orders"
_ALLOWED_PATHS = frozenset({_TOKEN_PATH, _SEARCH_PATH, _ORDER_PATH})
_CARD_KEYS = frozenset(
    {"creditCard", "securityCode", "cardNumber", "cvv", "cvc", "pan", "formOfPayments"}
)
_IATA = re.compile(r"^[A-Za-z]{3}$")
_CALLING_CODE = re.compile(r"^\+?[0-9]{1,4}$")
_PHONE_NUMBER = re.compile(r"^[0-9]{1,15}$")
_GENDERS = {"MALE", "FEMALE", "UNSPECIFIED", "UNDISCLOSED"}
_CABIN = {
    "economy": "ECONOMY",
    "premium_economy": "PREMIUM_ECONOMY",
    "business": "BUSINESS",
    "first": "FIRST",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FlightProviderError(
            "refusing Amadeus redirect; production was not called and no card was charged"
        )


class LiveFlightAdapter:
    """Search Amadeus test offers, then create an order without a card."""

    def book(self, segment: dict, travelers: list, trip_id: str) -> dict:
        _require_test_env()
        problems, search_travelers, order_travelers, contacts = _party(segment, travelers)
        segment_id = segment.get("segmentId") if isinstance(segment.get("segmentId"), str) else None
        if problems:
            return booking_result(segment_id, "needs_user", error="; ".join(problems))
        token = _access_token()
        offer = _search_offer(token, segment, search_travelers)
        order = _create_order(token, offer, order_travelers, contacts, trip_id)
        data = order.get("data") if isinstance(order, dict) else None
        if not isinstance(data, dict):
            raise FlightProviderError("Amadeus test order returned no confirmation; no card was charged")
        code = _confirmation(data)
        price = _order_price(data, offer)
        return booking_result(segment_id, "booked", confirmation_code=code, price=price, error=None)


def _require_test_env() -> None:
    hostname = os.environ.get("AMADEUS_HOSTNAME", "").strip().lower()
    if hostname != "test":
        raise FlightProviderError(
            "AMADEUS_HOSTNAME must be test; production was not called and no card was charged"
        )
    if urlparse(_TEST_ORIGIN).hostname != _TEST_HOST:
        raise FlightProviderError("refusing non-test Amadeus host; no card was charged")
    client_id = os.environ.get("AMADEUS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("AMADEUS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise FlightProviderError(
            "AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET are required; no request was sent and no card was charged"
        )


def _access_token() -> str:
    body = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": os.environ["AMADEUS_CLIENT_ID"].strip(),
            "client_secret": os.environ["AMADEUS_CLIENT_SECRET"].strip(),
        }
    ).encode()
    payload = _request(
        _TOKEN_PATH,
        body,
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        "Amadeus test authentication",
        scrub_body=True,
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise FlightProviderError("Amadeus test authentication failed; no card was charged")
    return token


def _search_offer(token: str, segment: dict, search_travelers: list[dict]) -> dict:
    body = _without_card_fields(
        {
            "currencyCode": "USD",
            "originDestinations": _origin_destinations(segment),
            "travelers": search_travelers,
            "sources": ["GDS"],
            "searchCriteria": {
                "maxFlightOffers": 5,
                "flightFilters": {
                    "cabinRestrictions": [
                        {
                            "cabin": _CABIN[segment["cabin"]],
                            "coverage": "MOST_SEGMENTS",
                            "originDestinationIds": [item["id"] for item in _origin_destinations(segment)],
                        }
                    ]
                },
            },
        }
    )
    payload = _request(
        _SEARCH_PATH,
        json.dumps(body).encode(),
        _json_headers(token),
        "Flight Offers Search",
    )
    offers = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(offers, list) or not offers:
        raise FlightProviderError("Flight Offers Search returned no offers; no card was charged")
    for offer in offers:
        if isinstance(offer, dict) and offer.get("paymentCardRequired") is not True:
            cleaned = _without_card_fields(offer)
            if isinstance(cleaned, dict):
                return cleaned
    raise FlightProviderError(
        "Flight Offers Search returned only card-required offers; no card was sent and no card was charged"
    )


def _create_order(
    token: str,
    offer: dict,
    order_travelers: list[dict],
    contacts: list[dict],
    trip_id: str,
) -> dict:
    remark = re.sub(r"[^A-Za-z0-9 -]", "", trip_id.strip())[:60] or "TRIP"
    body = _without_card_fields(
        {
            "data": {
                "type": "flight-order",
                "flightOffers": [offer],
                "travelers": order_travelers,
                "contacts": contacts,
                "remarks": {
                    "general": [{"subType": "GENERAL_MISCELLANEOUS", "text": f"TRIP {remark}"}]
                },
                # Unpaid test hold. CONFIRM means payment is done; this client never pays.
                "ticketingAgreement": {"option": "DELAY_TO_CANCEL", "delay": "6D"},
            }
        }
    )
    encoded = json.dumps(body)
    if any(marker in encoded for marker in ('"creditCard"', '"securityCode"', '"cardNumber"')):
        raise FlightProviderError("refusing to send card data; no request was sent and no card was charged")
    return _request(
        _ORDER_PATH,
        encoded.encode(),
        _json_headers(token),
        "Flight Create Orders",
    )


def _request(path: str, body: bytes, headers: dict[str, str], api_name: str, *, scrub_body: bool = False) -> dict:
    if path not in _ALLOWED_PATHS:
        raise FlightProviderError("refusing unexpected Amadeus path; no card was charged")
    url = _TEST_ORIGIN + path
    if urlparse(url).hostname != _TEST_HOST:
        raise FlightProviderError("refusing non-test Amadeus host; no card was charged")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            final_host = urlparse(response.geturl()).hostname
            if final_host != _TEST_HOST:
                raise FlightProviderError(
                    "refusing Amadeus response from a non-test host; no card was charged"
                )
            raw = response.read(2_000_000)
    except FlightProviderError:
        raise
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc.read(65536), scrub_body=scrub_body)
        raise FlightProviderError(f"{api_name} failed: {detail}; no card was charged") from None
    except Exception:
        raise FlightProviderError(f"{api_name} failed; no card was charged") from None
    try:
        payload = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        raise FlightProviderError(f"{api_name} returned invalid JSON; no card was charged") from None
    if not isinstance(payload, dict):
        raise FlightProviderError(f"{api_name} returned an invalid response; no card was charged")
    return payload


def _json_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _origin_destinations(segment: dict) -> list[dict]:
    outbound = {
        "id": "1",
        "originLocationCode": segment["from"].strip().upper(),
        "destinationLocationCode": segment["to"].strip().upper(),
        "departureDateTimeRange": {"date": segment["departDate"]},
    }
    legs = [outbound]
    if segment.get("returnDate") is not None:
        legs.append(
            {
                "id": "2",
                "originLocationCode": segment["to"].strip().upper(),
                "destinationLocationCode": segment["from"].strip().upper(),
                "departureDateTimeRange": {"date": segment["returnDate"]},
            }
        )
    return legs


def _party(segment: dict, travelers: list) -> tuple[list[str], list[dict], list[dict], list[dict]]:
    problems: list[str] = []
    origin = segment.get("from")
    destination = segment.get("to")
    if not isinstance(origin, str) or _IATA.fullmatch(origin.strip()) is None:
        problems.append("from must be an IATA code for Amadeus test")
    if not isinstance(destination, str) or _IATA.fullmatch(destination.strip()) is None:
        problems.append("to must be an IATA code for Amadeus test")
    depart = _parse_date(segment.get("departDate"))
    if depart is None:
        problems.append("departDate must be YYYY-MM-DD")
    index = {}
    for traveler in travelers:
        if isinstance(traveler, dict):
            traveler_id = traveler.get("id", traveler.get("travelerId"))
            if isinstance(traveler_id, str) and traveler_id.strip():
                index[traveler_id.strip()] = traveler
    profiles: list[tuple[str, dict]] = []
    for traveler_id in segment.get("travelerIds") or []:
        if not isinstance(traveler_id, str):
            continue
        traveler = index.get(traveler_id.strip())
        if traveler is None:
            problems.append(f"traveler {traveler_id.strip()} was not provided")
            continue
        profile, profile_problems = _profile(traveler_id.strip(), traveler, depart)
        problems.extend(profile_problems)
        if profile is not None:
            profiles.append((traveler_id.strip(), profile))
    if problems or depart is None or not profiles:
        if not problems:
            problems.append("at least one traveler is required")
        return problems, [], [], []
    adults = [offset for offset, (_, profile) in enumerate(profiles, start=1) if profile["travelerType"] == "ADULT"]
    if any(profile["travelerType"] == "HELD_INFANT" for _, profile in profiles) and not adults:
        return ["an infant needs an adult traveler"], [], [], []
    search_travelers: list[dict] = []
    order_travelers: list[dict] = []
    for offset, (_, profile) in enumerate(profiles, start=1):
        amadeus_id = str(offset)
        search_item = {"id": amadeus_id, "travelerType": profile["travelerType"]}
        if profile["travelerType"] == "HELD_INFANT":
            search_item["associatedAdultId"] = str(adults[0])
        search_travelers.append(search_item)
        order_travelers.append(
            {
                "id": amadeus_id,
                "dateOfBirth": profile["dateOfBirth"],
                "name": {"firstName": profile["firstName"], "lastName": profile["lastName"]},
                "gender": profile["gender"],
                "contact": {
                    "emailAddress": profile["email"],
                    "phones": [
                        {
                            "deviceType": "MOBILE",
                            "countryCallingCode": profile["countryCallingCode"],
                            "number": profile["phoneNumber"],
                        }
                    ],
                },
            }
        )
    first = order_travelers[0]
    contacts = [
        {
            "addresseeName": first["name"],
            "purpose": "STANDARD",
            "emailAddress": first["contact"]["emailAddress"],
            "phones": first["contact"]["phones"],
        }
    ]
    return [], search_travelers, order_travelers, contacts


def _profile(traveler_id: str, traveler: dict, depart: date | None) -> tuple[dict | None, list[str]]:
    problems: list[str] = []
    first, last = _person_name(traveler)
    if not first or not last:
        problems.append(f"traveler {traveler_id} needs a given name and family name")
    dob = _parse_date(traveler.get("dateOfBirth"))
    if dob is None:
        problems.append(f"traveler {traveler_id} needs dateOfBirth YYYY-MM-DD")
    gender = traveler.get("gender")
    if not isinstance(gender, str) or gender.strip().upper() not in _GENDERS:
        problems.append(f"traveler {traveler_id} needs gender MALE, FEMALE, UNSPECIFIED, or UNDISCLOSED")
        gender_value = ""
    else:
        gender_value = gender.strip().upper()
    email = traveler.get("email") or traveler.get("emailAddress")
    if not isinstance(email, str) or "@" not in email or email.strip().startswith("@"):
        problems.append(f"traveler {traveler_id} needs an email")
        email_value = ""
    else:
        email_value = email.strip()
    calling_code = traveler.get("countryCallingCode")
    number = traveler.get("phoneNumber") or traveler.get("phone")
    if not isinstance(calling_code, str) or _CALLING_CODE.fullmatch(calling_code.strip()) is None:
        problems.append(f"traveler {traveler_id} needs countryCallingCode")
        calling_code = ""
    if not isinstance(number, str) or _PHONE_NUMBER.fullmatch(number.strip()) is None:
        problems.append(f"traveler {traveler_id} needs phoneNumber")
        number = ""
    if problems or depart is None or dob is None:
        return None, problems
    return (
        {
            "firstName": first.upper()[:56],
            "lastName": last.upper()[:57],
            "dateOfBirth": dob.isoformat(),
            "gender": gender_value,
            "email": email_value,
            "countryCallingCode": str(calling_code).strip().lstrip("+"),
            "phoneNumber": str(number).strip(),
            "travelerType": _traveler_type(dob, depart),
        },
        [],
    )


def _person_name(traveler: dict) -> tuple[str, str]:
    given = traveler.get("givenName") or traveler.get("firstName")
    family = traveler.get("familyName") or traveler.get("lastName")
    if isinstance(given, str) and given.strip() and isinstance(family, str) and family.strip():
        return given.strip(), family.strip()
    name = traveler.get("name")
    if isinstance(name, str) and " " in name.strip():
        first, last = name.strip().rsplit(" ", 1)
        return first.strip(), last.strip()
    return "", ""


def _traveler_type(dob: date, depart: date) -> str:
    years = depart.year - dob.year - ((depart.month, depart.day) < (dob.month, dob.day))
    if years >= 12:
        return "ADULT"
    if years >= 2:
        return "CHILD"
    return "HELD_INFANT"


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _confirmation(data: dict) -> str:
    records = data.get("associatedRecords")
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("reference"), str) and record["reference"].strip():
                return record["reference"].strip()
    order_id = data.get("id")
    if isinstance(order_id, str) and order_id.strip():
        return order_id.strip()
    raise FlightProviderError("Amadeus test order returned no confirmation; no card was charged")


def _order_price(data: dict, offer: dict) -> dict:
    offers = data.get("flightOffers")
    source = offers[0] if isinstance(offers, list) and offers and isinstance(offers[0], dict) else offer
    price = source.get("price") if isinstance(source, dict) else None
    if not isinstance(price, dict):
        raise FlightProviderError("Amadeus test order returned no price; no card was charged")
    amount = price.get("grandTotal") or price.get("total")
    currency = price.get("currency")
    if isinstance(amount, bool) or not isinstance(currency, str) or not currency.strip():
        raise FlightProviderError("Amadeus test order returned no price; no card was charged")
    if not isinstance(amount, str):
        amount = str(amount) if isinstance(amount, int | float) else ""
    try:
        quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise FlightProviderError("Amadeus test order returned no price; no card was charged") from None
    return {"amount": f"{quantized:.2f}", "currency": currency.strip()}


def _without_card_fields(value):
    if isinstance(value, dict):
        return {key: _without_card_fields(item) for key, item in value.items() if key not in _CARD_KEYS}
    if isinstance(value, list):
        return [_without_card_fields(item) for item in value]
    return value


def _error_detail(raw: bytes, *, scrub_body: bool) -> str:
    if scrub_body:
        return "authentication failed"
    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _scrub(text)[:300] or "request failed"
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if isinstance(errors, list):
        parts: list[str] = []
        for item in errors[:3]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") if isinstance(item.get("title"), str) else ""
            detail = item.get("detail") if isinstance(item.get("detail"), str) else ""
            message = " ".join(part for part in (title.strip(), detail.strip()) if part)
            if message:
                parts.append(message)
        if parts:
            return _scrub("; ".join(parts))[:500]
    return "request failed"


def _scrub(text: str) -> str:
    for key in ("AMADEUS_CLIENT_SECRET", "AMADEUS_CLIENT_ID"):
        secret = os.environ.get(key, "").strip()
        if secret:
            text = text.replace(secret, "[redacted]")
    return text
