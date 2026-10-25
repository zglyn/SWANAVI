"""Tool names the master calls.

Each function forwards to a capability package. None of them books a supplier,
parses an inbox, decides whether the trip is on track, shifts the day, decides
a guard outcome, or decides an assist outcome.
"""

from __future__ import annotations

import inspect
from typing import Any

from booking.master.capabilities import (
    AUTHORIZE_SPEND_NOT_INSTALLED,
    CHECK_BUDGET_NOT_INSTALLED,
    CHECK_CONFLICTS_NOT_INSTALLED,
    CHECK_ENTRY_NOT_INSTALLED,
    CHECK_HOURS_NOT_INSTALLED,
    CHECK_TRANSFER_NOT_INSTALLED,
    CHECK_WEATHER_NOT_INSTALLED,
    EMERGENCY_CARD_NOT_INSTALLED,
    HOLD_TABLE_NOT_INSTALLED,
    LUGGAGE_DROP_NOT_INSTALLED,
    PROGRESS_NOT_INSTALLED,
    PROVIDER_NOT_INSTALLED,
    QUOTE_FX_NOT_INSTALLED,
    REFUND_BOOKING_NOT_INSTALLED,
    REPLAN_NOT_INSTALLED,
    REQUEST_RIDE_NOT_INSTALLED,
    TRIP_NOTICE_NOT_INSTALLED,
    TRIP_WALLET_NOT_INSTALLED,
    VERIFIER_NOT_INSTALLED,
    WATCH_NOT_INSTALLED,
    AFTER_DARK_NOT_INSTALLED,
    AIRPORT_LEAVE_NOT_INSTALLED,
    LATE_CHECKOUT_NOT_INSTALLED,
    PHRASE_CARD_NOT_INSTALLED,
    TIP_POLICY_NOT_INSTALLED,
    FLIGHT_STATUS_NOT_INSTALLED,
    CHECK_IN_FLIGHT_NOT_INSTALLED,
    REFUSE_DCC_NOT_INSTALLED,
    PICK_CARD_NOT_INSTALLED,
    CASH_NEEDED_NOT_INSTALLED,
    HOLIDAY_CLOSURE_NOT_INSTALLED,
    CHECK_LAYOVER_NOT_INSTALLED,
    ETIQUETTE_CARD_NOT_INSTALLED,
    TAX_REFUND_NOT_INSTALLED,
    REBOOK_SEGMENT_NOT_INSTALLED,
    INCIDENTAL_HOLD_NOT_INSTALLED,
    LANDING_DATA_NOT_INSTALLED,
    ProgressNotInstalled,
    load_after_dark,
    load_airport_leave,
    load_authorize_spend,
    load_book,
    load_check_budget,
    load_check_conflicts,
    load_check_entry,
    load_check_hours,
    load_check_transfer,
    load_check_weather,
    load_emergency_card,
    load_hold_table,
    load_late_checkout,
    load_luggage_drop,
    load_phrase_card,
    load_quote_fx,
    load_refund_booking,
    load_replan,
    load_request_ride,
    load_tip_policy,
    load_trip_notice,
    load_trip_progress,
    load_trip_wallet,
    load_verifier,
    load_watch_trip,
    load_flight_status,
    load_check_in_flight,
    load_refuse_dcc,
    load_pick_card,
    load_cash_needed,
    load_holiday_closure,
    load_check_layover,
    load_etiquette_card,
    load_tax_refund,
    load_rebook_segment,
    load_incidental_hold,
    load_landing_data,
)

# One scripted demo charge. The spend guard decides payAmount and reason.
SCRIPTED_AUTHORIZED_AMOUNT = 10
SCRIPTED_REQUESTED_AMOUNT = 12
SCRIPTED_CURRENCY = "USD"

# Scripted assist inputs. The assist packages decide the outcomes.
SCRIPTED_FX_AMOUNT = 1000
SCRIPTED_FX_FROM = "JPY"
SCRIPTED_FX_TO = "USD"
SCRIPTED_VISA_ON_FILE = False
SCRIPTED_PASSPORT_DAYS_AFTER_TRIP_END = 30
SCRIPTED_WEATHER_CONDITION = "storm"
SCRIPTED_HOURS_OPEN = "09:00"
SCRIPTED_HOURS_CLOSE = "17:00"
SCRIPTED_HOURS_CLOSED_WEEKDAYS: list[int] = []
SCRIPTED_TRAVEL_MINUTES = 30
SCRIPTED_EMERGENCY_COUNTRY = "Japan"

