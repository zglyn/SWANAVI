"""Opening hours: inside the window, closed Sunday, end after close.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest

from booking.assist.hours import AGENTCORE_TOOL, TOOL_SPEC, check_hours, handler
from booking.assist.hours import hours as hours_mod
from booking.assist.hours import tool as tool_mod

# 2026-10-26 is Monday. 2026-10-25 is Sunday.
MONDAY = "2026-10-26"
SUNDAY = "2026-10-25"


def _stop(**extra) -> dict:
    payload = {
        "segmentId": "attraction-1",
        "start": f"{MONDAY}T10:00:00",
        "end": f"{MONDAY}T11:00:00",
        "open": "09:00",
        "close": "17:00",
        "closedWeekdays": [6],
    }
    payload.update(extra)
    return payload


class HoursTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_inside_hours_is_ok(self) -> None:
        payload = _stop()
        original = copy.deepcopy(payload)
        result = check_hours(payload)

        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "ok": True,
                "reason": "within opening hours",
            },
        )
        self.assertEqual(payload, original)
        self.assertTrue(check_hours(**payload)["ok"])
        self.assertTrue(check_hours(json.dumps(payload))["ok"])

    def test_sunday_closed_is_not_ok(self) -> None:
        result = check_hours(
            _stop(
                start=f"{SUNDAY}T10:00:00",
                end=f"{SUNDAY}T11:00:00",
            )
        )
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "ok": False,
                "reason": "closed on Sunday",
            },
        )

    def test_ends_after_close_is_not_ok(self) -> None:
        result = check_hours(_stop(end=f"{MONDAY}T18:00:00"))
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "ok": False,
                "reason": "ends after closing",
            },
        )

    def test_touching_close_is_not_ok(self) -> None:
        at_close = check_hours(_stop(end=f"{MONDAY}T17:00:00"))
        self.assertFalse(at_close["ok"])
        self.assertEqual(at_close["reason"], "touches closing time")

        starts_at_close = check_hours(
            _stop(start=f"{MONDAY}T17:00:00", end=f"{MONDAY}T17:30:00")
        )
        self.assertFalse(starts_at_close["ok"])
        self.assertEqual(starts_at_close["reason"], "touches closing time")

        one_minute_before = check_hours(
            _stop(start=f"{MONDAY}T09:00:00", end=f"{MONDAY}T16:59:00")
        )
        self.assertTrue(one_minute_before["ok"])

    def test_starts_before_open_is_not_ok(self) -> None:
        result = check_hours(_stop(start=f"{MONDAY}T08:59:59"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "starts before opening")

    def test_iso_clock_is_not_shifted_to_utc(self) -> None:
        # Monday 00:30 in Japan is still Sunday 15:30 UTC. Closed Monday uses the +09:00 date.
        local_monday = check_hours(
            _stop(
                start="2026-10-26T00:30:00+09:00",
                end="2026-10-26T01:00:00+09:00",
                open="00:00",
                close="02:00",
                closedWeekdays=[0],
            )
        )
        self.assertFalse(local_monday["ok"])
        self.assertEqual(local_monday["reason"], "closed on Monday")

        # The same numbers written with Z are Sunday afternoon, and Monday is the closed day.
        written_sunday = check_hours(
            _stop(
                start="2026-10-25T15:30:00Z",
                end="2026-10-25T16:00:00Z",
                closedWeekdays=[0],
            )
        )
        self.assertTrue(written_sunday["ok"])

        # Sunday 23:00 at offset -04:00 is Monday in UTC. The closed day is the ISO date.
        local_sunday = check_hours(
            _stop(
                start="2026-10-25T23:00:00-04:00",
                end="2026-10-25T23:30:00-04:00",
                open="09:00",
                close="23:59",
                closedWeekdays=[6],
            )
        )
        self.assertFalse(local_sunday["ok"])
        self.assertEqual(local_sunday["reason"], "closed on Sunday")

    def test_missing_fields_are_not_ok_and_do_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            [],
            {"segmentId": "attraction-1"},
            _stop(start="2026-10-26"),
            _stop(open="9:00"),
            _stop(close="17:00:00"),
            _stop(closedWeekdays=None),
            _stop(closedWeekdays=[True]),
            _stop(closedWeekdays=["6"]),
            _stop(closedWeekdays=[7]),
            _stop(segmentId=""),
            _stop(segmentId=1),
            _stop(close="09:00"),
        ]
        for case in cases:
            result = check_hours(case)
            self.assertEqual(set(result), {"segmentId", "ok", "reason"})
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "missing fields")
            self.assertIsInstance(result["segmentId"], str)

        self.assertEqual(
            check_hours(),
            {"segmentId": "", "ok": False, "reason": "missing fields"},
        )
        kept = check_hours(segmentId="attraction-1", start=f"{MONDAY}T10:00:00")
        self.assertEqual(kept["segmentId"], "attraction-1")
        self.assertFalse(kept["ok"])

    def test_tool_spec_is_check_hours(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_hours")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "start", "end", "open", "close", "closedWeekdays"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["segmentId", "ok", "reason"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("after a replan", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_hours")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_hours(self) -> None:
        payload = _stop()
        self.assertEqual(handler(payload), check_hours(payload))
        self.assertEqual(handler(json.dumps(payload)), check_hours(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("assist___check_hours"))
        self.assertTrue(wrapped["ok"])
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(
            rejected,
            {
                "segmentId": "",
                "ok": False,
                "reason": "unsupported AgentCore tool; expected check_hours",
            },
        )

    def test_does_not_read_the_wall_clock_or_aws(self) -> None:
        source = inspect.getsource(hours_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            ".utcnow",
            "astimezone",
            "time.time",
            "time.localtime",
            "zoneinfo",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "bedrock_agentcore",
            "socket",
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
            raise AssertionError("check_hours opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
