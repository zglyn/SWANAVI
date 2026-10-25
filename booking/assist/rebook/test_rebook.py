"""Same-day rebook: not cancelled, a future flight kept, a past attraction moved.

These tests stay in-process. They do not call a booker, the planner, Amadeus, or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest
from datetime import datetime, timedelta, timezone

from booking.assist.rebook import AGENTCORE_TOOL, TOOL_SPEC, handler, rebook_segment
from booking.assist.rebook import rebook as rebook_mod
from booking.assist.rebook import tool as tool_mod
from booking.assist.rebook.rebook import REASON_NOT_CANCELLED, REASON_REBOOKED, REASON_UNREADABLE

TRIP = "trip-kyoto-001"
NOW = "2026-11-06T14:10:00Z"
LATER = "2026-11-08T09:00:00Z"
TRAVELERS = [{"id": "t1", "givenName": "Ada", "familyName": "Lovelace"}]


def _flight(**overrides):
    segment = {
        "segmentId": "seg-flight-1",
        "kind": "flight",
        "from": "JFK",
        "to": "KIX",
        "departDate": "2026-11-08",
        "returnDate": "2026-11-15",
        "cabin": "economy",
        "travelerIds": ["t1"],
        "price": {"amount": "248.00", "currency": "USD"},
    }
    segment.update(overrides)
    return segment


def _hotel(**overrides):
    segment = {
        "segmentId": "seg-hotel-1",
        "kind": "hotel",
        "city": "Kyoto",
        "checkIn": "2026-11-08",
        "checkOut": "2026-11-11",
        "rooms": 1,
        "guests": 2,
    }
    segment.update(overrides)
    return segment


def _attraction(**overrides):
    segment = {
        "segmentId": "seg-fushimi-1",
        "kind": "attraction",
        "name": "Fushimi Inari Taisha",
        "city": "Kyoto",
        "date": "2026-11-06",
        "time": "09:00",
        "partySize": 2,
        "price": {"amount": "36.00", "currency": "USD"},
    }
    segment.update(overrides)
    return segment


def _call(segment, *, now=NOW, cancelled=True, travelers=None, trip_id=TRIP):
    return rebook_segment(
        tripId=trip_id,
        now=now,
        segment=segment,
        travelers=list(TRAVELERS if travelers is None else travelers),
        cancelled=cancelled,
    )


class RebookSegmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_not_cancelled_leaves_the_segment(self) -> None:
        segment = _attraction()
        result = _call(segment, cancelled=False)

        self.assertEqual(result["segmentId"], "seg-fushimi-1")
        self.assertFalse(result["changed"])
        self.assertEqual(result["reason"], REASON_NOT_CANCELLED)
        self.assertIsNone(result["replacement"])
        self.assertEqual(result["notes"], ["segment is not cancelled"])

        again = rebook_segment(
            {
                "tripId": TRIP,
                "now": NOW,
                "segment": segment,
                "travelers": TRAVELERS,
                "cancelled": False,
            }
        )
        self.assertEqual(again, result)

    def test_future_flight_is_kept(self) -> None:
        segment = _flight()
        before = copy.deepcopy(segment)
        result = _call(segment, now=NOW)

        self.assertTrue(result["changed"])
        self.assertEqual(result["reason"], REASON_REBOOKED)
        replacement = result["replacement"]
        self.assertEqual(replacement["segmentId"], "seg-flight-1")
        self.assertEqual(replacement["kind"], "flight")
        self.assertEqual(replacement["from"], "JFK")
        self.assertEqual(replacement["to"], "KIX")
        self.assertEqual(replacement["departDate"], "2026-11-08")
        self.assertEqual(replacement["returnDate"], "2026-11-15")
        self.assertEqual(replacement["cabin"], "economy")
        self.assertEqual(replacement["travelerIds"], ["t1"])
        self.assertEqual(replacement["status"], "booked")
        self.assertTrue(replacement["confirmationCode"].startswith("SANDBOX-RB-"))
        self.assertEqual(replacement["price"], {"amount": "248.00", "currency": "USD"})
        self.assertIsNone(replacement["error"])
        self.assertEqual(result["notes"], ["kept the original start"])
        self.assertEqual(segment, before)

        positional = rebook_segment(TRIP, NOW, segment, TRAVELERS, True)
        self.assertEqual(positional, result)

    def test_past_attraction_moves_30_minutes(self) -> None:
        now = datetime(2026, 11, 6, 14, 10, tzinfo=timezone.utc)
        expected = now + timedelta(minutes=30)
        segment = _attraction()
        result = _call(segment, now=now.strftime("%Y-%m-%dT%H:%M:%SZ"))

        replacement = result["replacement"]
        self.assertTrue(result["changed"])
        self.assertEqual(result["reason"], REASON_REBOOKED)
        self.assertEqual(replacement["segmentId"], "seg-fushimi-1")
        self.assertEqual(replacement["kind"], "attraction")
        self.assertEqual(replacement["name"], "Fushimi Inari Taisha")
        self.assertEqual(replacement["city"], "Kyoto")
        self.assertEqual(replacement["date"], expected.date().isoformat())
        self.assertEqual(replacement["time"], expected.strftime("%H:%M"))
        self.assertEqual(replacement["time"], "14:40")
        self.assertEqual(replacement["partySize"], 2)
        self.assertEqual(replacement["status"], "booked")
        self.assertTrue(replacement["confirmationCode"].startswith("SANDBOX-RB-"))
        self.assertEqual(replacement["price"], {"amount": "36.00", "currency": "USD"})
        self.assertIsNone(replacement["error"])
        self.assertEqual(result["notes"], ["moved the start to 2026-11-06 14:40 UTC"])

        offset = _call(segment, now="2026-11-06T23:10:00+09:00")
        self.assertEqual(offset["replacement"]["date"], replacement["date"])
        self.assertEqual(offset["replacement"]["time"], replacement["time"])
        self.assertEqual(offset["replacement"]["confirmationCode"], replacement["confirmationCode"])

    def test_confirmation_code_prefix_and_same_inputs(self) -> None:
        first = _call(_flight(), now=LATER)
        second = _call(_flight(), now=LATER)
        code = first["replacement"]["confirmationCode"]

        self.assertEqual(first, second)
        self.assertTrue(code.startswith("SANDBOX-RB-"))
        self.assertGreater(len(code), len("SANDBOX-RB-"))
        self.assertNotEqual(code, _call(_attraction())["replacement"]["confirmationCode"])

    def test_missing_price_is_null_and_cities_stay(self) -> None:
        flight = _flight()
        del flight["price"]
        booked = _call(flight, now=LATER)
        self.assertIsNone(booked["replacement"]["price"])
        self.assertEqual(booked["replacement"]["from"], "JFK")
        self.assertEqual(booked["replacement"]["to"], "KIX")

        broken = _call(_attraction(price={"amount": "36.00"}), now=NOW)
        self.assertIsNone(broken["replacement"]["price"])
        self.assertEqual(broken["replacement"]["city"], "Kyoto")

    def test_past_flight_date_follows_now_plus_30_minutes(self) -> None:
        kept_today = _call(_flight(departDate="2026-11-06", returnDate="2026-11-09"), now=NOW)
        self.assertEqual(kept_today["replacement"]["departDate"], "2026-11-06")
        self.assertEqual(kept_today["replacement"]["returnDate"], "2026-11-09")
        self.assertEqual(kept_today["replacement"]["from"], "JFK")
        self.assertIn("moved the start to 2026-11-06 14:40 UTC", kept_today["notes"])

        moved = _call(_flight(departDate="2026-11-05", returnDate="2026-11-09"), now=NOW)
        self.assertEqual(moved["replacement"]["departDate"], "2026-11-06")
        self.assertEqual(moved["replacement"]["returnDate"], "2026-11-10")
        self.assertEqual(moved["replacement"]["to"], "KIX")

    def test_hotel_keeps_a_future_stay_and_shifts_a_past_stay(self) -> None:
        future = _call(_hotel(), now=NOW)
        self.assertEqual(future["replacement"]["city"], "Kyoto")
        self.assertEqual(future["replacement"]["checkIn"], "2026-11-08")
        self.assertEqual(future["replacement"]["checkOut"], "2026-11-11")
        self.assertEqual(future["notes"], ["kept the original start"])
        self.assertTrue(future["replacement"]["confirmationCode"].startswith("SANDBOX-RB-"))

        past = _call(_hotel(checkIn="2026-11-02", checkOut="2026-11-05"), now=NOW)
        self.assertEqual(past["replacement"]["city"], "Kyoto")
        self.assertEqual(past["replacement"]["checkIn"], "2026-11-06")
        self.assertEqual(past["replacement"]["checkOut"], "2026-11-09")
        self.assertEqual(past["replacement"]["rooms"], 1)
        self.assertEqual(past["replacement"]["guests"], 2)
        self.assertIsNone(past["replacement"]["price"])

    def test_attraction_can_cross_midnight(self) -> None:
        result = _call(_attraction(time="23:00"), now="2026-11-06T23:40:00Z")
        replacement = result["replacement"]
        self.assertEqual(replacement["date"], "2026-11-07")
        self.assertEqual(replacement["time"], "00:10")
        self.assertEqual(replacement["city"], "Kyoto")
        self.assertEqual(replacement["name"], "Fushimi Inari Taisha")

    def test_partial_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            [],
            {"cancelled": True},
            {"tripId": TRIP, "now": NOW, "segment": _flight(), "travelers": TRAVELERS, "cancelled": "yes"},
            {"tripId": TRIP, "now": "tomorrow", "segment": _flight(), "travelers": TRAVELERS, "cancelled": True},
            {"tripId": TRIP, "now": NOW, "segment": {"segmentId": "x", "kind": "train"}, "travelers": [], "cancelled": True},
            {"tripId": "", "now": NOW, "segment": _flight(), "travelers": TRAVELERS, "cancelled": True},
        ]
        for case in cases:
            result = rebook_segment(case)
            self.assertEqual(
                set(result),
                {"segmentId", "changed", "reason", "replacement", "notes"},
            )
            self.assertIsInstance(result["segmentId"], str)
            self.assertIsInstance(result["changed"], bool)
            self.assertIsInstance(result["reason"], str)
            self.assertIsInstance(result["notes"], list)
            self.assertFalse(result["changed"])
            self.assertIsNone(result["replacement"])

        self.assertEqual(rebook_segment()["reason"], REASON_UNREADABLE)

    def test_tool_spec_is_rebook_segment(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "rebook_segment")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["tripId", "now", "segment", "travelers", "cancelled"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "changed", "reason", "replacement", "notes"],
        )
        self.assertIn("SANDBOX-RB-", TOOL_SPEC["description"])
        self.assertIn("does not call the planner", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "rebook_segment")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_rebook_segment(self) -> None:
        payload = {
            "tripId": TRIP,
            "now": LATER,
            "segment": _flight(),
            "travelers": TRAVELERS,
            "cancelled": True,
        }
        self.assertEqual(handler(payload), rebook_segment(payload))
        self.assertEqual(handler(json.dumps(payload)), rebook_segment(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("assist___rebook_segment"))
        self.assertTrue(wrapped["changed"])
        self.assertTrue(wrapped["replacement"]["confirmationCode"].startswith("SANDBOX-RB-"))
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(rejected["reason"], REASON_UNREADABLE)
        self.assertIsNone(rejected["replacement"])
        self.assertFalse(rejected["changed"])

    def test_does_not_call_the_planner_or_open_a_socket(self) -> None:
        source = inspect.getsource(rebook_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            "utcnow",
            "time.time",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "httpx",
            "socket",
            "booking.replan",
            "booking.master",
            "booking.providers",
            "booking.orchestrator",
            "amadeus",
            "Amadeus",
        ):
            self.assertNotIn(banned, source)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("rebook_segment opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