# Scripted concierge inputs. The packages decide the outcomes.
SCRIPTED_DCC_MERCHANT_AMOUNT = 1000
SCRIPTED_DCC_MERCHANT_CURRENCY = "JPY"
SCRIPTED_DCC_OFFERED_AMOUNT = 8
SCRIPTED_DCC_OFFERED_CURRENCY = "USD"
SCRIPTED_CARD_AMOUNT = 1000
SCRIPTED_CARD_CURRENCY = "JPY"
SCRIPTED_CARD_COUNTRY = "Japan"
SCRIPTED_CARDS = (
    {"id": "visa-japan", "network": "visa", "fxFeePercent": 3, "noFxCountries": ["Japan"]},
    {"id": "mc-japan", "network": "mastercard", "fxFeePercent": 2, "noFxCountries": ["Japan"]},
)
SCRIPTED_CASH_MERCHANT = {
    "name": "Cash market",
    "acceptsCard": False,
    "amount": 1000,
    "currency": "JPY",
}
SCRIPTED_CASH_TRIP_CURRENCY = "USD"
SCRIPTED_TAX_COUNTRY = "Japan"
SCRIPTED_TAX_PURCHASES = ({"amount": 10000, "currency": "JPY", "eligible": True},)
SCRIPTED_TAX_DEPART_AT = "2026-11-06T09:00:00Z"
SCRIPTED_HOLD_AUTHORIZED = 200
SCRIPTED_HOLD_CAPTURED = 40
SCRIPTED_HOLD_OVER_CAPTURE = 250
SCRIPTED_HOLD_CURRENCY = "USD"
SCRIPTED_HOLD_CHECKOUT_AT = "2026-11-06T11:00:00Z"
SCRIPTED_ETIQUETTE_COUNTRY = "Japan"
SCRIPTED_ETIQUETTE_PLACE = "Sample shrine"
SCRIPTED_ETIQUETTE_KIND = "shrine"
SCRIPTED_LAYOVER_INBOUND = {
    "segmentId": "fixture-in",
    "arriveAt": "2026-11-02T12:00:00Z",
    "airport": "KIX",
}
SCRIPTED_LAYOVER_OUTBOUND = {
    "segmentId": "fixture-out",
    "departAt": "2026-11-02T13:00:00Z",
    "airport": "KIX",
}
SCRIPTED_LAYOVER_INTERNATIONAL = True
SCRIPTED_HAS_DATA = False

BOOK_TOOL_BY_KIND = {
    "flight": "book_flight",
    "hotel": "book_hotel",
    "attraction": "book_attraction",
}

VERIFY_TOOL_BY_KIND = {
    "flight": "verify_flight_email",
    "hotel": "verify_hotel_email",
    "attraction": "verify_attraction_email",
}


