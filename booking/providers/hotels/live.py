"""Amadeus test client: Hotel Search, then Hotel Booking.

Loaded only when ``book`` selects the live provider. Unit tests must not
call this module. The only supported invoke path is the AgentCore runtime,
which calls ``handler`` and then ``book``.

Requests go to ``https://test.api.amadeus.com`` and nowhere else. Response
``self`` links are ignored so a payload cannot redirect the client onto
production. Card data is never sent.
"""

from __future__ import annotations

import json
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener

from .errors import HotelProviderError
from .safety import contains_payment_instrument
from .segment import HotelStay, traveler_name

# Locked host. There is no constructor argument that can point this at production.
AMADEUS_TEST_ORIGIN = "https://test.api.amadeus.com"
_TEST_HOST = "test.api.amadeus.com"

_HOTEL_LIST_PATH = "/v1/reference-data/locations/hotels/by-city"
_HOTEL_SEARCH_PATH = "/v3/shopping/hotel-offers"
_HOTEL_BOOKING_PATH = "/v1/booking/hotel-bookings"
_TOKEN_PATH = "/v1/security/oauth2/token"

# paymentType values that charge the guest at booking time.
_CHARGE_POLICIES = {"deposit", "prepay", "prepaid"}


class AmadeusHotelClient:
    """Hotel Search, then Hotel Booking, on the Amadeus test host only."""

    name = "live"

    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise HotelProviderError("Amadeus client credentials are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None

    def book(self, stay: HotelStay, travelers: list, trip_id: str, fault: object = None) -> dict:
        if _fault_set(fault):
            raise HotelProviderError("sandboxFault is not sent to Amadeus")
        if not travelers:
            return _needs_user(stay, "Amadeus Hotel Booking needs at least one traveler name")
        if stay.hotel_id_rejected:
            return _needs_user(stay, "hotelId must be an Amadeus hotel id")
        if stay.city_code_rejected:
            return _needs_user(stay, "cityCode must be a 3-letter IATA city code")

        hotel_ids = stay.hotel_ids
        if not hotel_ids:
            city_code = _city_code(stay)
            if city_code is None:
                return _needs_user(
                    stay,
                    "city needs an IATA city code (segment.cityCode) for Amadeus Hotel Search",
                )
            hotel_ids = self._hotel_ids_for_city(city_code)
        if not hotel_ids:
            raise HotelProviderError("Amadeus Hotel List returned no hotels for Hotel Search")

        offer = self._search_offer(stay, hotel_ids)
        confirmation, price = self._create_booking(offer, travelers, trip_id, stay.rooms)
        return {
            "segmentId": stay.segment_id,
            "kind": "hotel",
            "status": "booked",
            "confirmationCode": confirmation,
            "price": price,
            "error": None,
        }

    def _hotel_ids_for_city(self, city_code: str) -> tuple[str, ...]:
        payload = self._get(
            _HOTEL_LIST_PATH,
            {"cityCode": city_code, "radius": "5", "radiusUnit": "KM"},
        )
        ids: list[str] = []
        for item in _data_list(payload):
            hotel_id = item.get("hotelId") if isinstance(item, dict) else None
            safe = _safe_token(hotel_id, max_len=12)
            if safe and safe not in ids:
                ids.append(safe)
            if len(ids) == 8:
                break
        return tuple(ids)

    def _search_offer(self, stay: HotelStay, hotel_ids: tuple[str, ...]) -> dict:
        adults = max(1, min(9, (stay.guests + stay.rooms - 1) // stay.rooms))
        rooms = max(1, min(9, stay.rooms))
        payload = self._get(
            _HOTEL_SEARCH_PATH,
            {
                "hotelIds": ",".join(hotel_ids),
                "adults": str(adults),
                "checkInDate": stay.check_in.isoformat(),
                "checkOutDate": stay.check_out.isoformat(),
                "roomQuantity": str(rooms),
            },
        )
        offer = _cheapest_offer_without_charge(_data_list(payload))
        if offer is None:
            raise HotelProviderError(
                "Amadeus Hotel Search returned no offer that can be booked without charging a card"
            )
        return offer

    def _create_booking(self, offer: dict, travelers: list, trip_id: str, rooms: int) -> tuple[str, dict]:
        offer_id = _safe_token(offer.get("id"), max_len=128)
        if offer_id is None:
            raise HotelProviderError("Amadeus Hotel Search offer id is invalid")
        body = _booking_body(offer_id, travelers, trip_id, rooms)
        payload = self._post_json(_HOTEL_BOOKING_PATH, body)
        confirmation = _confirmation_code(payload)
        price = _price(offer, rooms)
        return confirmation, price

    def _get(self, path: str, query: dict[str, str]) -> dict:
        return self._send("GET", f"{path}?{urlencode(query)}", None, json_body=False)

    def _post_json(self, path: str, body: dict) -> dict:
        if contains_payment_instrument(body):
            raise HotelProviderError("refusing to send card or payment details")
        return self._send("POST", path, json.dumps(body).encode("utf-8"), json_body=True)

    def _send(self, method: str, path: str, data: bytes | None, json_body: bool) -> dict:
        url = _test_url(path)
        token = self._access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        return _read_json(_open(request))

    def _access_token(self) -> str:
        if self._token:
            return self._token
        form = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        ).encode("utf-8")
        request = Request(
            _test_url(_TOKEN_PATH),
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        payload = _read_json(_open(request))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise HotelProviderError("Amadeus token response did not include an access token")
        self._token = token
        return token


def _test_url(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        raise HotelProviderError("refusing non-test Amadeus host")
    url = f"{AMADEUS_TEST_ORIGIN}{path}"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host != _TEST_HOST or parsed.username or parsed.password:
        raise HotelProviderError("refusing production Amadeus host")
    return url


def _open(request: Request):
    opener = build_opener(_RefuseRedirects)
    try:
        return opener.open(request, timeout=20)
    except HotelProviderError:
        raise
    except HTTPError as exc:
        raise _http_error(exc) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HotelProviderError(f"Amadeus hotel request failed: {exc}") from exc


def _http_error(exc: HTTPError) -> HotelProviderError:
    detail = str(exc.reason)
    try:
        raw = exc.read()
    finally:
        exc.close()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        payload = None
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            detail = str(errors[0].get("detail") or errors[0].get("title") or detail)
    return HotelProviderError(f"Amadeus hotel request failed: {detail}")


def _read_json(response) -> dict:
    try:
        raw = response.read()
    finally:
        response.close()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HotelProviderError("Amadeus hotel response was not JSON") from exc
    if not isinstance(payload, dict):
        raise HotelProviderError("Amadeus hotel response was not an object")
    return payload


def _booking_body(offer_id: str, travelers: list, trip_id: str, rooms: int) -> dict:
    guests = []
    for index, traveler in enumerate(travelers, start=1):
        guest = _guest(traveler, index)
        if guest is not None:
            guests.append(guest)
    if not guests:
        raise HotelProviderError("Amadeus Hotel Booking needs a traveler name")
    guest_ids = [guest["id"] for guest in guests]
    room_count = max(1, min(9, rooms))
    if room_count == 1:
        room_list = [{"guestIds": guest_ids}]
    else:
        room_list = [{"guestIds": [guest_ids[index % len(guest_ids)]]} for index in range(room_count)]
    # No payments object. Deposit and prepay offers are skipped before this call.
    body = {
        "data": {
            "offerId": offer_id,
            "guests": guests,
            "rooms": room_list,
        }
    }
    if contains_payment_instrument(body) or "payments" in body["data"]:
        raise HotelProviderError("refusing to send card or payment details")
    return body


def _guest(traveler: object, guest_id: int) -> dict | None:
    name = traveler_name(traveler)
    if name is None:
        return None
    parts = name.split()
    first = parts[0].upper()
    last = parts[-1].upper() if len(parts) > 1 else "GUEST"
    guest: dict = {"id": guest_id, "name": {"firstName": first, "lastName": last}}
    if isinstance(traveler, dict):
        contact = {}
        email = traveler.get("email")
        phone = traveler.get("phone")
        if isinstance(email, str) and email.strip() and "@" in email:
            contact["email"] = email.strip()
        if isinstance(phone, str) and phone.strip():
            contact["phone"] = phone.strip()
        if contact:
            guest["contact"] = contact
    return guest


def _cheapest_offer_without_charge(hotels: list) -> dict | None:
    best: tuple[Decimal, dict] | None = None
    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        offers = hotel.get("offers")
        if not isinstance(offers, list):
            continue
        for offer in offers:
            if not isinstance(offer, dict) or _charges_at_booking(offer):
                continue
            amount = _offer_amount(offer)
            if amount is None:
                continue
            if best is None or amount < best[0]:
                best = (amount, offer)
    return None if best is None else best[1]


def _charges_at_booking(offer: dict) -> bool:
    policies = offer.get("policies")
    if not isinstance(policies, dict):
        return False
    payment_type = str(policies.get("paymentType") or "").strip().lower()
    return payment_type in _CHARGE_POLICIES


def _offer_amount(offer: dict) -> Decimal | None:
    price = offer.get("price")
    if not isinstance(price, dict):
        return None
    raw = price.get("total", price.get("base"))
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def _price(offer: dict, rooms: int) -> dict:
    amount = _offer_amount(offer)
    if amount is None:
        raise HotelProviderError("Amadeus Hotel Search offer is missing a price")
    price = offer.get("price") if isinstance(offer.get("price"), dict) else {}
    currency = price.get("currency")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        currency = "USD"
    total = (amount * max(1, rooms)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"amount": f"{total:.2f}", "currency": currency.upper()}


def _confirmation_code(payload: dict) -> str:
    data = payload.get("data")
    record = data[0] if isinstance(data, list) and data else data
    if not isinstance(record, dict):
        raise HotelProviderError("Amadeus Hotel Booking did not return a confirmation")
    code = record.get("providerConfirmationId") or record.get("id")
    if not isinstance(code, str) or not code.strip():
        raise HotelProviderError("Amadeus Hotel Booking did not return a confirmation")
    return code.strip()


def _data_list(payload: dict) -> list:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _city_code(stay: HotelStay) -> str | None:
    if stay.city_code:
        return stay.city_code
    if stay.airports:
        return stay.airports[0]
    if len(stay.city) == 3 and stay.city.isalpha():
        return stay.city.upper()
    return None


def _safe_token(value: object, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > max_len or not text.isalnum():
        return None
    return text


def _needs_user(stay: HotelStay, error: str) -> dict:
    return {
        "segmentId": stay.segment_id,
        "kind": "hotel",
        "status": "needs_user",
        "confirmationCode": None,
        "price": None,
        "error": error,
    }


def _fault_set(fault: object) -> bool:
    if fault is None or fault is False:
        return False
    if isinstance(fault, str) and not fault.strip():
        return False
    return True


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HotelProviderError("refusing Amadeus redirect")
