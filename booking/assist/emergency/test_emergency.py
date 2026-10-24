"""Emergency card: sandbox phone numbers for Japan, France, and the United States.

These tests stay in-process. They do not call AWS or open a connection.
The card returns phone numbers only.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.emergency import AGENTCORE_TOOL, TOOL_SPEC, emergency_card, handler
from booking.assist.emergency import card as card_mod
from booking.assist.emergency import tool as tool_mod

TRAVELER = "Ada Lovelace"


def _payload(country: str, traveler_name: str = TRAVELER) -> dict:
    return {"country": country, "travelerName": traveler_name}


class EmergencyCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_japan_returns_110(self) -> None:
        result = emergency_card(_payload("Japan"))

        self.assertEqual(set(result), {"country", "emergencyNumber", "embassyPhone", "note"})
        self.assertEqual(result["country"], "Japan")
        self.assertEqual(result["emergencyNumber"], "110")
        self.assertEqual(result["embassyPhone"], "+81-3-3224-5000")
        self.assertIn(TRAVELER, result["note"])
        self.assertIn("Phone numbers only", result["note"])
        self.assertNotIn("unknown_country", result["note"])

    def test_france_and_united_states_use_the_sandbox_directory(self) -> None:
        france = emergency_card(_payload("France"))
        self.assertEqual(france["country"], "France")
        self.assertEqual(france["emergencyNumber"], "112")
        self.assertEqual(france["embassyPhone"], "+33-1-4312-2222")
        self.assertIn(TRAVELER, france["note"])

        states = emergency_card(_payload("United States"))
        self.assertEqual(states["country"], "United States")
        self.assertEqual(states["emergencyNumber"], "911")
        self.assertEqual(states["embassyPhone"], "+1-202-555-0100")
        self.assertIn(TRAVELER, states["note"])

    def test_unknown_country_returns_112_and_null_embassy(self) -> None:
        result = emergency_card(_payload("Wakanda"))

        self.assertEqual(result["country"], "Wakanda")
        self.assertEqual(result["emergencyNumber"], "112")
        self.assertIsNone(result["embassyPhone"])
        self.assertIn("unknown_country", result["note"])
        self.assertIn(TRAVELER, result["note"])
        self.assertIn("Phone numbers only", result["note"])
        self.assertIsNone(json.loads(json.dumps(result))["embassyPhone"])

    def test_country_aliases_stay_inside_the_sandbox_directory(self) -> None:
        self.assertEqual(emergency_card(_payload("japan"))["emergencyNumber"], "110")
        self.assertEqual(emergency_card(_payload("JP"))["country"], "Japan")
        self.assertEqual(emergency_card(_payload("FR"))["embassyPhone"], "+33-1-4312-2222")
        self.assertEqual(emergency_card(_payload("USA"))["emergencyNumber"], "911")
        self.assertEqual(emergency_card("United States", TRAVELER)["country"], "United States")

    def test_missing_fields_do_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"travelerName": TRAVELER},
            {"country": "Japan"},
            {"country": None, "travelerName": None},
            {"arguments": {"country": "Japan", "travelerName": TRAVELER}},
            {"input": {"country": "France", "traveler_name": TRAVELER}},
        ]
        for case in cases:
            result = emergency_card(case)
            self.assertEqual(set(result), {"country", "emergencyNumber", "embassyPhone", "note"})
            self.assertIsInstance(result["country"], str)
            self.assertIsInstance(result["emergencyNumber"], str)
            self.assertTrue(result["emergencyNumber"])
            self.assertTrue(result["embassyPhone"] is None or isinstance(result["embassyPhone"], str))
            self.assertIsInstance(result["note"], str)
            self.assertTrue(result["note"])

        named = emergency_card({"country": "Japan", "travelerName": TRAVELER})
        self.assertEqual(named["emergencyNumber"], "110")
        self.assertIn(TRAVELER, named["note"])

        missing_name = emergency_card({"country": "Atlantis"})
        self.assertEqual(missing_name["emergencyNumber"], "112")
        self.assertIsNone(missing_name["embassyPhone"])
        self.assertIn("unknown_country", missing_name["note"])

    def test_json_object_is_one_card(self) -> None:
        raw = '{"country":"Japan","travelerName":"Ada Lovelace"}'
        result = emergency_card(raw)
        self.assertEqual(result["emergencyNumber"], "110")
        self.assertIn(TRAVELER, result["note"])

    def test_tool_spec_is_emergency_card(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "emergency_card")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["country", "travelerName"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["country", "emergencyNumber", "embassyPhone", "note"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("phone numbers only", TOOL_SPEC["description"].lower())
        self.assertIn("not medical guidance", TOOL_SPEC["description"])
        self.assertIn("unknown_country", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "emergency_card")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_emergency_card(self) -> None:
        payload = _payload("Japan")
        self.assertEqual(handler(payload), emergency_card(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___emergency_card"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), emergency_card(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___trip_notice"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(set(ignored), {"country", "emergencyNumber", "embassyPhone", "note"})
        self.assertEqual(ignored["emergencyNumber"], "112")
        self.assertIsNone(ignored["embassyPhone"])
        self.assertIn("unknown_country", ignored["note"])
        self.assertIn(TRAVELER, ignored["note"])

    def test_sandbox_sources_do_not_touch_network_or_aws(self) -> None:
        for module in (card_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("subprocess", source)
            self.assertNotIn("datetime.now", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("emergency_card opened a connection")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
