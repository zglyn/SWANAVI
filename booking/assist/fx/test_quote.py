"""Currency quote: sandbox rates into the trip currency.

These tests stay in-process. They do not fetch a rate, call a ledger, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.fx import AGENTCORE_TOOL, TOOL_SPEC, handler, quote_fx
from booking.assist.fx import quote as quote_mod
from booking.assist.fx import tool as tool_mod


class QuoteFxTests(unittest.TestCase):
    def test_1000_jpy_quotes_to_usd(self) -> None:
        result = quote_fx(1000, "JPY", "USD")
        self.assertEqual(
            result,
            {
                "amount": 6.7,
                "currency": "USD",
                "rate": 0.0067,
                "source": "sandbox",
                "reason": "quoted",
            },
        )
        self.assertEqual(quote_fx(amount=1000, fromCurrency="jpy", toCurrency="usd"), result)

    def test_usd_to_usd_keeps_the_amount_at_rate_one(self) -> None:
        result = quote_fx(1000, "USD", "USD")
        self.assertEqual(
            result,
            {
                "amount": 1000,
                "currency": "USD",
                "rate": 1,
                "source": "sandbox",
                "reason": "same_currency",
            },
        )

    def test_unknown_currency_returns_null_amount(self) -> None:
        result = quote_fx(1000, "XYZ", "USD")
        self.assertIsNone(result["amount"])
        self.assertIsNone(result["rate"])
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["source"], "sandbox")
        self.assertEqual(result["reason"], "unknown_currency")

        other_way = quote_fx(50, "USD", "ABC")
        self.assertIsNone(other_way["amount"])
        self.assertEqual(other_way["reason"], "unknown_currency")
        self.assertEqual(other_way["source"], "sandbox")

    def test_eur_and_gbp_use_the_sandbox_usd_rates(self) -> None:
        eur = quote_fx(10, "EUR", "USD")
        self.assertEqual(eur["amount"], 10.8)
        self.assertEqual(eur["rate"], 1.08)
        self.assertEqual(eur["currency"], "USD")
        self.assertEqual(eur["reason"], "quoted")

        gbp = quote_fx(2, "GBP", "USD")
        self.assertEqual(gbp["amount"], 2.54)
        self.assertEqual(gbp["rate"], 1.27)
        self.assertEqual(gbp["currency"], "USD")

    def test_same_currency_rounds_to_two_decimal_places(self) -> None:
        result = quote_fx("10.256", "EUR", "EUR")
        self.assertEqual(result["amount"], 10.26)
        self.assertEqual(result["rate"], 1)
        self.assertEqual(result["currency"], "EUR")
        self.assertEqual(result["reason"], "same_currency")

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            quote_fx(),
            quote_fx(None),
            quote_fx("not-json"),
            quote_fx([]),
            quote_fx(-5, "JPY", "USD"),
            quote_fx("nope", "JPY", "USD"),
            quote_fx(True, "USD", "USD"),
            quote_fx(float("nan"), "USD", "USD"),
            quote_fx(float("inf"), "EUR", "USD"),
            quote_fx({"amount": {}, "fromCurrency": "JPY", "toCurrency": "USD"}),
            quote_fx(1000, None, "USD"),
            quote_fx(1000, "JPY", ""),
        ]
        for result in cases:
            self.assertIsNone(result["amount"])
            self.assertEqual(result["source"], "sandbox")
            self.assertIn(result["reason"], {"invalid_amount", "unknown_currency"})
            self.assertEqual(set(result), {"amount", "currency", "rate", "source", "reason"})

    def test_tool_spec_is_quote_fx(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "quote_fx")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["amount", "fromCurrency", "toCurrency"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["amount", "currency", "rate", "source", "reason"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["source"]["enum"], ["sandbox"])
        description = TOOL_SPEC["description"]
        self.assertIn("before authorize_spend", description)
        self.assertIn("vendor currency is not the trip currency", description)
        self.assertIn("unknown_currency", description)
        self.assertIn("JPY 0.0067", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "quote_fx")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_quote_fx(self) -> None:
        payload = {"amount": 1000, "fromCurrency": "JPY", "toCurrency": "USD"}
        self.assertEqual(handler(payload), quote_fx(payload))
        self.assertEqual(handler(json.dumps(payload)), quote_fx(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___quote_fx"))
        self.assertEqual(wrapped["amount"], 6.7)
        self.assertEqual(wrapped["reason"], "quoted")

        rejected = handler(payload, _AgentCoreContext("authorize_spend"))
        self.assertIsNone(rejected["amount"])
        self.assertIsNone(rejected["rate"])
        self.assertEqual(rejected["currency"], "USD")
        self.assertEqual(rejected["source"], "sandbox")
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected quote_fx")

    def test_does_not_call_the_network(self) -> None:
        source = inspect.getsource(quote_mod) + inspect.getsource(tool_mod)
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
        with _network_forbidden():
            result = quote_fx(1000, "JPY", "USD")
        self.assertEqual(result["amount"], 6.7)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("quote_fx opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
