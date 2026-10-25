"""Landing data: ready when the phone has data, remind before the window, install inside it.

These tests stay in-process. They do not call a carrier, buy a plan, or open a socket.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest
from pathlib import Path

from booking.assist.connectivity import AGENTCORE_TOOL, TOOL_SPEC, handler, landing_data
from booking.assist.connectivity import landing as landing_mod
from booking.assist.connectivity.landing import PLAN_PREFIX
from booking.assist.connectivity import tool as tool_mod

COUNTRY = "JP"
ARRIVE = "2026-11-02T14:00:00Z"
REMIND_AT = "2026-11-02T12:00:00Z"
TOO_EARLY = "2026-11-02T11:59:59Z"
INSIDE = "2026-11-02T13:00:00Z"
AFTER = "2026-11-02T16:30:00Z"

_OUTPUT_KEYS = {"country", "status", "action", "planCode", "remindAt"}


def _ask(**overrides):
    payload = {
        "country": COUNTRY,
        "arriveAt": ARRIVE,
        "now": INSIDE,
        "hasData": False,
    }
    payload.update(overrides)
    return landing_data(payload)


class LandingDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_has_data_is_ready_with_no_plan(self) -> None:
        inside = _ask(hasData=True, now=INSIDE)
        early = _ask(hasData=True, now=TOO_EARLY)
        after = landing_data(COUNTRY, ARRIVE, AFTER, True)

        for result in (inside, early, after):
            self.assertEqual(set(result), _OUTPUT_KEYS)
            self.assertEqual(result["country"], COUNTRY)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["action"], "none")
            self.assertIsNone(result["planCode"])
            self.assertIsNone(result["remindAt"])

    def test_too_early_to_install_reminds(self) -> None:
        result = _ask(hasData=False, now=TOO_EARLY)

        self.assertEqual(result["country"], COUNTRY)
        self.assertEqual(result["status"], "remind")
        self.assertEqual(result["action"], "remind")
        self.assertIsNone(result["planCode"])
        self.assertEqual(result["remindAt"], REMIND_AT)

        shifted = _ask(
            arriveAt="2026-11-02T23:00:00+09:00",
            now="2026-11-02T20:59:59+09:00",
            hasData=False,
        )
        self.assertEqual(shifted["status"], "remind")
        self.assertEqual(shifted["remindAt"], REMIND_AT)
        self.assertIsNone(shifted["planCode"])

    def test_inside_the_window_installs_a_sandbox_label(self) -> None:
        inside = _ask(hasData=False, now=INSIDE)
        on_the_hour = _ask(hasData=False, now=REMIND_AT)
        after = _ask(hasData=False, now=AFTER)
        later = _ask(hasData=False, now="2026-11-03T01:00:00Z")

        for result in (inside, on_the_hour, after, later):
            self.assertEqual(result["country"], COUNTRY)
            self.assertEqual(result["status"], "install")
            self.assertEqual(result["action"], "install_esim")
            self.assertIsNone(result["remindAt"])
            self.assertIsInstance(result["planCode"], str)
            self.assertTrue(result["planCode"].startswith(PLAN_PREFIX))
            self.assertTrue(result["planCode"].startswith("SANDBOX-ESIM-"))

        self.assertEqual(inside["planCode"], after["planCode"])
        self.assertEqual(inside["planCode"], later["planCode"])
        self.assertNotIn("http", inside["planCode"].lower())

    def test_missing_country_needs_user(self) -> None:
        for country in (None, "", "   ", "unknown", "n/a", "J"):
            result = _ask(country=country, hasData=False, now=INSIDE)
            self.assertEqual(set(result), _OUTPUT_KEYS)
            self.assertEqual(result["status"], "needs_user")
            self.assertEqual(result["action"], "none")
            self.assertIsNone(result["planCode"])
            self.assertIsNone(result["remindAt"])

        blank = _ask(country="   ")
        self.assertEqual(blank["country"], "")
        named = _ask(country=" unknown ")
        self.assertEqual(named["country"], "unknown")

        ready_without_country = _ask(country="", hasData=True)
        self.assertEqual(ready_without_country["status"], "needs_user")
        self.assertIsNone(ready_without_country["planCode"])

    def test_partial_input_does_not_raise_or_label_a_plan(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"country": COUNTRY},
            {"country": COUNTRY, "hasData": False, "arriveAt": ARRIVE},
            {"country": COUNTRY, "hasData": "maybe", "arriveAt": ARRIVE, "now": INSIDE},
            {"country": COUNTRY, "hasData": False, "arriveAt": "tomorrow", "now": INSIDE},
            {"country": COUNTRY, "hasData": False, "arriveAt": ARRIVE, "now": "soon"},
        ]
        for case in cases:
            result = landing_data(case)
            self.assertEqual(set(result), _OUTPUT_KEYS)
            self.assertIsInstance(result["country"], str)
            self.assertIn(result["status"], {"ready", "remind", "install", "needs_user"})
            self.assertIn(result["action"], {"none", "remind", "install_esim"})
            self.assertIsNone(result["planCode"])
            self.assertNotEqual(result["status"], "install")

    def test_tool_spec_is_landing_data(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "landing_data")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["country", "arriveAt", "now", "hasData"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["country", "status", "action", "planCode", "remindAt"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"],
            ["ready", "remind", "install", "needs_user"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["action"]["enum"],
            ["none", "remind", "install_esim"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("2 hours", TOOL_SPEC["description"])
        self.assertIn("SANDBOX-ESIM-", TOOL_SPEC["description"])
        self.assertIn("no real eSIM seller", TOOL_SPEC["description"])
        self.assertIn("No carrier API", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "landing_data")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_landing_data(self) -> None:
        payload = {
            "country": COUNTRY,
            "arriveAt": ARRIVE,
            "now": INSIDE,
            "hasData": False,
        }
        self.assertEqual(handler(payload), landing_data(payload))
        self.assertEqual(handler(json.dumps(payload)), landing_data(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___landing_data"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), landing_data(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___request_ride"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["status"], "needs_user")
        self.assertEqual(ignored["action"], "none")
        self.assertIsNone(ignored["planCode"])
        self.assertEqual(ignored["country"], "")

    def test_readme_states_the_two_hour_rule_and_the_unittest(self) -> None:
        text = (Path(__file__).with_name("README.md")).read_text(encoding="utf-8")
        self.assertIn("2 hours", text)
        self.assertIn("2-hour", text)
        self.assertIn("SANDBOX-ESIM-", text)
        self.assertIn("landing_data", text)
        self.assertIn("PYTHONPATH=. python3 -m unittest booking.assist.connectivity.test_connectivity", text)
        self.assertIn("later integrator", text)
        self.assertIn("booking/master", text)
        self.assertIn("no real eSIM seller", text)
        self.assertIn("does not buy a plan", text)

    def test_sandbox_sources_do_not_buy_or_touch_network(self) -> None:
        for module in (landing_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("subprocess", source)
            self.assertNotIn("datetime.now", source)
            self.assertNotIn(".utcnow", source)
            self.assertNotIn("time.time", source)
            self.assertNotIn("booking.master", source)
            self.assertNotIn("stripe", source)
            self.assertNotIn("airalo", source.lower())


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("landing_data opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
