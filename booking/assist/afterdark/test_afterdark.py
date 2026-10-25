"""After dark: a walk after sunset asks for a ride, and a ride stays a ride.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.assist.afterdark import AGENTCORE_TOOL, TOOL_SPEC, after_dark, handler
from booking.assist.afterdark import afterdark as afterdark_mod
from booking.assist.afterdark import tool as tool_mod
from booking.assist.afterdark.afterdark import REASON_AFTER, REASON_BEFORE, REASON_RIDE


def _segment(**overrides) -> dict:
    payload = {
        "segmentId": "walk-fushimi",
        "mode": "walk",
        "now": "2026-11-03T16:00:00+09:00",
        "sunset": "2026-11-03T17:00:00+09:00",
    }
    payload.update(overrides)
    return payload


class AfterDarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_walk_after_sunset_requests_ride(self) -> None:
        payload = _segment(
            now="2026-11-03T08:30:00Z",
            sunset="2026-11-03T17:00:00+09:00",
        )
        result = handler(payload)

        self.assertEqual(
            result,
            {
                "segmentId": "walk-fushimi",
                "ok": False,
                "action": "request_ride",
                "reason": REASON_AFTER,
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "request_ride")

        at_sunset = after_dark(
            _segment(
                now="2026-11-03T08:00:00Z",
                sunset="2026-11-03T17:00:00+09:00",
            )
        )
        self.assertFalse(at_sunset["ok"])
        self.assertEqual(at_sunset["action"], "request_ride")
        self.assertEqual(at_sunset["reason"], REASON_AFTER)

    def test_walk_before_sunset_is_fine(self) -> None:
        result = after_dark(_segment())

        self.assertEqual(
            result,
            {
                "segmentId": "walk-fushimi",
                "ok": True,
                "action": "none",
                "reason": REASON_BEFORE,
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "none")

    def test_ride_is_fine(self) -> None:
        result = after_dark(
            _segment(
                mode="ride",
                now="2026-11-03T18:30:00+09:00",
                sunset="2026-11-03T17:00:00+09:00",
            )
        )

        self.assertEqual(
            result,
            {
                "segmentId": "walk-fushimi",
                "ok": True,
                "action": "none",
                "reason": REASON_RIDE,
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "none")

        without_times = handler({"segmentId": "ride-1", "mode": "ride"})
        self.assertTrue(without_times["ok"])
        self.assertEqual(without_times["action"], "none")
        self.assertEqual(without_times["segmentId"], "ride-1")

    def test_missing_times_do_not_request_ride(self) -> None:
        missing_now = after_dark(_segment(now=None))
        self.assertFalse(missing_now["ok"])
        self.assertEqual(missing_now["action"], "none")
        self.assertIn("now", missing_now["reason"])

        missing_sunset = after_dark(_segment(sunset=""))
        self.assertFalse(missing_sunset["ok"])
        self.assertEqual(missing_sunset["action"], "none")
        self.assertIn("sunset", missing_sunset["reason"])

        both = after_dark({"segmentId": "walk-fushimi", "mode": "walk"})
        self.assertFalse(both["ok"])
        self.assertEqual(both["action"], "none")
        self.assertIn("now", both["reason"])
        self.assertIn("sunset", both["reason"])

        invalid = after_dark(_segment(now="not-a-time"))
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["action"], "none")
        self.assertIn("now", invalid["reason"])

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            [],
            {},
            "{",
            {"mode": "walking", "now": "2026-11-03T18:30:00Z", "sunset": "2026-11-03T17:00:00Z"},
            {"segmentId": "walk-fushimi", "mode": "walk", "now": 1, "sunset": True},
        ]
        for case in cases:
            result = after_dark(case)
            self.assertEqual(set(result), {"segmentId", "ok", "action", "reason"})
            self.assertIsInstance(result["ok"], bool)
            self.assertIn(result["action"], ("none", "request_ride"))
            self.assertIsInstance(result["reason"], str)
            self.assertTrue(result["reason"])
            self.assertNotEqual(result["action"], "request_ride")

    def test_tool_spec_is_after_dark(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "after_dark")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "mode", "now", "sunset"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "ok", "action", "reason"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["action"]["enum"],
            ["none", "request_ride"],
        )
        self.assertIn("Bedrock AgentCore", TOOL_SPEC["description"])
        self.assertIn("request_ride", TOOL_SPEC["description"])
        self.assertIn("ride agent", TOOL_SPEC["description"])
        self.assertIn("no network and no AWS", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "after_dark")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_after_dark(self) -> None:
        payload = _segment()
        self.assertEqual(handler(payload), after_dark(payload))
        self.assertEqual(handler(payload, _AgentCoreContext("runtime___after_dark")), after_dark(payload))
        wrapped = after_dark({"arguments": payload})
        self.assertEqual(wrapped, after_dark(payload))

        rejected = handler(payload, _AgentCoreContext("ride"))
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["action"], "none")
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected after_dark")

    def test_sandbox_source_has_no_network_client(self) -> None:
        for module in (afterdark_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("import boto", source)
            self.assertNotIn("import requests", source)
            self.assertNotIn("import urllib", source)
            self.assertNotIn("import httpx", source)
            self.assertNotIn("import socket", source)
            self.assertNotIn("amazonaws", source)
            self.assertNotIn("datetime.now", source)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = self
        self.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("after_dark opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
