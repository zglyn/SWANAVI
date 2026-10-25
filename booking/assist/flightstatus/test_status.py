"""Flight status: on time, a delay, a cancellation, a bad delay, and a non-flight.

These tests stay in-process. They do not call an airline API, open a socket, or call AWS.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest

from booking.assist.flightstatus import AGENTCORE_TOOL, TOOL_SPEC, flight_status, handler
from booking.assist.flightstatus import status as status_mod
from booking.assist.flightstatus import tool as tool_mod

TRIP = "sample-kyoto"
NOW = "2026-11-02T08:00:00Z"
DEPART = "2026-11-02T16:00:00Z"


def _flight(**extra) -> dict:
    segment = {
        "segmentId": "flight-1",
        "kind": "flight",
        "from": "SFO",
        "to": "KIX",
        "departAt": DEPART,
        "confirmationCode": "SANDBOX-FLIGHT",
    }
    segment.update(extra)
    return segment


def _call(segment=None, feed=None, **extra) -> dict:
    payload = {
        "tripId": extra.pop("tripId", TRIP),
        "now": extra.pop("now", NOW),
        "segment": _flight() if segment is None else segment,
    }
    if feed is not None:
        payload["feed"] = feed
    payload.update(extra)
    return flight_status(payload)


class FlightStatusTests(unittest.TestCase):
    def test_omitted_feed_is_on_time(self) -> None:
        segment = _flight()
        before = copy.deepcopy(segment)
        result = _call(segment)

        self.assertEqual(
            result,
            {
                "segmentId": "flight-1",
                "event": "on_time",
                "delayMinutes": 0,
                "action": "none",
                "departAt": DEPART,
            },
        )
        self.assertEqual(segment, before)

        explicit = _call(feed={"event": "on_time", "delayMinutes": 15})
        self.assertEqual(explicit["event"], "on_time")
        self.assertEqual(explicit["delayMinutes"], 0)
        self.assertEqual(explicit["action"], "none")

        dated = _flight()
        del dated["departAt"]
        dated["departDate"] = "2026-11-02"
        dated["confirmationCode"] = None
        by_date = _call(dated)
        self.assertEqual(by_date["departAt"], "2026-11-02")
        self.assertEqual(by_date["event"], "on_time")
        self.assertEqual(by_date["action"], "none")

    def test_delayed_feed_asks_for_replan(self) -> None:
        segment = _flight()
        feed = {"event": "delayed", "delayMinutes": 40}
        before_segment = copy.deepcopy(segment)
        before_feed = copy.deepcopy(feed)
        result = _call(segment, feed=feed)

        self.assertEqual(
            result,
            {
                "segmentId": "flight-1",
                "event": "delayed",
                "delayMinutes": 40,
                "action": "replan",
                "departAt": DEPART,
            },
        )
        self.assertEqual(segment, before_segment)
        self.assertEqual(feed, before_feed)
        self.assertNotIn("error", result)

        named = flight_status(
            tripId=TRIP,
            now=NOW,
            segment=_flight(),
            feed={"event": " Delayed ", "delayMinutes": "25"},
        )
        self.assertEqual(named["event"], "delayed")
        self.assertEqual(named["delayMinutes"], 25)
        self.assertEqual(named["action"], "replan")
        self.assertEqual(named["departAt"], DEPART)

    def test_cancelled_feed_asks_for_replan(self) -> None:
        segment = _flight()
        plan = {"tripId": TRIP, "flights": [segment]}
        feed = {"event": "cancelled", "delayMinutes": 90}
        payload = {"tripId": TRIP, "now": NOW, "segment": segment, "feed": feed, "plan": plan}
        before = copy.deepcopy(payload)
        result = flight_status(payload)

        self.assertEqual(
            result,
            {
                "segmentId": "flight-1",
                "event": "cancelled",
                "delayMinutes": 0,
                "action": "replan",
                "departAt": DEPART,
            },
        )
        self.assertEqual(payload, before)
        self.assertEqual(feed["delayMinutes"], 90)

        bare = _call(feed={"event": "Cancelled"})
        self.assertEqual(bare["event"], "cancelled")
        self.assertEqual(bare["delayMinutes"], 0)
        self.assertEqual(bare["action"], "replan")

    def test_bad_delay_stays_on_time(self) -> None:
        cases = (
            {"event": "delayed", "delayMinutes": 0},
            {"event": "delayed", "delayMinutes": -15},
            {"event": "delayed", "delayMinutes": 0.0},
            {"event": "delayed", "delayMinutes": "0"},
            {"event": "delayed", "delayMinutes": None},
            {"event": "delayed"},
            {"event": "delayed", "delayMinutes": "nope"},
        )
        for feed in cases:
            with self.subTest(feed=feed):
                result = _call(feed=feed)
                self.assertEqual(result["event"], "on_time")
                self.assertEqual(result["action"], "none")
                self.assertEqual(result["delayMinutes"], 0)
                self.assertEqual(result["segmentId"], "flight-1")
                self.assertEqual(result["departAt"], DEPART)
                self.assertNotIn("error", result)

    def test_non_flight_segment_is_ignored(self) -> None:
        for kind in ("hotel", "attraction", "transfer", "Hotel"):
            with self.subTest(kind=kind):
                segment = {"segmentId": "stop-1", "kind": kind, "from": "Kyoto", "to": "Nara"}
                before = copy.deepcopy(segment)
                result = _call(segment, feed={"event": "cancelled", "delayMinutes": 30})
                self.assertEqual(
                    result,
                    {
                        "segmentId": "stop-1",
                        "event": "not_a_flight",
                        "delayMinutes": 0,
                        "action": "none",
                        "departAt": "",
                    },
                )
                self.assertEqual(segment, before)

    def test_missing_fields_do_not_raise(self) -> None:
        flight = _flight()
        missing_from = _flight()
        del missing_from["from"]
        missing_departure = _flight()
        del missing_departure["departAt"]
        bad_code = _flight(confirmationCode=12)
        cases = [
            None,
            "not-json",
            "{",
            [],
            {},
            {"tripId": TRIP, "now": NOW},
            {"tripId": TRIP, "now": NOW, "segment": None},
            {"now": NOW, "segment": flight},
            {"tripId": TRIP, "segment": flight},
            {"tripId": "  ", "now": NOW, "segment": flight},
            {"tripId": TRIP, "now": "2026-11-02", "segment": flight},
            {"tripId": TRIP, "now": "not-a-time", "segment": flight},
            {"tripId": TRIP, "now": NOW, "segment": missing_from},
            {"tripId": TRIP, "now": NOW, "segment": missing_departure},
            {"tripId": TRIP, "now": NOW, "segment": bad_code},
            {"tripId": TRIP, "now": NOW, "segment": _flight(), "feed": ["delayed"]},
            {"tripId": TRIP, "now": NOW, "segment": _flight(), "feed": {"event": "diverted", "delayMinutes": 10}},
        ]
        for case in cases:
            result = flight_status(case)
            self.assertEqual(result["error"], "invalid_segment")
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["delayMinutes"], 0)
            self.assertIn("segmentId", result)
            self.assertIn("departAt", result)

        self.assertEqual(flight_status()["error"], "invalid_segment")
        self.assertEqual(flight_status()["action"], "none")

    def test_tool_spec_is_flight_status(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "flight_status")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["tripId", "now", "segment"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "event", "delayMinutes", "action", "departAt"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("before it replans", description)
        self.assertIn("action to replan", description)
        self.assertIn("not_a_flight", description)
        self.assertIn("invalid_segment", description)
        self.assertIn("does not change the segment", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "flight_status")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_flight_status(self) -> None:
        payload = {
            "tripId": TRIP,
            "now": NOW,
            "segment": _flight(),
            "feed": {"event": "delayed", "delayMinutes": 40},
        }
        self.assertEqual(handler(payload), flight_status(payload))
        self.assertEqual(handler(json.dumps(payload)), flight_status(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("assist___flight_status"))
        self.assertEqual(wrapped["action"], "replan")
        self.assertEqual(wrapped["delayMinutes"], 40)

        nested = handler({"input": payload})
        self.assertEqual(nested["event"], "delayed")

        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(rejected["error"], "invalid_segment")
        self.assertEqual(rejected["action"], "none")

    def test_does_not_call_the_network_or_aws(self) -> None:
        source = inspect.getsource(status_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            ".utcnow",
            "time.time",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "httpx",
            "socket",
            "amadeus",
            "uber",
            "bedrock_agentcore",
        ):
            self.assertNotIn(banned, source.lower())
        with _network_forbidden():
            result = _call(feed={"event": "cancelled", "delayMinutes": 5})
        self.assertEqual(result["action"], "replan")
        self.assertEqual(result["delayMinutes"], 0)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("flight_status opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
