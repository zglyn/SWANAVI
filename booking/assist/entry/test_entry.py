"""Entry requirements: valid passport and visa, short expiry, missing visa.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import socket
import unittest
from datetime import date, timedelta

from booking.assist.entry import AGENTCORE_TOOL, TOOL_SPEC, check_entry, handler
from booking.assist.entry import entry as entry_mod
from booking.assist.entry import tool as tool_mod
from booking.assist.entry.entry import (
    ISSUE_PASSPORT_MISSING,
    ISSUE_PASSPORT_SHORT,
    ISSUE_VISA_FALSE,
    ISSUE_VISA_MISSING,
)


def _facts(**overrides) -> dict:
    payload = {
        "destinationCountry": "JP",
        "passportExpiry": "2027-12-01",
        "tripEnd": "2026-06-01",
        "visaOnFile": True,
    }
    payload.update(overrides)
    return payload


class CheckEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_valid_passport_and_visa_ok(self) -> None:
        result = check_entry(_facts())

        self.assertEqual(result, {"ok": True, "issues": []})
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])

    def test_expiry_inside_180_days_not_ok(self) -> None:
        result = check_entry(_facts(passportExpiry="2026-08-01"))

        self.assertFalse(result["ok"])
        self.assertIn(ISSUE_PASSPORT_SHORT, result["issues"])
        self.assertNotIn(ISSUE_VISA_FALSE, result["issues"])

        trip_end = date(2026, 6, 1)
        one_day_short = (trip_end + timedelta(days=179)).isoformat()
        short = check_entry(_facts(tripEnd=trip_end.isoformat(), passportExpiry=one_day_short))
        self.assertFalse(short["ok"])
        self.assertEqual(short["issues"], [ISSUE_PASSPORT_SHORT])

    def test_passport_exactly_180_days_after_trip_end_ok(self) -> None:
        trip_end = date(2026, 6, 1)
        on_the_day = (trip_end + timedelta(days=180)).isoformat()
        result = check_entry(_facts(tripEnd=trip_end.isoformat(), passportExpiry=on_the_day))

        self.assertEqual(result, {"ok": True, "issues": []})

    def test_visa_missing_not_ok(self) -> None:
        refused = check_entry(_facts(visaOnFile=False))
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["issues"], [ISSUE_VISA_FALSE])

        absent = check_entry(
            {
                "destinationCountry": "JP",
                "passportExpiry": "2027-12-01",
                "tripEnd": "2026-06-01",
            }
        )
        self.assertFalse(absent["ok"])
        self.assertEqual(absent["issues"], [ISSUE_VISA_MISSING])

    def test_passport_missing_not_ok(self) -> None:
        result = check_entry(_facts(passportExpiry=None))

        self.assertFalse(result["ok"])
        self.assertIn(ISSUE_PASSPORT_MISSING, result["issues"])
        self.assertNotIn(ISSUE_PASSPORT_SHORT, result["issues"])

        blank = check_entry(_facts(passportExpiry="  "))
        self.assertFalse(blank["ok"])
        self.assertIn(ISSUE_PASSPORT_MISSING, blank["issues"])

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            [],
            {},
            {"passportExpiry": "2026-13-40", "tripEnd": "2026-06-01", "visaOnFile": True},
            {"passportExpiry": "01-06-2026", "tripEnd": "2026-06-01", "visaOnFile": False},
            "{",
        ]
        for case in cases:
            result = check_entry(case)
            self.assertEqual(set(result), {"ok", "issues"})
            self.assertFalse(result["ok"])
            self.assertIsInstance(result["issues"], list)
            self.assertTrue(result["issues"])
            self.assertTrue(all(isinstance(issue, str) and issue for issue in result["issues"]))

    def test_tool_spec_is_check_entry(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_entry")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["destinationCountry", "passportExpiry", "tripEnd", "visaOnFile"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["ok", "issues"])
        self.assertIn("before the trip starts", TOOL_SPEC["description"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("no network and no AWS", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_entry")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_entry(self) -> None:
        payload = _facts()
        self.assertEqual(handler(payload), check_entry(payload))
        self.assertEqual(handler(payload, _AgentCoreContext("assist___check_entry")), check_entry(payload))

        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["issues"], ["unsupported AgentCore tool; expected check_entry"])

    def test_sandbox_source_has_no_network_client(self) -> None:
        for module in (entry_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("import boto", source)
            self.assertNotIn("import requests", source)
            self.assertNotIn("import urllib", source)
            self.assertNotIn("import httpx", source)
            self.assertNotIn("import socket", source)
            self.assertNotIn("amazonaws", source)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = self
        self.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("check_entry opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