def _message(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _failed(segment: dict[str, Any], kind: str, error: str) -> dict[str, Any]:
    segment_id = segment.get("segmentId") if isinstance(segment, dict) else None
    return {
        "segmentId": segment_id if isinstance(segment_id, str) else None,
        "kind": kind,
        "status": "failed",
        "confirmationCode": None,
        "price": None,
        "error": error,
    }


def call_book(kind: str, segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call book_flight, book_hotel, or book_attraction."""

    book = load_book(kind)
    if book is None:
        return _failed(segment, kind, PROVIDER_NOT_INSTALLED)
    try:
        raw = book(segment, travelers, trip_id)
    except Exception as exc:
        return _failed(segment, kind, _message(exc))
    if not isinstance(raw, dict):
        return _failed(segment, kind, "invalid_provider_result")
    return raw


def book_flight(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call booking.providers.flights."""

    return call_book("flight", segment, travelers, trip_id)


def book_hotel(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call booking.providers.hotels."""

    return call_book("hotel", segment, travelers, trip_id)


def book_attraction(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call booking.providers.attractions."""

    return call_book("attraction", segment, travelers, trip_id)


def call_verify(
    kind: str,
    segment: dict[str, Any],
    confirmation_code: str,
    travelers: list[Any],
    trip_id: str,
) -> dict[str, Any]:
    """Sandbox path: sample_email, then verify. A real inbox is never read."""

    segment_id = segment.get("segmentId") if isinstance(segment.get("segmentId"), str) else None
    verifier = load_verifier(kind)
    if verifier is None:
        return {
            "segmentId": segment_id,
            "kind": kind,
            "verified": False,
            "reason": VERIFIER_NOT_INSTALLED,
        }
    sample_email, verify = verifier
    try:
        email = sample_email(segment, confirmation_code, travelers, trip_id)
    except Exception as exc:
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": _message(exc)}
    if not isinstance(email, dict):
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": "invalid_email"}
    try:
        outcome = verify(email, segment, confirmation_code, travelers)
    except Exception as exc:
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": _message(exc)}
    if not isinstance(outcome, dict):
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": "invalid_verifier_result"}
    verified = outcome.get("verified") is True
    reason = outcome.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "verified" if verified else "not_verified"
    return {
        "segmentId": outcome.get("segmentId") if isinstance(outcome.get("segmentId"), str) else segment_id,
        "kind": kind,
        "verified": verified,
        "reason": reason.strip(),
    }


def verify_flight_email(
    segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str
) -> dict[str, Any]:
    """Call booking.verify.flights. Sandbox uses sample_email, then verify."""

    return call_verify("flight", segment, confirmation_code, travelers, trip_id)


def verify_hotel_email(
    segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str
) -> dict[str, Any]:
    """Call booking.verify.hotels. Sandbox uses sample_email, then verify."""

    return call_verify("hotel", segment, confirmation_code, travelers, trip_id)


def verify_attraction_email(
    segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str
) -> dict[str, Any]:
    """Call booking.verify.attractions. Sandbox uses sample_email, then verify."""

    return call_verify("attraction", segment, confirmation_code, travelers, trip_id)


def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> Any:
    """Call booking.progress.trip_progress.

    Raises ProgressNotInstalled when that function is not importable.
    """

    progress = load_trip_progress()
    if progress is None:
        raise ProgressNotInstalled(PROGRESS_NOT_INSTALLED)
    return progress(plan, results, clock)


def _call_replan(
    event: str,
    trip_id: str,
    now: str,
    plan: dict[str, Any],
    disruption: dict[str, Any],
) -> Any:
    """Forward one disruption to that event's replan agent."""

    replan = load_replan(event)
    if replan is None:
        return {
            "changed": False,
            "plan": None,
            "notes": [],
            "error": REPLAN_NOT_INSTALLED,
        }
    return replan(trip_id, now, plan, disruption)


def replan_cancel(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> Any:
    """Call booking.replan.cancel.replan_cancel. One agent for a cancellation."""

    return _call_replan("cancelled", trip_id, now, plan, disruption)


def replan_early(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> Any:
    """Call booking.replan.early.replan_early. One agent for an early finish."""

    return _call_replan("ended_early", trip_id, now, plan, disruption)


def replan_late(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> Any:
    """Call booking.replan.late.replan_late. One agent for a late finish."""

    return _call_replan("ended_late", trip_id, now, plan, disruption)


BOOK_TOOLS = {
    "flight": book_flight,
    "hotel": book_hotel,
    "attraction": book_attraction,
}

VERIFY_TOOLS = {
    "flight": verify_flight_email,
    "hotel": verify_hotel_email,
    "attraction": verify_attraction_email,
}

REPLAN_TOOLS = {
    "cancelled": replan_cancel,
    "ended_early": replan_early,
    "ended_late": replan_late,
}


def check_budget(trip_id: str, segment: dict[str, Any], price: dict[str, Any] | None) -> Any:
    """Call booking.guard.budget.check_budget before a booked segment is accepted.

    Returns the tool result, or ``check_budget_not_installed`` when that
    function cannot be imported.
    """

    budget = load_check_budget()
    if budget is None:
        return CHECK_BUDGET_NOT_INSTALLED
    try:
        return _call_budget(budget, trip_id, segment, price)
    except Exception as exc:
        return {"allowed": None, "error": _message(exc)}


def authorize_spend(
    authorizedAmount: int = SCRIPTED_AUTHORIZED_AMOUNT,
    requestedAmount: int = SCRIPTED_REQUESTED_AMOUNT,
    currency: str = SCRIPTED_CURRENCY,
) -> dict[str, Any]:
    """Call booking.guard.spend.authorize_spend for the scripted demo charge.

    The master passes authorizedAmount 10, requestedAmount 12, and currency USD.
    payAmount and reason are whatever that tool returns.
    """

    record: dict[str, Any] = {
        "authorizedAmount": authorizedAmount,
        "requestedAmount": requestedAmount,
        "currency": currency,
    }
    spend = load_authorize_spend()
    if spend is None:
        record["payAmount"] = None
        record["reason"] = AUTHORIZE_SPEND_NOT_INSTALLED
        return record
    try:
        # The spend package names these fields. Positional order is segmentId, currency, then the amounts.
        raw = spend(authorizedAmount=authorizedAmount, requestedAmount=requestedAmount, currency=currency)
    except Exception as exc:
        record["payAmount"] = None
        record["reason"] = _message(exc)
        return record
    if not isinstance(raw, dict):
        record["payAmount"] = None
        record["reason"] = "invalid_spend_result"
        return record
    record.update(raw)
    record.setdefault("payAmount", None)
    record.setdefault("reason", None)
    return record


def refund_booking(
    trip_id: str,
    segment_id: str | None,
    confirmation_code: str | None,
    amount: Any = None,
    currency: str | None = None,
) -> Any:
    """Call booking.refund.refund_booking when a segment is cancelled."""

    refund = load_refund_booking()
    if refund is None:
        return REFUND_BOOKING_NOT_INSTALLED
    try:
        raw = _call_refund(refund, trip_id, segment_id, confirmation_code, amount, currency)
    except Exception as exc:
        return {"error": _message(exc)}
    if not isinstance(raw, dict):
        return {"error": "invalid_refund_result"}
    return raw


def check_conflicts(trip_id: str, plan: dict[str, Any]) -> Any:
    """Call booking.guard.conflicts.check_conflicts after a replan changes the plan."""

    conflicts = load_check_conflicts()
    if conflicts is None:
        return CHECK_CONFLICTS_NOT_INSTALLED
    try:
        raw = conflicts(trip_id, plan)
    except Exception as exc:
        return {"error": _message(exc)}
    if not isinstance(raw, dict):
        return {"error": "invalid_conflicts_result"}
    return raw


def trip_notice(trip_id: str, event: dict[str, Any]) -> Any:
    """Call booking.notify.trip_notice after a replan or an over-capture rejection."""

    notice = load_trip_notice()
    if notice is None:
        return TRIP_NOTICE_NOT_INSTALLED
    try:
        return _call_notice(notice, trip_id, event)
    except Exception as exc:
        return {"error": _message(exc)}


_NOTICE_EVENTS = frozenset({"cancelled", "ended_early", "ended_late", "booked", "over_capture_rejected"})


def check_entry(
    destinationCountry: str,
    passportExpiry: str,
    tripEnd: str,
    visaOnFile: bool = SCRIPTED_VISA_ON_FILE,
) -> Any:
    """Call booking.assist.entry.check_entry once before the trip starts.

    The master scripts passportExpiry and visaOnFile. Returns the tool result,
    or ``check_entry_not_installed`` when that function cannot be imported.
    """

    return _assist(
        load_check_entry,
        CHECK_ENTRY_NOT_INSTALLED,
        {
            "destinationCountry": destinationCountry,
            "passportExpiry": passportExpiry,
            "tripEnd": tripEnd,
            "visaOnFile": visaOnFile,
        },
    )


def check_hours(
    segmentId: str,
    start: str,
    end: str,
    open: str = SCRIPTED_HOURS_OPEN,
    close: str = SCRIPTED_HOURS_CLOSE,
    closedWeekdays: list[int] | None = None,
) -> Any:
    """Call booking.assist.hours.check_hours for one attraction after a replan."""

    return _assist(
        load_check_hours,
        CHECK_HOURS_NOT_INSTALLED,
        {
            "segmentId": segmentId,
            "start": start,
            "end": end,
            "open": open,
            "close": close,
            "closedWeekdays": list(SCRIPTED_HOURS_CLOSED_WEEKDAYS if closedWeekdays is None else closedWeekdays),
        },
    )


def check_transfer(
    fromSegmentId: str,
    toSegmentId: str,
    fromEnd: str,
    toStart: str,
    travelMinutes: int = SCRIPTED_TRAVEL_MINUTES,
) -> Any:
    """Call booking.assist.transfers.check_transfer between two consecutive stops."""

    return _assist(
        load_check_transfer,
        CHECK_TRANSFER_NOT_INSTALLED,
        {
            "fromSegmentId": fromSegmentId,
            "toSegmentId": toSegmentId,
            "fromEnd": fromEnd,
            "toStart": toStart,
            "travelMinutes": travelMinutes,
        },
    )


def quote_fx(
    amount: int = SCRIPTED_FX_AMOUNT,
    fromCurrency: str = SCRIPTED_FX_FROM,
    toCurrency: str = SCRIPTED_FX_TO,
) -> Any:
    """Call booking.assist.fx.quote_fx before authorize_spend.

    The scripted quote is 1000 JPY into USD.
    """

    quoted = _assist(
        load_quote_fx,
        QUOTE_FX_NOT_INSTALLED,
        {"amount": amount, "fromCurrency": fromCurrency, "toCurrency": toCurrency},
    )
    if isinstance(quoted, dict):
        quoted.setdefault("fromAmount", amount)
        quoted.setdefault("fromCurrency", fromCurrency)
        quoted.setdefault("toCurrency", toCurrency)
    return quoted


def check_weather(segmentId: str, outdoor: bool, condition: str = SCRIPTED_WEATHER_CONDITION) -> Any:
    """Call booking.assist.weather.check_weather for one outdoor segment."""

    return _assist(
        load_check_weather,
        CHECK_WEATHER_NOT_INSTALLED,
        {"segmentId": segmentId, "outdoor": outdoor, "condition": condition},
    )


def emergency_card(country: str = SCRIPTED_EMERGENCY_COUNTRY, travelerName: str = "") -> Any:
    """Call booking.assist.emergency.emergency_card for Japan."""

    return _assist(
        load_emergency_card,
        EMERGENCY_CARD_NOT_INSTALLED,
        {"country": country, "travelerName": travelerName},
    )


def request_ride(
    pickupAt: str,
    dropoffName: str,
    segmentId: str = "",
    toSegmentId: str = "",
    tripId: str = "",
) -> Any:
    """Call booking.assist.ride.request_ride. The package returns any SANDBOX-RIDE- code."""

    return _assist(
        load_request_ride,
        REQUEST_RIDE_NOT_INSTALLED,
        {
            "tripId": tripId,
            "trip_id": tripId,
            "segmentId": segmentId,
            "fromSegmentId": segmentId,
            "toSegmentId": toSegmentId,
            "pickupAt": pickupAt,
            "dropoffName": dropoffName,
        },
    )


def hold_table(
    segmentId: str,
    arriveAt: str,
    reservationAt: str,
    tripId: str = "",
    name: str = "",
    partySize: int | None = None,
) -> Any:
    """Call booking.assist.table.hold_table when a meal arrival is after the reservation."""

    fields: dict[str, Any] = {
        "tripId": tripId,
        "trip_id": tripId,
        "segmentId": segmentId,
        "name": name,
        "venue": name,
        "arriveAt": arriveAt,
        "reservationAt": reservationAt,
    }
    if partySize is not None:
        fields["partySize"] = partySize
    return _assist(load_hold_table, HOLD_TABLE_NOT_INSTALLED, fields)


def luggage_drop(
    arrivalAt: str,
    checkIn: str,
    segmentId: str = "",
    flightSegmentId: str = "",
    tripId: str = "",
    travelerName: str = "",
) -> Any:
    """Call booking.assist.luggage.luggage_drop when arrival is before hotel check-in."""

    return _assist(
        load_luggage_drop,
        LUGGAGE_DROP_NOT_INSTALLED,
        {
            "tripId": tripId,
            "trip_id": tripId,
            "segmentId": segmentId,
            "hotelSegmentId": segmentId,
            "flightSegmentId": flightSegmentId,
            "arrivalAt": arrivalAt,
            "arriveAt": arrivalAt,
            "checkIn": checkIn,
            "checkInAt": checkIn,
            "travelerName": travelerName,
        },
    )


def airport_leave(
    tripId: str,
    segmentId: str,
    date: str,
    now: str,
    origin: str = "",
    destination: str = "",
    departAt: str = "",
    international: bool | None = None,
    hotelCheckoutAt: str = "",
) -> Any:
    """Call booking.assist.airport.airport_leave on a flight day."""

    fields: dict[str, Any] = {
        "tripId": tripId,
        "trip_id": tripId,
        "segmentId": segmentId,
        "flightSegmentId": segmentId,
        "date": date,
        "now": now,
        "from": origin,
        "to": destination,
        "origin": origin,
        "destination": destination,
    }
    if departAt:
        fields["departAt"] = departAt
    if isinstance(international, bool):
        fields["international"] = international
    if hotelCheckoutAt:
        fields["hotelCheckoutAt"] = hotelCheckoutAt
    return _assist(load_airport_leave, AIRPORT_LEAVE_NOT_INSTALLED, fields)


def after_dark(
    segmentId: str,
    name: str,
    start: str,
    end: str,
    now: str = "",
    tripId: str = "",
) -> Any:
    """Call booking.assist.afterdark.after_dark for one walk leg."""

    return _assist(
        load_after_dark,
        AFTER_DARK_NOT_INSTALLED,
        {
            "tripId": tripId,
            "trip_id": tripId,
            "segmentId": segmentId,
            "name": name,
            "start": start,
            "end": end,
            "now": now,
            "leg": "walk",
            "mode": "walk",
        },
    )


def late_checkout(
    tripId: str,
    flightSegmentId: str,
    hotelSegmentId: str,
    date: str,
    checkOut: str,
    departAt: str = "",
    travelerName: str = "",
    checkoutAt: str = "",
) -> Any:
    """Call booking.assist.checkout.late_checkout when a flight shares the checkout day."""

    fields: dict[str, Any] = {
        "tripId": tripId,
        "trip_id": tripId,
        "flightSegmentId": flightSegmentId,
        "hotelSegmentId": hotelSegmentId,
        "segmentId": hotelSegmentId,
        "date": date,
        "checkOut": checkOut,
        "checkoutAt": checkoutAt or checkOut,
    }
    if departAt:
        fields["departAt"] = departAt
    if travelerName:
        fields["travelerName"] = travelerName
    return _assist(load_late_checkout, LATE_CHECKOUT_NOT_INSTALLED, fields)


def tip_policy(tripId: str, country: str, currency: str, requestedAmount: int) -> Any:
    """Call booking.assist.tip.tip_policy before authorize_spend."""

    return _assist(
        load_tip_policy,
        TIP_POLICY_NOT_INSTALLED,
        {
            "tripId": tripId,
            "trip_id": tripId,
            "country": country,
            "currency": currency,
            "requestedAmount": requestedAmount,
            "amount": requestedAmount,
            "subtotal": requestedAmount,
        },
    )


_PHRASE_LANGUAGES = {
    "japan": "ja",
    "jp": "ja",
    "jpn": "ja",
    "france": "fr",
    "fr": "fr",
    "fra": "fr",
}


def _phrase_language(country: str) -> str:
    """Language code the phrase card already accepts for this country name."""

    return _PHRASE_LANGUAGES.get(country.strip().casefold(), "")


def phrase_card(
    tripId: str,
    country: str,
    dropoffName: str,
    pickupAt: str,
    segmentId: str = "",
) -> Any:
    """Call booking.assist.phrase.phrase_card when a ride is requested."""

    return _assist(
        load_phrase_card,
        PHRASE_CARD_NOT_INSTALLED,
        {
            "tripId": tripId,
            "trip_id": tripId,
            "country": country,
            "dropoffName": dropoffName,
            "pickupAt": pickupAt,
            "segmentId": segmentId,
            "situation": "ride",
            "language": _phrase_language(country),
            "placeName": dropoffName,
            "arriveAt": pickupAt,
        },
    )


def trip_wallet(tripId: str, codes: list[str]) -> Any:
    """Call booking.assist.wallet.trip_wallet with the codes the master already has."""

    return _assist(
        load_trip_wallet,
        TRIP_WALLET_NOT_INSTALLED,
        {
            "tripId": tripId,
            "trip_id": tripId,
            "codes": list(codes),
            "confirmationCodes": list(codes),
            "items": [{"code": code} for code in codes if isinstance(code, str) and code.strip()],
        },
    )


def flight_status(
    tripId: str,
    now: str,
    segment: dict[str, Any],
    feed: dict[str, Any] | None = None,
) -> Any:
    """Call booking.assist.flightstatus.flight_status for one flight.

    An omitted feed is left off the call so the package reports on_time.
    """

    fields: dict[str, Any] = {"tripId": tripId, "now": now, "segment": segment}
    if feed is not None:
        fields["feed"] = feed
    return _assist(load_flight_status, FLIGHT_STATUS_NOT_INSTALLED, fields)


def check_in_flight(now: str, segment: dict[str, Any], travelers: list[Any]) -> Any:
    """Call booking.assist.checkin.check_in_flight for one flight."""

    return _assist(
        load_check_in_flight,
        CHECK_IN_FLIGHT_NOT_INSTALLED,
        {"now": now, "segment": segment, "travelers": travelers},
    )


def refuse_dcc(
    merchantAmount: int = SCRIPTED_DCC_MERCHANT_AMOUNT,
    merchantCurrency: str = SCRIPTED_DCC_MERCHANT_CURRENCY,
    offeredAmount: int = SCRIPTED_DCC_OFFERED_AMOUNT,
    offeredCurrency: str = SCRIPTED_DCC_OFFERED_CURRENCY,
) -> Any:
    """Call booking.assist.dcc.refuse_dcc for a sample terminal offer.

    The scripted offer is a JPY merchant amount with a USD terminal offer.
    """

    return _assist(
        load_refuse_dcc,
        REFUSE_DCC_NOT_INSTALLED,
        {
            "merchantAmount": merchantAmount,
            "merchantCurrency": merchantCurrency,
            "offeredAmount": offeredAmount,
            "offeredCurrency": offeredCurrency,
        },
    )


def pick_card(
    merchantCountry: str = SCRIPTED_CARD_COUNTRY,
    amount: int = SCRIPTED_CARD_AMOUNT,
    currency: str = SCRIPTED_CARD_CURRENCY,
    cards: list[dict[str, Any]] | None = None,
) -> Any:
    """Call booking.assist.card.pick_card. The Visa fixture must not be chosen."""

    return _assist(
        load_pick_card,
        PICK_CARD_NOT_INSTALLED,
        {
            "merchantCountry": merchantCountry,
            "amount": amount,
            "currency": currency,
            "cards": list(SCRIPTED_CARDS if cards is None else cards),
        },
    )


def cash_needed(
    merchant: dict[str, Any] | None = None,
    tripCurrency: str = SCRIPTED_CASH_TRIP_CURRENCY,
) -> Any:
    """Call booking.assist.cash.cash_needed for a cash-only merchant."""

    return _assist(
        load_cash_needed,
        CASH_NEEDED_NOT_INSTALLED,
        {
            "merchant": dict(SCRIPTED_CASH_MERCHANT if merchant is None else merchant),
            "tripCurrency": tripCurrency,
        },
    )


def holiday_closure(segment: dict[str, Any]) -> Any:
    """Call booking.assist.holidays.holiday_closure for one segment."""

    return _assist(load_holiday_closure, HOLIDAY_CLOSURE_NOT_INSTALLED, {"segment": segment})


def check_layover(
    inbound: dict[str, Any] | None = None,
    outbound: dict[str, Any] | None = None,
    international: bool = SCRIPTED_LAYOVER_INTERNATIONAL,
) -> Any:
    """Call booking.assist.layover.check_layover.

    The scripted fixture is a 60-minute international connection at one airport.
    """

    return _assist(
        load_check_layover,
        CHECK_LAYOVER_NOT_INSTALLED,
        {
            "inbound": dict(SCRIPTED_LAYOVER_INBOUND if inbound is None else inbound),
            "outbound": dict(SCRIPTED_LAYOVER_OUTBOUND if outbound is None else outbound),
            "international": international,
        },
    )


def etiquette_card(
    country: str = SCRIPTED_ETIQUETTE_COUNTRY,
    placeName: str = SCRIPTED_ETIQUETTE_PLACE,
    kind: str = SCRIPTED_ETIQUETTE_KIND,
) -> Any:
    """Call booking.assist.etiquette.etiquette_card for one stop."""

    return _assist(
        load_etiquette_card,
        ETIQUETTE_CARD_NOT_INSTALLED,
        {"country": country, "placeName": placeName, "kind": kind},
    )


def tax_refund(
    country: str = SCRIPTED_TAX_COUNTRY,
    purchases: list[dict[str, Any]] | None = None,
    departAt: str = SCRIPTED_TAX_DEPART_AT,
    now: str = "",
) -> Any:
    """Call booking.assist.taxrefund.tax_refund. This is a quote, not tax advice."""

    return _assist(
        load_tax_refund,
        TAX_REFUND_NOT_INSTALLED,
        {
            "country": country,
            "purchases": list(SCRIPTED_TAX_PURCHASES if purchases is None else purchases),
            "departAt": departAt,
            "now": now,
        },
    )


def rebook_segment(
    tripId: str,
    now: str,
    segment: dict[str, Any],
    travelers: list[Any],
    cancelled: bool = True,
) -> Any:
    """Call booking.assist.rebook.rebook_segment for one already-cancelled segment."""

    return _assist(
        load_rebook_segment,
        REBOOK_SEGMENT_NOT_INSTALLED,
        {
            "tripId": tripId,
            "now": now,
            "segment": segment,
            "travelers": travelers,
            "cancelled": cancelled,
        },
    )


def incidental_hold(
    authorizedHold: int = SCRIPTED_HOLD_AUTHORIZED,
    capturedAmount: int = SCRIPTED_HOLD_CAPTURED,
    currency: str = SCRIPTED_HOLD_CURRENCY,
    checkoutAt: str = SCRIPTED_HOLD_CHECKOUT_AT,
) -> Any:
    """Call booking.assist.hold.incidental_hold. Nothing is charged."""

    return _assist(
        load_incidental_hold,
        INCIDENTAL_HOLD_NOT_INSTALLED,
        {
            "authorizedHold": authorizedHold,
            "capturedAmount": capturedAmount,
            "currency": currency,
            "checkoutAt": checkoutAt,
        },
    )


def landing_data(
    country: str,
    arriveAt: str,
    now: str,
    hasData: bool = SCRIPTED_HAS_DATA,
) -> Any:
    """Call booking.assist.connectivity.landing_data. The plan code is a sandbox label."""

    return _assist(
        load_landing_data,
        LANDING_DATA_NOT_INSTALLED,
        {"country": country, "arriveAt": arriveAt, "now": now, "hasData": hasData},
    )


def watch_trip(
    now: str,
    plan: dict[str, Any],
    rides: list[Any],
    signals: list[Any],
    tripId: str = "",
) -> Any:
    """Call booking.assist.watch.watch_trip at the start of a tick.

    Returns the tool result, or ``watch_not_installed`` when that function
    cannot be imported. The master does not decide which warnings to raise.
    """

    return _assist(
        load_watch_trip,
        WATCH_NOT_INSTALLED,
        {
            "now": now,
            "plan": plan,
            "rides": rides,
            "signals": signals,
            "tripId": tripId,
            "trip_id": tripId,
        },
    )


def _assist(load: Any, missing: str, fields: dict[str, Any]) -> Any:
    fn = load()
    if fn is None:
        return missing
    try:
        return _invoke(fn, fields)
    except Exception as exc:
        return {"error": _message(exc)}


def _invoke(fn: Any, fields: dict[str, Any]) -> Any:
    """Call ``fn`` with the argument names that function already accepts."""

    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(fields)
    params = list(signature.parameters.values())
    var_kw = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
    named = [
        param
        for param in params
        if param.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    if len(named) == 1 and named[0].name not in fields and not var_kw:
        return fn(fields)
    if var_kw and not named:
        return fn(**fields)
    kwargs: dict[str, Any] = {}
    for param in named:
        if param.name in fields:
            kwargs[param.name] = fields[param.name]
            continue
        camel = _camel(param.name)
        if camel in fields:
            kwargs[param.name] = fields[camel]
    if var_kw:
        for key, value in fields.items():
            kwargs.setdefault(key, value)
        return fn(**kwargs)
    missing = [
        param.name
        for param in named
        if param.name not in kwargs and param.default is inspect.Parameter.empty
    ]
    if missing and len(named) == 1:
        return fn(fields)
    return fn(**kwargs)


def _camel(name: str) -> str:
    parts = name.split("_")
    if len(parts) == 1:
        return name
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:] if part)


def _param_names(fn: Any) -> list[str]:
    try:
        return list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return []


def _call_budget(
    budget: Any,
    trip_id: str,
    segment: dict[str, Any],
    price: dict[str, Any] | None,
) -> Any:
    """booking.guard.budget.check_budget takes one source object, not three positional args."""

    if _param_names(budget)[:1] == ["source"]:
        return budget(_budget_source(trip_id, segment, price))
    return budget(trip_id, segment, price)


def _budget_source(trip_id: str, segment: dict[str, Any], price: dict[str, Any] | None) -> dict[str, Any]:
    """Quoted price is the proposed charge. The plan has no separate budget, so that quote is the cap."""

    currency = ""
    proposed = None
    if isinstance(price, dict):
        raw_currency = price.get("currency")
        if isinstance(raw_currency, str):
            currency = raw_currency
        if "amount" in price:
            proposed = price.get("amount")
    segment_currency = segment.get("currency")
    if isinstance(segment_currency, str) and segment_currency.strip():
        currency = segment_currency
    return {
        "tripId": trip_id,
        "currency": currency,
        "budgetAmount": segment.get("budgetAmount", proposed),
        "spentAmount": segment.get("spentAmount", "0"),
        "proposedAmount": segment.get("proposedAmount", proposed),
    }


def _call_refund(
    refund: Any,
    trip_id: str,
    segment_id: str | None,
    confirmation_code: str | None,
    amount: Any,
    currency: str | None,
) -> Any:
    """booking.refund.refund_booking is (segmentId, confirmationCode, amount, currency, event)."""

    if "confirmationCode" in _param_names(refund):
        return refund(segment_id, confirmation_code, amount, currency, "cancelled")
    return refund(trip_id, segment_id, confirmation_code)


def _call_notice(notice: Any, trip_id: str, event: dict[str, Any]) -> Any:
    """booking.notify.trip_notice reads tripId, event, notes, and segmentId."""

    names = _param_names(notice)
    if "tripId" in names and "trip_id" not in names:
        name, notes, segment_id = _notice_fields(event)
        return notice(tripId=trip_id, event=name, notes=notes, segmentId=segment_id)
    return notice(trip_id, event)


def _notice_fields(event: dict[str, Any]) -> tuple[str, Any, str]:
    raw_event = event.get("event")
    raw_type = event.get("type")
    if isinstance(raw_event, str) and raw_event in _NOTICE_EVENTS:
        name = raw_event
    elif isinstance(raw_type, str) and raw_type in _NOTICE_EVENTS:
        name = raw_type
    else:
        name = "update"
    segment_id = event.get("segmentId")
    if not isinstance(segment_id, str):
        segment_id = ""
    return name, event.get("notes"), segment_id


RUNTIME_TOOLS = {
    "book_flight": book_flight,
    "book_hotel": book_hotel,
    "book_attraction": book_attraction,
    "verify_flight_email": verify_flight_email,
    "verify_hotel_email": verify_hotel_email,
    "verify_attraction_email": verify_attraction_email,
    "trip_progress": trip_progress,
    "replan_cancel": replan_cancel,
    "replan_early": replan_early,
    "replan_late": replan_late,
    "check_budget": check_budget,
    "authorize_spend": authorize_spend,
    "refund_booking": refund_booking,
    "check_conflicts": check_conflicts,
    "trip_notice": trip_notice,
    "check_entry": check_entry,
    "check_hours": check_hours,
    "check_transfer": check_transfer,
    "quote_fx": quote_fx,
    "check_weather": check_weather,
    "emergency_card": emergency_card,
    "request_ride": request_ride,
    "hold_table": hold_table,
    "luggage_drop": luggage_drop,
    "watch_trip": watch_trip,
    "airport_leave": airport_leave,
    "after_dark": after_dark,
    "late_checkout": late_checkout,
    "tip_policy": tip_policy,
    "phrase_card": phrase_card,
    "trip_wallet": trip_wallet,
    "flight_status": flight_status,
    "check_in_flight": check_in_flight,
    "refuse_dcc": refuse_dcc,
    "pick_card": pick_card,
    "cash_needed": cash_needed,
    "holiday_closure": holiday_closure,
    "check_layover": check_layover,
    "etiquette_card": etiquette_card,
    "tax_refund": tax_refund,
    "rebook_segment": rebook_segment,
    "incidental_hold": incidental_hold,
    "landing_data": landing_data,
}
