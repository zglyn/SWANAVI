"""Trip progress: on track, rebook, unverified email, and a finished trip.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.progress import AGENTCORE_TOOL, TOOL_SPEC, handler, trip_progress
from booking.progress import progress as progress_mod
from booking.progress.progress import ISSUE_CANCELLED, ISSUE_EMAIL, ISSUE_ENDED_EARLY, ISSUE_ENDED_LATE, ISSUE_REBOOK

PLAN = {
    "tripId": "sample-kyoto",
    "travelers": [{"id": "t1", "name": "Sample Traveler"}],
    "destination": {"city": "Kyoto", "country": "JP"},
    "dates": {"start": "2026-11-02", "end": "2026-11-06"},
    "flights": [
        {
            "segmentId": "flight-1",
            "kind": "flight",
            "from": "SFO",
            "to": "KIX",
            "departDate": "2026-11-02",
            "returnDate": "2026-11-06",
            "cabin": "economy",
            "travelerIds": ["t1"],
        }
    ],
    "hotels": [
        {
            "segmentId": "hotel-1",
            "kind": "hotel",
            "city": "Kyoto",
            "checkIn": "2026-11-02",
            "checkOut": "2026-11-06",
            "rooms": 1,
            "guests": 1,
        }
    ],
    "attractions": [
        {
            "segmentId": "attraction-1",
            "kind": "attraction",
            "name": "Sample temple visit",
            "city": "Kyoto",
            "date": "2026-11-03",
            "partySize": 1,
            "time": "09:00",
        }
    ],
}

DURING = "2026-11-03T08:00:00Z"
BEFORE = "2026-11-01T12:00:00Z"
ATTRACTION_OVERDUE = "2026-11-03T10:00:00Z"
ATTRACTION_EXACTLY_45 = "2026-11-03T09:45:00Z"
AFTER = "2026-11-08T00:00:00Z"


def _booking(segment_id: str, kind: str, *, status: str = "booked", email_verified: bool = True) -> dict:
    return {
        "segmentId": segment_id,
        "kind": kind,
        "status": status,
        "confirmationCode": f"SANDBOX-{segment_id}",
        "emailVerified": email_verified,
    }


def _booked_results(**overrides: dict) -> list:
    results = [
        _booking("flight-1", "flight"),
        _booking("hotel-1", "hotel"),
        _booking("attraction-1", "attraction"),
    ]
    by_id = {item["segmentId"]: item for item in results}
    for segment_id, fields in overrides.items():
        by_id[segment_id].update(fields)
    return results


class TripProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_on_track_plan(self) -> None:
        during = trip_progress(PLAN, _booked_results(), DURING)
        before = trip_progress({"plan": PLAN, "results": _booked_results(), "now": BEFORE})

        self.assertEqual(during["phase"], "in_progress")
        self.assertTrue(during["onTrack"])
        self.assertEqual(during["updates"], [])
        self.assertEqual(before["phase"], "pre_trip")
        self.assertTrue(before["onTrack"])
        self.assertEqual(before["updates"], [])

    def test_segment_that_finished_early_needs_rebook(self) -> None:
        result = trip_progress(PLAN, _booked_results(), ATTRACTION_OVERDUE)

        self.assertEqual(result["phase"], "in_progress")
        self.assertFalse(result["onTrack"])
        self.assertEqual(
            result["updates"],
            [
                {
                    "segmentId": "attraction-1",
                    "kind": "attraction",
                    "issue": ISSUE_REBOOK,
                    "action": "rebook",
                }
            ],
        )

        still_inside_grace = trip_progress(PLAN, _booked_results(), ATTRACTION_EXACTLY_45)
        self.assertTrue(still_inside_grace["onTrack"])
        self.assertEqual(still_inside_grace["updates"], [])

    def test_unverified_booking_needs_verify_email(self) -> None:
        results = _booked_results(**{"hotel-1": {"emailVerified": False}})
        result = handler({"plan": PLAN, "results": results, "now": DURING})

        self.assertEqual(result["phase"], "in_progress")
        self.assertTrue(result["onTrack"])
        self.assertEqual(
            result["updates"],
            [
                {
                    "segmentId": "hotel-1",
                    "kind": "hotel",
                    "issue": ISSUE_EMAIL,
                    "action": "verify_email",
                }
            ],
        )

    def test_trip_done(self) -> None:
        results = [
            _booking("flight-1", "flight", status="finished"),
            _booking("hotel-1", "hotel", status="finished"),
            _booking("attraction-1", "attraction", status="finished"),
        ]
        result = trip_progress(PLAN, results, AFTER)

        self.assertEqual(result, {"phase": "done", "onTrack": True, "updates": []})

    def test_partial_plan_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"plan": None, "results": None, "now": None},
            {"plan": {"flights": [{}]}, "results": "nope", "now": "not-a-time"},
            {"plan": {"hotels": [{"kind": "hotel"}]}, "results": [{}], "now": DURING},
            {"flights": [{"segmentId": "flight-1", "kind": "flight"}]},
        ]
        for case in cases:
            result = trip_progress(case)
            self.assertEqual(set(result), {"phase", "onTrack", "updates"})
            self.assertIn(result["phase"], {"pre_trip", "in_progress", "done"})
            self.assertIsInstance(result["onTrack"], bool)
            self.assertIsInstance(result["updates"], list)
            for update in result["updates"]:
                self.assertIn(update["action"], {"none", "rebook", "verify_email", "replan"})

    def test_tool_spec_is_trip_progress(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "trip_progress")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["plan", "results", "now"])
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["phase"]["enum"], ["pre_trip", "in_progress", "done"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["updates"]["items"]["properties"]["action"]["enum"],
            ["none", "rebook", "verify_email", "replan"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("does not run that loop", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "trip_progress")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_trip_progress(self) -> None:
        payload = {"plan": PLAN, "results": _booked_results(), "now": DURING}
        self.assertEqual(handler(payload), trip_progress(PLAN, _booked_results(), DURING))

    def test_cancelled_signal_needs_replan(self) -> None:
        result = trip_progress(
            PLAN,
            _booked_results(),
            DURING,
            signals=[{"segmentId": "flight-1", "event": "cancelled", "deltaMinutes": 0}],
        )

        self.assertEqual(result["phase"], "in_progress")
        self.assertTrue(result["onTrack"])
        self.assertEqual(
            result["updates"],
            [
                {
                    "segmentId": "flight-1",
                    "kind": "flight",
                    "issue": ISSUE_CANCELLED,
                    "event": "cancelled",
                    "deltaMinutes": 0,
                    "action": "replan",
                }
            ],
        )

    def test_ended_early_signal_needs_replan(self) -> None:
        result = handler(
            {
                "plan": PLAN,
                "results": _booked_results(),
                "now": DURING,
                "signals": [{"segmentId": "hotel-1", "event": "ended_early", "deltaMinutes": 30}],
            }
        )

        self.assertTrue(result["onTrack"])
        self.assertEqual(
            result["updates"],
            [
                {
                    "segmentId": "hotel-1",
                    "kind": "hotel",
                    "issue": ISSUE_ENDED_EARLY,
                    "event": "ended_early",
                    "deltaMinutes": 30,
                    "action": "replan",
                }
            ],
        )

    def test_ended_late_signal_needs_replan(self) -> None:
        result = trip_progress(
            PLAN,
            _booked_results(),
            DURING,
            [{"segmentId": "attraction-1", "event": "ended_late", "deltaMinutes": 15}],
        )

        self.assertTrue(result["onTrack"])
        self.assertEqual(
            result["updates"],
            [
                {
                    "segmentId": "attraction-1",
                    "kind": "attraction",
                    "issue": ISSUE_ENDED_LATE,
                    "event": "ended_late",
                    "deltaMinutes": 15,
                    "action": "replan",
                }
            ],
        )

    def test_clock_rule_stays_rebook_beside_a_signal(self) -> None:
        result = trip_progress(
            PLAN,
            _booked_results(),
            ATTRACTION_OVERDUE,
            signals=[{"segmentId": "flight-1", "event": "cancelled", "deltaMinutes": 10}],
        )

        self.assertFalse(result["onTrack"])
        self.assertEqual(result["updates"][0]["action"], "rebook")
        self.assertEqual(result["updates"][0]["segmentId"], "attraction-1")
        self.assertNotIn("event", result["updates"][0])
        self.assertEqual(result["updates"][1]["action"], "replan")
        self.assertEqual(result["updates"][1]["event"], "cancelled")

    def test_does_not_read_the_wall_clock(self) -> None:
        source = inspect.getsource(progress_mod)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn(".utcnow", source)
        self.assertNotIn("time.time", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("trip_progress opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
