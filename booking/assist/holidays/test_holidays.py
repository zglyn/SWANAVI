"""Holiday closures: Culture Day shifts an attraction, a hotel stays open, an ordinary Tuesday stays open.

These tests stay in-process. They do not call a holiday API, open a socket, or call AWS.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest
from datetime import date

from booking.assist.holidays import AGENTCORE_TOOL, TOOL_SPEC, handler, holiday_closure
from booking.assist.holidays import holidays as holidays_mod
from booking.assist.holidays import tool as tool_mod

CULTURE_DAY = "2026-11-03"
ORDINARY_TUESDAY = "2026-11-10"


def _segment(**extra) -> dict:
    payload = {
        "segmentId": "attraction-1",
        "kind": "attraction",
        "name": "Senso-ji",
        "city": "Tokyo",
        "country": "Japan",
        "date": CULTURE_DAY,
    }
    payload.update(extra)
    return payload


class HolidayClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_culture_day_attraction_is_closed(self) -> None:
        payload = _segment()
        original = copy.deepcopy(payload)
        result = holiday_closure(payload)

        self.assertEqual(date.fromisoformat(CULTURE_DAY).strftime("%A"), "Tuesday")
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "closed": True,
                "holiday": "Culture Day",
                "action": "shift",
            },
        )
        self.assertEqual(payload, original)
        self.assertNotIn("error", result)

    def test_culture_day_hotel_stays_open(self) -> None:
        result = holiday_closure(
            _segment(segmentId="hotel-1", kind="hotel", name="Ryokan")
        )
        self.assertEqual(
            result,
            {
                "segmentId": "hotel-1",
                "closed": False,
                "holiday": "Culture Day",
                "action": "none",
            },
        )

    def test_ordinary_tuesday_stays_open(self) -> None:
        self.assertEqual(date.fromisoformat(ORDINARY_TUESDAY).strftime("%A"), "Tuesday")
        result = holiday_closure(
            _segment(segmentId="attraction-2", date=ORDINARY_TUESDAY, name="TeamLab")
        )
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-2",
                "closed": False,
                "holiday": None,
                "action": "none",
            },
        )

    def test_open_kinds_stay_open_on_a_holiday(self) -> None:
        for kind in ("flight", "hotel", "restaurant", "Flight", " HOTEL "):
            result = holiday_closure(_segment(kind=kind, name="Stay"))
            self.assertFalse(result["closed"], kind)
            self.assertEqual(result["action"], "none", kind)
            self.assertEqual(result["holiday"], "Culture Day", kind)
            self.assertNotIn("error", result)

    def test_sandbox_holiday_table(self) -> None:
        cases = (
            ("Japan", "2026-11-03", "Culture Day", "Tokyo"),
            ("jp", "2026-11-23", "Labor Thanksgiving Day", "Osaka"),
            ("France", "2026-11-11", "Armistice Day", "Paris"),
            ("FR", "2026-11-11", "Armistice Day", "Lyon"),
            ("United States", "2026-11-26", "Thanksgiving Day", "New York"),
            ("US", "2026-11-26", "Thanksgiving Day", "Boston"),
            ("USA", "2026-11-26", "Thanksgiving Day", "Chicago"),
            (" usa ", "2026-11-26", "Thanksgiving Day", "Seattle"),
        )
        for country, day, holiday, city in cases:
            result = holiday_closure(
                _segment(kind="Attraction", country=country, date=day, city=city, name=holiday)
            )
            self.assertEqual(
                result,
                {
                    "segmentId": "attraction-1",
                    "closed": True,
                    "holiday": holiday,
                    "action": "shift",
                },
                country,
            )

    def test_same_date_in_another_country_is_open(self) -> None:
        result = holiday_closure(
            _segment(country="France", city="Paris", name="Louvre", date=CULTURE_DAY)
        )
        self.assertEqual(
            result,
            {
                "segmentId": "attraction-1",
                "closed": False,
                "holiday": None,
                "action": "none",
            },
        )

    def test_bad_segment_does_not_raise(self) -> None:
        cases = [
            None,
            "not-json",
            [],
            {},
            {"segmentId": "attraction-1"},
            _segment(kind="walk"),
            _segment(kind="meal"),
            _segment(date="11/03/2026"),
            _segment(date="2026-11-3"),
            _segment(date="2026-11-31"),
            _segment(date="2026-11-03T10:00:00"),
            _segment(segmentId=""),
            _segment(segmentId=1),
            _segment(country=""),
            _segment(country=None),
            _segment(name=""),
            _segment(name=None),
            _segment(city="  "),
        ]
        for case in cases:
            result = holiday_closure(case)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["error"], "invalid_segment")
            self.assertFalse(result["closed"])
            self.assertIsNone(result["holiday"])
            self.assertIsInstance(result["segmentId"], str)

        self.assertEqual(
            holiday_closure(),
            {
                "segmentId": "",
                "closed": False,
                "holiday": None,
                "action": "none",
                "error": "invalid_segment",
            },
        )
        kept = holiday_closure(_segment(kind="cruise"))
        self.assertEqual(kept["segmentId"], "attraction-1")
        self.assertEqual(kept["action"], "none")

    def test_call_shapes(self) -> None:
        payload = _segment()
        self.assertTrue(holiday_closure(json.dumps(payload))["closed"])
        self.assertTrue(holiday_closure(**payload)["closed"])
        self.assertTrue(holiday_closure({"segment": payload})["closed"])
        self.assertTrue(holiday_closure({"arguments": payload})["closed"])
        self.assertTrue(holiday_closure({"input": payload})["closed"])
        self.assertEqual(holiday_closure(payload)["holiday"], "Culture Day")

    def test_tool_spec_is_holiday_closure(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "holiday_closure")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "kind", "name", "city", "country", "date"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "closed", "holiday", "action"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["action"]["enum"],
            ["none", "shift"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("AgentCore", description)
        self.assertIn("shift", description)
        self.assertIn("does not move", description)
        self.assertIn("invalid_segment", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "holiday_closure")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_holiday_closure(self) -> None:
        payload = _segment()
        self.assertEqual(handler(payload), holiday_closure(payload))
        self.assertEqual(handler(json.dumps(payload)), holiday_closure(payload))
        wrapped = handler(
            {"arguments": payload},
            _AgentCoreContext("runtime___holiday_closure"),
        )
        self.assertEqual(wrapped["action"], "shift")
        self.assertEqual(wrapped["holiday"], "Culture Day")

        rejected = handler(payload, _AgentCoreContext("check_weather"))
        self.assertEqual(rejected["closed"], False)
        self.assertEqual(rejected["action"], "none")
        self.assertEqual(rejected["segmentId"], "attraction-1")
        self.assertEqual(
            rejected["error"],
            "unsupported AgentCore tool; expected holiday_closure",
        )
        self.assertEqual(handler(None), holiday_closure(None))

    def test_does_not_call_the_network(self) -> None:
        source = inspect.getsource(holidays_mod) + inspect.getsource(tool_mod)
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
            "datetime.now",
            ".utcnow",
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
            raise AssertionError("holiday_closure opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
