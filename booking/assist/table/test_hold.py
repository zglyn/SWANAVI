"""Dinner table hold: on time, twenty minutes late, and a missing time.

These tests stay in-process. They do not call OpenTable, AWS, or the network.
"""

from __future__ import annotations

import inspect
import socket
import unittest
from datetime import datetime, timedelta, timezone

from booking.assist.table import AGENTCORE_TOOL, TOOL_SPEC, handler, hold_table
from booking.assist.table import hold as hold_mod
from booking.assist.table import tool as tool_mod
from booking.assist.table.hold import REASON_HELD, REASON_MISSING, REASON_ON_TIME

SEGMENT = "dinner-1"
VENUE = "Kikunoi"
PARTY = 2
RESERVATION = "2026-11-03T19:00:00Z"
EARLY = "2026-11-03T18:40:00Z"
LATE = "2026-11-03T19:20:00Z"


def _meal(**overrides) -> dict:
    payload = {
        "segmentId": SEGMENT,
        "venue": VENUE,
        "reservationAt": RESERVATION,
        "arriveAt": EARLY,
        "partySize": PARTY,
    }
    payload.update(overrides)
    return payload


def _parse(iso: str) -> datetime:
    text = iso[:-1] + "+00:00" if iso.endswith(("Z", "z")) else iso
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class HoldTableTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_on_time(self) -> None:
        early = hold_table(_meal())
        self.assertEqual(
            early,
            {
                "segmentId": SEGMENT,
                "status": "on_time",
                "heldUntil": RESERVATION,
                "reason": REASON_ON_TIME,
            },
        )

        same = hold_table(_meal(arriveAt=RESERVATION))
        self.assertEqual(same["status"], "on_time")
        self.assertEqual(same["heldUntil"], RESERVATION)

        zoned = hold_table(
            _meal(
                reservationAt="2026-11-03T12:00:00Z",
                arriveAt="2026-11-03T20:00:00+09:00",
            )
        )
        self.assertLess(_parse("2026-11-03T20:00:00+09:00"), _parse("2026-11-03T12:00:00Z"))
        self.assertEqual(zoned["status"], "on_time")
        self.assertEqual(zoned["heldUntil"], "2026-11-03T12:00:00Z")

        echoed = "2026-11-03T19:00:00+09:00"
        local = hold_table(_meal(reservationAt=echoed, arriveAt="2026-11-03T18:00:00+09:00"))
        self.assertEqual(local["status"], "on_time")
        self.assertEqual(local["heldUntil"], echoed)

        keywords = hold_table(
            segmentId=SEGMENT,
            venue=VENUE,
            reservationAt=RESERVATION,
            arriveAt=EARLY,
            partySize=PARTY,
        )
        self.assertEqual(keywords["status"], "on_time")
        self.assertEqual(keywords["heldUntil"], RESERVATION)

    def test_twenty_minutes_late_holds_until_arrive_at_plus_15(self) -> None:
        result = hold_table(_meal(arriveAt=LATE))

        arrive = _parse(LATE)
        reservation = _parse(RESERVATION)
        self.assertEqual(arrive - reservation, timedelta(minutes=20))
        self.assertEqual(result["segmentId"], SEGMENT)
        self.assertEqual(result["status"], "held")
        self.assertEqual(result["reason"], REASON_HELD)
        self.assertEqual(result["heldUntil"], "2026-11-03T19:35:00Z")
        self.assertEqual(_parse(result["heldUntil"]) - arrive, timedelta(minutes=15))

        offset = hold_table(
            _meal(
                reservationAt="2026-11-03T19:00:00+09:00",
                arriveAt="2026-11-03T10:20:00Z",
            )
        )
        self.assertEqual(
            _parse("2026-11-03T10:20:00Z") - _parse("2026-11-03T19:00:00+09:00"),
            timedelta(minutes=20),
        )
        self.assertEqual(offset["status"], "held")
        self.assertEqual(offset["heldUntil"], "2026-11-03T10:35:00Z")
        self.assertEqual(_parse(offset["heldUntil"]) - _parse("2026-11-03T10:20:00Z"), timedelta(minutes=15))

    def test_missing_time_fails(self) -> None:
        cases = [
            {"segmentId": SEGMENT, "venue": VENUE, "partySize": PARTY},
            {"segmentId": SEGMENT, "venue": VENUE, "arriveAt": LATE, "partySize": PARTY},
            {"segmentId": SEGMENT, "venue": VENUE, "reservationAt": RESERVATION, "partySize": PARTY},
            _meal(reservationAt=""),
            _meal(arriveAt="   "),
            _meal(reservationAt=None, arriveAt=None),
            _meal(reservationAt=None),
            _meal(arriveAt=None),
        ]
        for case in cases:
            result = hold_table(case)
            self.assertEqual(set(result), {"segmentId", "status", "heldUntil", "reason"})
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["heldUntil"])
            self.assertEqual(result["reason"], REASON_MISSING)
            self.assertEqual(result["segmentId"], SEGMENT)

        unreadable = hold_table(_meal(reservationAt="tomorrow", arriveAt=LATE))
        self.assertEqual(unreadable["status"], "failed")
        self.assertIsNone(unreadable["heldUntil"])
        self.assertNotEqual(unreadable["status"], "held")

    def test_bad_input_does_not_raise(self) -> None:
        cases = [None, "", "not json", "{", [], 3, {"partySize": "two"}, {"arriveAt": 15}]
        for case in cases:
            result = hold_table(case)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["heldUntil"])
            self.assertIsInstance(result["segmentId"], str)
            self.assertIsInstance(result["reason"], str)

        wrapped = hold_table(
            {
                "arguments": _meal(arriveAt=LATE),
            }
        )
        self.assertEqual(wrapped["status"], "held")
        self.assertEqual(wrapped["heldUntil"], "2026-11-03T19:35:00Z")

    def test_tool_spec_is_hold_table(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "hold_table")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "venue", "reservationAt", "arriveAt", "partySize"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"],
            ["on_time", "held", "failed"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "status", "heldUntil", "reason"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("AgentCore", description)
        self.assertIn("late to a meal", description)
        self.assertIn("15 minutes", description)
        self.assertIn("OpenTable", description)
        self.assertIn("no network", description)
        self.assertIn("no AWS", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "hold_table")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_hold_table(self) -> None:
        payload = _meal(arriveAt=LATE)
        self.assertEqual(handler(payload), hold_table(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "table___hold_table"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), hold_table(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "table___book_ride"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["status"], "failed")
        self.assertIsNone(ignored["heldUntil"])
        self.assertIn("hold_table", ignored["reason"])

    def test_sandbox_sources_do_not_touch_network_or_aws(self) -> None:
        for module in (hold_mod, tool_mod):
            source = inspect.getsource(module)
            lowered = source.lower()
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("httpx", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("subprocess", source)
            self.assertNotIn("datetime.now", source)
            self.assertNotIn("api.opentable", lowered)
            self.assertNotIn("import aws", lowered)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("hold_table opened a connection")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
