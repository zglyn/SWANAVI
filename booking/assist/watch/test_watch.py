"""Early trip watch: replan, shift, ride, tight transfer, and an all-clear plan.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest

from booking.assist.watch import AGENTCORE_TOOL, TOOL_SPEC, handler, watch_trip
from booking.assist.watch import tool as tool_mod
from booking.assist.watch import watch as watch_mod
from booking.assist.watch.watch import ISSUE_REPLAN, ISSUE_RIDE, ISSUE_SHIFT, ISSUE_TRANSFER

NOW = "2026-11-03T09:00:00Z"
DAY = "2026-11-03"


def _segment(segment_id: str, start: str, end: str, **extra) -> dict:
    segment = {"segmentId": segment_id, "start": start, "end": end}
    segment.update(extra)
    return segment


def _plan(flights=(), hotels=(), attractions=()) -> dict:
    return {
        "tripId": "sample-kyoto",
        "flights": list(flights),
        "hotels": list(hotels),
        "attractions": list(attractions),
    }


def _clear_plan() -> dict:
    return _plan(
        flights=[_segment("flight-1", f"{DAY}T08:00:00Z", f"{DAY}T09:30:00Z", kind="flight")],
        hotels=[_segment("hotel-1", f"{DAY}T18:00:00Z", "2026-11-04T10:00:00Z", kind="hotel")],
        attractions=[
            _segment(
                "temple",
                f"{DAY}T11:00:00Z",
                f"{DAY}T13:00:00Z",
                kind="attraction",
                outdoor=True,
                name="Temple walk",
            ),
            _segment(
                "garden",
                f"{DAY}T14:00:00Z",
                f"{DAY}T16:00:00Z",
                kind="attraction",
                outdoor=False,
                name="Garden",
            ),
        ],
    )


def _call(plan, *, now=NOW, rides=None, signals=None) -> dict:
    return watch_trip(
        {
            "now": now,
            "plan": plan,
            "rides": [] if rides is None else rides,
            "signals": [] if signals is None else signals,
        }
    )


class WatchTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_disruption_signal_needs_replan(self) -> None:
        plan = _clear_plan()
        before = copy.deepcopy(plan)
        signals = [
            {"segmentId": "flight-1", "event": "cancelled", "condition": None, "deltaMinutes": None},
            {"segmentId": "hotel-1", "event": "Ended_Early", "condition": "", "deltaMinutes": 45},
            {"segmentId": "missing", "event": "ended_late", "condition": "clear", "deltaMinutes": 10},
        ]
        result = _call(plan, signals=signals)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["warnings"],
            [
                {
                    "segmentId": "flight-1",
                    "issue": ISSUE_REPLAN.format(event="cancelled"),
                    "severity": "act",
                    "action": "replan",
                },
                {
                    "segmentId": "hotel-1",
                    "issue": ISSUE_REPLAN.format(event="ended_early"),
                    "severity": "act",
                    "action": "replan",
                },
                {
                    "segmentId": "missing",
                    "issue": ISSUE_REPLAN.format(event="ended_late"),
                    "severity": "act",
                    "action": "replan",
                },
            ],
        )

        self.assertEqual(plan, before)
        self.assertEqual(_call(plan, signals=[{"segmentId": "flight-1", "event": "on_time"}])["warnings"], [])

    def test_outdoor_weather_before_arrival_needs_shift(self) -> None:
        plan = _clear_plan()
        before = copy.deepcopy(plan)
        for condition in ("rain", "Storm", " snow "):
            with self.subTest(condition=condition):
                result = _call(
                    plan,
                    signals=[{"segmentId": "temple", "event": "", "condition": condition, "deltaMinutes": 30}],
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["warnings"],
                    [
                        {
                            "segmentId": "temple",
                            "issue": ISSUE_SHIFT.format(condition=condition.strip().lower()),
                            "severity": "act",
                            "action": "shift",
                        }
                    ],
                )
        self.assertEqual(plan, before)

        indoor = _clear_plan()
        indoor["attractions"][0]["outdoor"] = False
        indoor["attractions"][0]["indoor"] = True
        self.assertEqual(
            _call(indoor, signals=[{"segmentId": "temple", "condition": "rain"}])["warnings"],
            [],
        )

        by_indoor_flag = _clear_plan()
        del by_indoor_flag["attractions"][0]["outdoor"]
        by_indoor_flag["attractions"][0]["indoor"] = False
        shifted = _call(by_indoor_flag, signals=[{"segmentId": "temple", "condition": "rain"}])
        self.assertEqual(shifted["warnings"][0]["action"], "shift")

        started = _call(
            plan,
            now="2026-11-03T11:00:00Z",
            signals=[{"segmentId": "temple", "condition": "rain"}],
        )
        self.assertEqual(started["warnings"], [])
        already = _call(
            plan,
            now="2026-11-03T12:00:00Z",
            signals=[{"segmentId": "temple", "condition": "snow"}],
        )
        self.assertEqual(already["warnings"], [])
        other = _call(plan, signals=[{"segmentId": "temple", "condition": "rainy"}])
        self.assertEqual(other["warnings"], [])

    def test_ending_attraction_needs_a_ride(self) -> None:
        plan = _plan(
            attractions=[
                _segment("temple", f"{DAY}T12:00:00Z", f"{DAY}T14:00:00Z", kind="attraction"),
                _segment("garden", f"{DAY}T15:00:00Z", f"{DAY}T16:30:00Z", kind="attraction"),
            ]
        )
        soon = _call(plan, now="2026-11-03T13:50:00Z")
        exactly = _call(plan, now="2026-11-03T13:40:00Z")
        at_end = _call(plan, now="2026-11-03T14:00:00Z")
        expected = [
            {
                "segmentId": "temple",
                "issue": ISSUE_RIDE,
                "severity": "act",
                "action": "request_ride",
            }
        ]
        self.assertEqual(soon["warnings"], expected)
        self.assertFalse(soon["ok"])
        self.assertEqual(exactly["warnings"], expected)
        self.assertEqual(at_end["warnings"], expected)

        too_early = _call(plan, now="2026-11-03T13:39:00Z")
        self.assertEqual(too_early, {"ok": True, "warnings": []})
        after = _call(plan, now="2026-11-03T14:01:00Z")
        self.assertEqual(after["warnings"], [])

        requested = _call(
            plan,
            now="2026-11-03T13:50:00Z",
            rides=[{"fromSegmentId": "temple", "status": "Requested"}],
        )
        self.assertEqual(requested, {"ok": True, "warnings": []})

        other_status = _call(
            plan,
            now="2026-11-03T13:50:00Z",
            rides=[{"fromSegmentId": "temple", "status": "completed"}],
        )
        self.assertEqual(other_status["warnings"], expected)

        rides = [{"fromSegmentId": "temple", "status": "completed"}]
        before_rides = copy.deepcopy(rides)
        _call(plan, now="2026-11-03T13:50:00Z", rides=rides)
        self.assertEqual(rides, before_rides)

        next_day = _plan(
            attractions=[
                _segment("temple", f"{DAY}T22:00:00Z", f"{DAY}T23:50:00Z", kind="attraction"),
                _segment("breakfast", "2026-11-04T08:00:00Z", "2026-11-04T09:00:00Z", kind="attraction"),
            ]
        )
        self.assertEqual(_call(next_day, now="2026-11-03T23:40:00Z")["warnings"], [])

    def test_tight_transfer_needs_a_check(self) -> None:
        def pair(next_start: str) -> dict:
            return _plan(
                attractions=[
                    _segment("temple", f"{DAY}T10:00:00Z", f"{DAY}T12:00:00Z", kind="attraction"),
                    _segment("garden", next_start, f"{DAY}T16:00:00Z", kind="attraction"),
                ]
            )

        under = _call(pair(f"{DAY}T12:29:00Z"), now="2026-11-03T08:00:00Z")
        self.assertEqual(
            under["warnings"],
            [
                {
                    "segmentId": "temple",
                    "issue": ISSUE_TRANSFER.format(next_id="garden"),
                    "severity": "act",
                    "action": "check_transfer",
                }
            ],
        )
        self.assertFalse(under["ok"])

        touching = _call(pair(f"{DAY}T12:00:00Z"), now="2026-11-03T08:00:00Z")
        self.assertEqual(touching["warnings"][0]["action"], "check_transfer")

        exact = _call(pair(f"{DAY}T12:30:00Z"), now="2026-11-03T08:00:00Z")
        self.assertEqual(exact, {"ok": True, "warnings": []})

        overlap = _plan(
            hotels=[_segment("hotel-1", f"{DAY}T08:00:00Z", "2026-11-06T11:00:00Z", kind="hotel")],
            attractions=[_segment("temple", f"{DAY}T10:00:00Z", f"{DAY}T12:00:00Z", kind="attraction")],
        )
        self.assertEqual(_call(overlap, now="2026-11-03T08:00:00Z"), {"ok": True, "warnings": []})

        removed = pair(f"{DAY}T12:10:00Z")
        removed["attractions"][0]["removed"] = True
        self.assertEqual(_call(removed, now="2026-11-03T08:00:00Z")["warnings"], [])

    def test_all_clear_plan(self) -> None:
        plan = _clear_plan()
        before = copy.deepcopy(plan)
        result = watch_trip(
            NOW,
            plan,
            [{"fromSegmentId": "garden", "status": "requested"}],
            [{"segmentId": "temple", "event": "on_time", "condition": "clear", "deltaMinutes": 0}],
        )

        self.assertEqual(result, {"ok": True, "warnings": []})
        self.assertEqual(plan, before)

    def test_stacked_warnings_leave_the_plan_in_place(self) -> None:
        plan = _plan(
            flights=[_segment("flight-1", f"{DAY}T08:00:00Z", f"{DAY}T09:00:00Z", kind="flight")],
            hotels=[_segment("hotel-1", f"{DAY}T18:00:00Z", "2026-11-04T10:00:00Z", kind="hotel")],
            attractions=[
                _segment("temple", f"{DAY}T14:00:00Z", f"{DAY}T14:10:00Z", kind="attraction", outdoor=True),
                _segment("garden", f"{DAY}T14:25:00Z", f"{DAY}T15:30:00Z", kind="attraction"),
            ],
        )
        before = copy.deepcopy(plan)
        result = _call(
            plan,
            now="2026-11-03T13:50:00Z",
            signals=[
                {"segmentId": "flight-1", "event": "cancelled", "condition": None, "deltaMinutes": None},
                {"segmentId": "temple", "event": None, "condition": "rain", "deltaMinutes": 15},
            ],
        )

        self.assertEqual(
            [(item["segmentId"], item["action"]) for item in result["warnings"]],
            [
                ("flight-1", "replan"),
                ("temple", "shift"),
                ("temple", "request_ride"),
                ("temple", "check_transfer"),
            ],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(plan, before)
        self.assertNotIn("plan", result)

    def test_partial_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            [],
            {"now": None, "plan": None, "rides": None, "signals": None},
            {"plan": {"flights": [None, "x", {}]}, "now": "not-a-time", "rides": "nope", "signals": {}},
            {"flights": [{"segmentId": "flight-1"}]},
            {"now": NOW, "plan": {"hotels": "nope", "attractions": None}, "rides": [None], "signals": [None]},
        ]
        for case in cases:
            result = watch_trip(case)
            self.assertEqual(set(result), {"ok", "warnings"})
            self.assertIsInstance(result["ok"], bool)
            self.assertIsInstance(result["warnings"], list)
            for warning in result["warnings"]:
                self.assertEqual(set(warning), {"segmentId", "issue", "severity", "action"})
                self.assertIn(warning["severity"], {"watch", "act"})
                self.assertIn(warning["action"], {"replan", "shift", "request_ride", "check_transfer"})

        self.assertEqual(watch_trip(), {"ok": True, "warnings": []})

    def test_tool_spec_is_watch_trip(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "watch_trip")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["now", "plan", "rides", "signals"])
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["ok", "warnings"])
        warning = TOOL_SPEC["outputSchema"]["properties"]["warnings"]["items"]
        self.assertEqual(warning["required"], ["segmentId", "issue", "severity", "action"])
        self.assertEqual(warning["properties"]["severity"]["enum"], ["watch", "act"])
        self.assertEqual(
            warning["properties"]["action"]["enum"],
            ["replan", "shift", "request_ride", "check_transfer"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("first on every tick", TOOL_SPEC["description"])
        self.assertIn("does not move the plan", TOOL_SPEC["description"])
        self.assertIn("does not request a ride", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "watch_trip")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_watch_trip(self) -> None:
        payload = {
            "now": NOW,
            "plan": _clear_plan(),
            "rides": [],
            "signals": [{"segmentId": "flight-1", "event": "cancelled"}],
        }
        self.assertEqual(handler(payload), watch_trip(payload))
        self.assertEqual(handler(json.dumps(payload)), watch_trip(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("assist___watch_trip"))
        self.assertEqual(wrapped["warnings"][0]["action"], "replan")
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(rejected, {"ok": True, "warnings": []})

    def test_does_not_read_the_wall_clock_or_aws(self) -> None:
        source = inspect.getsource(watch_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            ".utcnow",
            "time.time",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "bedrock_agentcore",
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
            raise AssertionError("watch_trip opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
