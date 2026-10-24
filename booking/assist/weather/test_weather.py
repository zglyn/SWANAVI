"""Weather holds: indoor stays, outdoor storm shifts, outdoor clear stays.

These tests stay in-process. They do not call a weather API, open a socket, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.weather import AGENTCORE_TOOL, TOOL_SPEC, check_weather, handler
from booking.assist.weather import tool as tool_mod
from booking.assist.weather import weather as weather_mod


def _call(outdoor, condition, segment_id="attraction-1") -> dict:
    return check_weather(
        {"segmentId": segment_id, "outdoor": outdoor, "condition": condition}
    )


class CheckWeatherTests(unittest.TestCase):
    def test_indoor_rain_is_ok(self) -> None:
        result = _call(False, "rain")
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "ok": True,
                "action": "none",
                "reason": "indoor",
            },
        )

    def test_outdoor_storm_action_shift(self) -> None:
        result = _call(True, "storm")
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "ok": False,
                "action": "shift",
                "reason": "storm",
            },
        )

    def test_outdoor_clear_is_ok(self) -> None:
        result = _call(True, "clear")
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "ok": True,
                "action": "none",
                "reason": "clear",
            },
        )

    def test_outdoor_rain_and_snow_shift(self) -> None:
        for condition in ("rain", "snow", " Storm ", "SNOW"):
            result = _call(True, condition)
            self.assertFalse(result["ok"])
            self.assertEqual(result["action"], "shift")
            self.assertEqual(result["reason"], condition.strip().lower())

    def test_outdoor_cloudy_is_ok(self) -> None:
        result = _call(True, "cloudy")
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "cloudy")

    def test_unknown_condition(self) -> None:
        for condition in ("fog", "rainy", "hail", "", None, 3):
            result = _call(True, condition)
            self.assertEqual(result["ok"], False)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "unknown_condition")
            self.assertEqual(set(result), {"segmentId", "ok", "action", "reason"})

    def test_bad_payload_does_not_raise(self) -> None:
        cases = [
            check_weather(),
            check_weather(None),
            check_weather("not-json"),
            check_weather([]),
            check_weather({"segmentId": "attraction-1", "condition": "storm"}),
            check_weather({"segmentId": "attraction-1", "outdoor": "true", "condition": "storm"}),
            check_weather({"segmentId": "attraction-1", "outdoor": 1, "condition": "clear"}),
        ]
        for result in cases:
            self.assertIsInstance(result, dict)
            self.assertEqual(result["ok"], False)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "invalid_input")
            self.assertEqual(set(result), {"segmentId", "ok", "action", "reason"})
        missing_outdoor = check_weather({"segmentId": "attraction-1", "condition": "storm"})
        self.assertEqual(missing_outdoor["segmentId"], "attraction-1")
        blank_id = check_weather(segmentId=12, outdoor=True, condition="clear")
        self.assertEqual(blank_id["segmentId"], "")
        self.assertTrue(blank_id["ok"])
        self.assertEqual(blank_id["action"], "none")

    def test_tool_spec_is_check_weather(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_weather")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "outdoor", "condition"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "ok", "action", "reason"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["action"]["enum"],
            ["none", "shift", "swap_indoor"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("AgentCore", description)
        self.assertIn("forecast", description)
        self.assertIn("does not move", description)
        self.assertIn("no weather API", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_weather")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_weather(self) -> None:
        payload = {"segmentId": "attraction-1", "outdoor": True, "condition": "storm"}
        self.assertEqual(handler(payload), check_weather(payload))
        self.assertEqual(handler(json.dumps(payload)), check_weather(payload))
        wrapped = handler(
            {"arguments": payload},
            _AgentCoreContext("runtime___check_weather"),
        )
        self.assertEqual(wrapped["action"], "shift")
        self.assertEqual(wrapped["reason"], "storm")

        rejected = handler(payload, _AgentCoreContext("replan_late"))
        self.assertEqual(rejected["ok"], False)
        self.assertEqual(rejected["action"], "none")
        self.assertEqual(rejected["segmentId"], "attraction-1")
        self.assertEqual(
            rejected["reason"],
            "unsupported AgentCore tool; expected check_weather",
        )
        self.assertEqual(handler(None), check_weather(None))

    def test_does_not_call_the_network(self) -> None:
        source = inspect.getsource(weather_mod) + inspect.getsource(tool_mod)
        for banned in (
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "httpx",
            "http.client",
            "socket",
            "xrpl",
            "stripe",
            "bedrock_agentcore",
            "openweather",
        ):
            self.assertNotIn(banned, source)
        with _network_forbidden():
            result = _call(True, "storm")
        self.assertEqual(result["action"], "shift")


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("check_weather opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
