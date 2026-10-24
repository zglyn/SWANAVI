"""Tip policy: country percent, then the ceiling the spend guard must use.

These tests stay in-process. They do not charge a card, call a ledger, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest
from decimal import Decimal

from booking.assist.tip import AGENTCORE_TOOL, TOOL_SPEC, handler, tip_policy
from booking.assist.tip import policy as policy_mod
from booking.assist.tip import tool as tool_mod


def _call(country, subtotal, currency="USD") -> dict:
    return tip_policy({"country": country, "subtotal": subtotal, "currency": currency})


class TipPolicyTests(unittest.TestCase):
    def test_japan_zero_on_ten_authorizes_ten(self) -> None:
        result = _call("Japan", 10, "JPY")
        self.assertEqual(
            result,
            {
                "maxTipPercent": 0,
                "tipAmount": 0,
                "authorizedAmount": 10,
                "currency": "JPY",
                "reason": "country_rule",
            },
        )

    def test_united_states_twenty_on_ten_authorizes_twelve(self) -> None:
        result = _call("United States", 10, "USD")
        self.assertEqual(
            result,
            {
                "maxTipPercent": 20,
                "tipAmount": 2,
                "authorizedAmount": 12,
                "currency": "USD",
                "reason": "country_rule",
            },
        )

    def test_us_short_name_is_the_same_twenty_percent(self) -> None:
        for country in ("US", "USA", "U.S.", "united states"):
            result = _call(country, 10, "USD")
            self.assertEqual(result["maxTipPercent"], 20, country)
            self.assertEqual(result["tipAmount"], 2, country)
            self.assertEqual(result["authorizedAmount"], 12, country)

    def test_france_zero_on_ten_authorizes_ten(self) -> None:
        result = _call("France", 10, "EUR")
        self.assertEqual(result["maxTipPercent"], 0)
        self.assertEqual(result["tipAmount"], 0)
        self.assertEqual(result["authorizedAmount"], 10)
        self.assertEqual(result["currency"], "EUR")
        self.assertEqual(result["reason"], "country_rule")

    def test_any_other_country_is_ten_percent(self) -> None:
        result = _call("Germany", 10, "EUR")
        self.assertEqual(result["maxTipPercent"], 10)
        self.assertEqual(result["tipAmount"], 1)
        self.assertEqual(result["authorizedAmount"], 11)

        unnamed = tip_policy({"subtotal": 10, "currency": "EUR"})
        self.assertEqual(unnamed["maxTipPercent"], 10)
        self.assertEqual(unnamed["authorizedAmount"], 11)

    def test_rounds_half_up_to_two_decimals(self) -> None:
        # 10.05 * 10 / 100 = 1.005 -> 1.01. 10.05 + 1.01 = 11.06.
        other = _call("Italy", "10.05", "EUR")
        self.assertEqual(other["maxTipPercent"], 10)
        self.assertEqual(other["tipAmount"], 1.01)
        self.assertEqual(other["authorizedAmount"], 11.06)

        # 33.33 * 20 / 100 = 6.666 -> 6.67. 33.33 + 6.67 = 40.00.
        united = _call("United States", "33.33", "USD")
        self.assertEqual(united["tipAmount"], 6.67)
        self.assertEqual(united["authorizedAmount"], 40)
        self.assertEqual(Decimal(str(united["authorizedAmount"])), Decimal("40"))

    def test_missing_subtotal_returns_null_tip(self) -> None:
        cases = [
            tip_policy({"country": "Japan", "currency": "JPY"}),
            tip_policy({"country": "Japan", "subtotal": None, "currency": "JPY"}),
            tip_policy({"country": "Japan", "subtotal": "  ", "currency": "JPY"}),
            tip_policy(country="Japan", currency="JPY"),
        ]
        for result in cases:
            self.assertEqual(result["maxTipPercent"], 0)
            self.assertIsNone(result["tipAmount"])
            self.assertIsNone(result["authorizedAmount"])
            self.assertEqual(result["currency"], "JPY")
            self.assertEqual(result["reason"], "missing_subtotal")

        named = tip_policy("Japan")
        self.assertEqual(named["maxTipPercent"], 0)
        self.assertIsNone(named["tipAmount"])
        self.assertEqual(named["reason"], "missing_subtotal")
        self.assertEqual(named["currency"], "")

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            tip_policy(),
            tip_policy(None),
            tip_policy("not-json"),
            tip_policy([]),
            tip_policy("{"),
            tip_policy("[1]"),
            tip_policy({"subtotal": "nope", "country": "France", "currency": "EUR"}),
            tip_policy({"subtotal": True, "country": "France"}),
            tip_policy({"subtotal": -1, "country": "Japan", "currency": "JPY"}),
            tip_policy({"subtotal": float("nan"), "country": "Japan"}),
            tip_policy({"subtotal": float("inf"), "country": "US"}),
            tip_policy({"subtotal": {}, "country": "France"}),
        ]
        for result in cases:
            self.assertEqual(
                set(result),
                {"maxTipPercent", "tipAmount", "authorizedAmount", "currency", "reason"},
            )
            self.assertIsNone(result["tipAmount"])
            self.assertIsNone(result["authorizedAmount"])
            self.assertIn(result["reason"], {"missing_subtotal", "invalid_subtotal"})

    def test_zero_subtotal_is_a_real_amount(self) -> None:
        result = _call("United States", 0, "USD")
        self.assertEqual(result["tipAmount"], 0)
        self.assertEqual(result["authorizedAmount"], 0)
        self.assertEqual(result["reason"], "country_rule")

    def test_currency_is_passed_through(self) -> None:
        result = _call("Japan", 10, " usd ")
        self.assertEqual(result["currency"], "usd")
        self.assertEqual(result["authorizedAmount"], 10)

    def test_tool_spec_is_tip_policy(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "tip_policy")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["country", "subtotal", "currency"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["maxTipPercent", "tipAmount", "authorizedAmount", "currency", "reason"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("AgentCore", description)
        self.assertIn("before authorize_spend", description)
        self.assertIn("vendor cannot add a tip past the country rule", description)
        self.assertIn("ceiling the spend guard must use", description)
        self.assertIn("Japan 0", description)
        self.assertIn("United States 20", description)
        self.assertIn("France 0", description)
        self.assertIn("missing_subtotal", description)
        self.assertIn("does not charge a card", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "tip_policy")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_tip_policy(self) -> None:
        payload = {"country": "United States", "subtotal": 10, "currency": "USD"}
        self.assertEqual(handler(payload), tip_policy(payload))
        self.assertEqual(handler(json.dumps(payload)), tip_policy(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___tip_policy"))
        self.assertEqual(wrapped["maxTipPercent"], 20)
        self.assertEqual(wrapped["authorizedAmount"], 12)

        nested = handler({"input": payload})
        self.assertEqual(nested["authorizedAmount"], 12)

        rejected = handler(payload, _AgentCoreContext("authorize_spend"))
        self.assertIsNone(rejected["tipAmount"])
        self.assertIsNone(rejected["authorizedAmount"])
        self.assertEqual(rejected["currency"], "USD")
        self.assertEqual(rejected["maxTipPercent"], 20)
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected tip_policy")

    def test_does_not_charge_or_call_the_network(self) -> None:
        source = inspect.getsource(policy_mod) + inspect.getsource(tool_mod)
        for banned in (
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "httpx",
            "xrpl",
            "stripe",
            "socket",
            "bedrock_agentcore",
        ):
            self.assertNotIn(banned, source)
        self.assertNotIn("authorize_spend(", source)
        with _network_forbidden():
            result = _call("United States", 10)
        self.assertEqual(result["authorizedAmount"], 12)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("tip_policy opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
