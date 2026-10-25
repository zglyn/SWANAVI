"""Cancellation replanning: pull the day forward, leave a started segment, ignore an unknown id.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.replan.cancel import AGENTCORE_TOOL, TOOL_SPEC, handler, replan_cancel
from booking.replan.cancel import cancel as cancel_mod
from booking.replan.cancel.cancel import NOTE_NOT_FOUND, NOTE_REMOVED, NOTE_SHIFTED, NOTE_STARTED
from booking.replan.cancel import tool as tool_mod

NOW = "2026-11-03T08:00:00Z"
DURING_GARDEN = "2026-11-03T15:30:00Z"


def _attraction(segment_id: str, time: str, *, date: str = "2026-11-03", name: str | None = None) -> dict:
    return {
        "segmentId": segment_id,
        "kind": "attraction",
        "name": name or segment_id,
        "city": "Kyoto",
        "date": date,
        "time": time,
        "partySize": 1,
    }


def _plan() -> dict:
    return {
        "tripId": "sample-kyoto",
        "travelers": [{"id": "t1", "name": "Sample Traveler"}],
        "flights": [
            {
                "segmentId": "flight-evening",
                "kind": "flight",
                "from": "KIX",
                "to": "ITM",
                "departDate": "2026-11-03",
                "cabin": "economy",
                "travelerIds": ["t1"],
                "start": "2026-11-03T16:00:00Z",
                "end": "2026-11-03T17:00:00Z",
            }
        ],
        "hotels": [],
        "attractions": [
            _attraction("market", "09:00"),
            _attraction("temple", "12:00", name="Temple"),
            _attraction("garden", "15:00", name="Garden"),
            _attraction("museum", "10:00", date="2026-11-04", name="Museum"),
        ],
    }


def _cancel(segment_id: str, kind: str = "attraction", **extra) -> dict:
    disruption = {
        "segmentId": segment_id,
        "kind": kind,
        "event": "cancelled",
        "deltaMinutes": None,
    }
    disruption.update(extra)
    return disruption


def _call(plan=None, disruption=None, now: str = NOW, trip_id: str = "sample-kyoto"):
    return replan_cancel(trip_id, now, _plan() if plan is None else plan, disruption)


class CancelReplanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_midday_attraction_cancel_pulls_the_next_same_day_item_forward(self) -> None:
        original = _plan()
        result = _call(original, _cancel("temple", deltaMinutes=15))

        self.assertEqual(result["segmentId"], "temple")
        self.assertEqual(result["event"], "cancelled")
        self.assertTrue(result["changed"])
        self.assertEqual(original, _plan())

        attractions = result["plan"]["attractions"]
        temple, market, garden, museum = attractions[1], attractions[0], attractions[2], attractions[3]
        self.assertTrue(temple["removed"])
        self.assertEqual(temple["time"], "12:00")
        self.assertNotIn("removed", market)
        self.assertEqual(market["time"], "09:00")
        self.assertNotIn("start", market)
        self.assertEqual(garden["time"], "13:00")
        self.assertEqual(garden["date"], "2026-11-03")
        self.assertEqual(garden["start"], "2026-11-03T13:00:00Z")
        self.assertEqual(garden["end"], "2026-11-03T15:00:00Z")
        self.assertEqual(museum["time"], "10:00")
        self.assertEqual(museum["date"], "2026-11-04")
        self.assertNotIn("start", museum)

        flight = result["plan"]["flights"][0]
        self.assertEqual(flight["start"], "2026-11-03T14:00:00Z")
        self.assertEqual(flight["end"], "2026-11-03T15:00:00Z")
        self.assertEqual(flight["departDate"], "2026-11-03")

        self.assertIn(NOTE_REMOVED.format(segment_id="temple"), result["notes"])
        self.assertIn(NOTE_SHIFTED.format(segment_id="garden", minutes="120"), result["notes"])
        self.assertIn(NOTE_SHIFTED.format(segment_id="flight-evening", minutes="120"), result["notes"])

    def test_segment_already_started_does_not_move(self) -> None:
        plan = _plan()
        plan["attractions"].append(_attraction("evening", "18:00"))
        plan["attractions"].append(_attraction("on-the-dot", "15:30"))
        result = _call(plan, _cancel("temple"), now=DURING_GARDEN)

        by_id = {item["segmentId"]: item for item in result["plan"]["attractions"]}
        self.assertTrue(result["changed"])
        self.assertTrue(by_id["temple"]["removed"])
        self.assertEqual(by_id["temple"]["time"], "12:00")
        self.assertEqual(by_id["garden"]["time"], "15:00")
        self.assertNotIn("start", by_id["garden"])
        self.assertEqual(by_id["evening"]["time"], "16:00")
        self.assertEqual(by_id["evening"]["start"], "2026-11-03T16:00:00Z")
        self.assertEqual(by_id["on-the-dot"]["time"], "13:30")
        self.assertIn(NOTE_STARTED.format(segment_id="garden"), result["notes"])
        self.assertNotIn(NOTE_SHIFTED.format(segment_id="garden", minutes="120"), result["notes"])

    def test_unknown_segment_id_does_not_raise(self) -> None:
        original = _plan()
        result = _call(original, _cancel("no-such-segment"))

        self.assertFalse(result["changed"])
        self.assertEqual(result["event"], "cancelled")
        self.assertEqual(result["segmentId"], "no-such-segment")
        self.assertEqual(result["notes"], [NOTE_NOT_FOUND.format(segment_id="no-such-segment")])
        self.assertEqual(result["plan"]["attractions"], original["attractions"])
        self.assertNotIn("removed", result["plan"]["attractions"][1])

    def test_shift_uses_explicit_duration(self) -> None:
        plan = {
            "tripId": "sample-kyoto",
            "attractions": [
                {
                    **_attraction("temple", "12:00"),
                    "start": "2026-11-03T12:00:00Z",
                    "end": "2026-11-03T13:30:00Z",
                },
                _attraction("garden", "15:00"),
            ],
        }
        result = _call(plan, _cancel("temple"))
        garden = result["plan"]["attractions"][1]
        self.assertEqual(garden["time"], "13:30")
        self.assertIn(NOTE_SHIFTED.format(segment_id="garden", minutes="90"), result["notes"])

    def test_flight_default_is_three_hours_from_nine_and_ignores_return(self) -> None:
        plan = {
            "tripId": "sample-kyoto",
            "flights": [
                {
                    "segmentId": "flight-1",
                    "kind": "flight",
                    "from": "SFO",
                    "to": "KIX",
                    "departDate": "2026-11-03",
                    "returnDate": "2026-11-06",
                    "cabin": "economy",
                    "travelerIds": ["t1"],
                }
            ],
            "attractions": [
                _attraction("after", "13:00"),
                _attraction("return-day", "10:00", date="2026-11-06"),
            ],
        }
        result = _call(plan, _cancel("flight-1", "flight"))
        by_id = {item["segmentId"]: item for item in result["plan"]["attractions"]}
        self.assertTrue(result["plan"]["flights"][0]["removed"])
        self.assertEqual(by_id["after"]["time"], "10:00")
        self.assertEqual(by_id["after"]["start"], "2026-11-03T10:00:00Z")
        self.assertEqual(by_id["return-day"]["time"], "10:00")
        self.assertEqual(by_id["return-day"]["date"], "2026-11-06")
        self.assertIn(NOTE_SHIFTED.format(segment_id="after", minutes="180"), result["notes"])

    def test_hotel_default_runs_from_check_in_to_check_out(self) -> None:
        plan = {
            "tripId": "sample-kyoto",
            "hotels": [
                {
                    "segmentId": "hotel-1",
                    "kind": "hotel",
                    "city": "Kyoto",
                    "checkIn": "2026-11-03",
                    "checkOut": "2026-11-04",
                    "rooms": 1,
                    "guests": 1,
                }
            ],
            "attractions": [
                _attraction("before", "10:00"),
                _attraction("night", "18:00"),
                _attraction("next", "12:00", date="2026-11-04"),
            ],
        }
        result = _call(plan, _cancel("hotel-1", "hotel"))
        by_id = {item["segmentId"]: item for item in result["plan"]["attractions"]}
        self.assertTrue(result["plan"]["hotels"][0]["removed"])
        self.assertEqual(result["plan"]["hotels"][0]["checkIn"], "2026-11-03")
        self.assertEqual(by_id["before"]["time"], "10:00")
        self.assertNotIn("start", by_id["before"])
        self.assertEqual(by_id["night"]["date"], "2026-11-02")
        self.assertEqual(by_id["night"]["time"], "22:00")
        self.assertEqual(by_id["night"]["start"], "2026-11-02T22:00:00Z")
        self.assertEqual(by_id["next"]["date"], "2026-11-04")
        self.assertEqual(by_id["next"]["time"], "12:00")

    def test_attraction_without_time_defaults_to_ten_for_two_hours(self) -> None:
        untitled = _attraction("temple", "10:00")
        del untitled["time"]
        plan = {"tripId": "sample-kyoto", "attractions": [untitled, _attraction("garden", "14:00")]}
        result = _call(plan, _cancel("temple"))
        garden = result["plan"]["attractions"][1]
        self.assertEqual(garden["time"], "12:00")
        self.assertIn(NOTE_SHIFTED.format(segment_id="garden", minutes="120"), result["notes"])

    def test_partial_plan_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"plan": None, "disruption": None, "now": None},
            {
                "tripId": "t",
                "now": "not-a-time",
                "plan": {"flights": [{}]},
                "disruption": {
                    "segmentId": "flight-1",
                    "kind": "flight",
                    "event": "cancelled",
                    "deltaMinutes": None,
                },
            },
            {
                "tripId": "t",
                "now": NOW,
                "plan": {"hotels": [{"kind": "hotel"}]},
                "disruption": {"event": "cancelled"},
            },
            {
                "tripId": "t",
                "now": NOW,
                "plan": {"attractions": None, "flights": "nope"},
                "disruption": _cancel("temple"),
            },
            {"flights": [{"segmentId": "flight-1", "kind": "flight"}]},
            {
                "tripId": "t",
                "now": NOW,
                "plan": _plan(),
                "disruption": {
                    "segmentId": "temple",
                    "kind": "attraction",
                    "event": "late",
                    "deltaMinutes": 20,
                },
            },
        ]
        for case in cases:
            result = replan_cancel(case)
            self.assertEqual(set(result), {"segmentId", "event", "changed", "plan", "notes"})
            self.assertEqual(result["event"], "cancelled")
            self.assertIsInstance(result["changed"], bool)
            self.assertIsInstance(result["plan"], dict)
            self.assertIsInstance(result["notes"], list)
            self.assertTrue(all(isinstance(note, str) and note for note in result["notes"]))

    def test_unreadable_now_marks_removed_and_does_not_shift(self) -> None:
        result = _call(_plan(), _cancel("temple"), now="not-a-time")
        garden = result["plan"]["attractions"][2]
        self.assertTrue(result["changed"])
        self.assertTrue(result["plan"]["attractions"][1]["removed"])
        self.assertEqual(garden["time"], "15:00")
        self.assertNotIn("start", garden)

    def test_tool_spec_is_replan_cancel(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "replan_cancel")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["tripId", "now", "plan", "disruption"])
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["event"]["enum"], ["cancelled"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "event", "changed", "plan", "notes"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("does not run that loop", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "replan_cancel")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_replan_cancel(self) -> None:
        payload = {
            "tripId": "sample-kyoto",
            "now": NOW,
            "plan": _plan(),
            "disruption": _cancel("temple"),
        }
        self.assertEqual(handler(payload), replan_cancel(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___replan_cancel"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), replan_cancel(payload))

    def test_sandbox_sources_do_not_touch_network_or_clock(self) -> None:
        for module in (cancel_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("datetime.now", source)
            self.assertNotIn("utcnow", source)
            self.assertNotIn("time.time", source)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("replan_cancel opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
