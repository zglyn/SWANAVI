"""Cash decision: card, or a sandbox quote of the cash into the trip currency.

These tests stay in-process. They do not call an ATM, open a socket, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest
from decimal import Decimal

from booking.assist.cash import AGENTCORE_TOOL, TOOL_SPEC, cash_needed, handler
from booking.assist.cash import cash as cash_mod
from booking.assist.cash import tool as tool_mod


def _merchant(name, accepts_card, amount, currency) -> dict:
    return {
        "merchant": {
            "name": name,
            "acceptsCard": accepts_card,
            "amount": amount,
            "currency": currency,
        }
    }


class CashNeededTests(unittest.TestCase):
    def test_card_accepted_needs_no_cash(self) -> None:
        result = cash_needed(
            {"name": "Cafe", "acceptsCard": True, "amount": 1200, "currency": "JPY"},
            tripCurrency="USD",
        )
        self.assertEqual(
            result,
            {
                "merchant": "Cafe",
                "action": "pay_card",
                "cashAmount": 0,
                "cashCurrency": "JPY",
                "tripAmount": 0,
                "tripCurrency": "USD",
                "reason": "card_accepted",
            },
        )

    def test_1000_jpy_cash_is_6_70_usd(self) -> None:
        result = cash_needed(
            merchant={"name": "Market", "acceptsCard": False, "amount": 1000, "currency": "JPY"}
        )
        self.assertEqual(result["merchant"], "Market")
        self.assertEqual(result["action"], "withdraw_cash")
        self.assertEqual(result["cashAmount"], 1000)
        self.assertEqual(result["cashCurrency"], "JPY")
        self.assertEqual(result["tripAmount"], 6.7)
        self.assertEqual(f"{result['tripAmount']:.2f}", "6.70")
        self.assertEqual(result["tripCurrency"], "USD")
        self.assertEqual(result["reason"], "quoted")

        same = cash_needed({**_merchant("Market", False, 1000, "jpy"), "tripCurrency": "usd"})
        self.assertEqual(same["tripAmount"], 6.7)
        self.assertEqual(same["cashCurrency"], "JPY")
        self.assertEqual(same["tripCurrency"], "USD")

    def test_unknown_currency_returns_null_trip_amount(self) -> None:
        result = cash_needed(_merchant("Kiosk", False, 1000, "XYZ"))
        self.assertEqual(result["merchant"], "Kiosk")
        self.assertEqual(result["action"], "withdraw_cash")
        self.assertEqual(result["cashAmount"], 1000)
        self.assertEqual(result["cashCurrency"], "XYZ")
        self.assertIsNone(result["tripAmount"])
        self.assertEqual(result["tripCurrency"], "USD")
        self.assertEqual(result["reason"], "unknown_currency")

        other_way = cash_needed(
            {"name": "Kiosk", "acceptsCard": False, "amount": 10, "currency": "USD"},
            tripCurrency="ABC",
        )
        self.assertEqual(other_way["action"], "withdraw_cash")
        self.assertEqual(other_way["cashAmount"], 10)
        self.assertIsNone(other_way["tripAmount"])
        self.assertEqual(other_way["tripCurrency"], "ABC")
        self.assertEqual(other_way["reason"], "unknown_currency")

    def test_negative_amount_is_invalid(self) -> None:
        result = cash_needed(_merchant("Cafe", False, -1000, "JPY"))
        self.assertEqual(result["reason"], "invalid_amount")
        self.assertEqual(result["cashAmount"], 0)
        self.assertIsNone(result["tripAmount"])
        self.assertEqual(result["action"], "")
        self.assertEqual(result["merchant"], "Cafe")

        on_card = cash_needed(_merchant("Cafe", True, -5, "USD"))
        self.assertEqual(on_card["reason"], "invalid_amount")
        self.assertEqual(on_card["cashAmount"], 0)
        self.assertIsNone(on_card["tripAmount"])

    def test_rates_match_the_fx_table_and_cross_into_the_trip_currency(self) -> None:
        self.assertEqual(
            cash_mod.RATES_INTO_USD,
            {
                "USD": Decimal("1"),
                "EUR": Decimal("1.08"),
                "GBP": Decimal("1.27"),
                "JPY": Decimal("0.0067"),
            },
        )
        eur = cash_needed(_merchant("Shop", False, 10, "EUR"))
        self.assertEqual(eur["tripAmount"], 10.8)
        self.assertEqual(f"{eur['tripAmount']:.2f}", "10.80")
        self.assertEqual(eur["tripCurrency"], "USD")

        gbp = cash_needed(_merchant("Shop", False, 2, "GBP"))
        self.assertEqual(gbp["tripAmount"], 2.54)

        to_eur = cash_needed(
            {"name": "Market", "acceptsCard": False, "amount": 1000, "currency": "JPY"},
            tripCurrency="EUR",
        )
        self.assertEqual(to_eur["tripAmount"], 6.2)
        self.assertEqual(f"{to_eur['tripAmount']:.2f}", "6.20")
        self.assertEqual(to_eur["tripCurrency"], "EUR")

        to_jpy = cash_needed(
            {"name": "Shop", "acceptsCard": False, "amount": 10, "currency": "USD"},
            tripCurrency="JPY",
        )
        self.assertEqual(to_jpy["cashAmount"], 10)
        self.assertEqual(to_jpy["tripAmount"], 1493)
        self.assertIsInstance(to_jpy["tripAmount"], int)

    def test_jpy_cash_rounds_half_up_to_zero_decimals(self) -> None:
        result = cash_needed(_merchant("Market", False, "1000.5", "JPY"), tripCurrency="JPY")
        self.assertEqual(result["cashAmount"], 1001)
        self.assertEqual(result["tripAmount"], 1001)
        self.assertEqual(result["reason"], "quoted")

    def test_card_accepted_does_not_quote_an_unknown_currency(self) -> None:
        result = cash_needed(_merchant("Cafe", True, 50, "XYZ"))
        self.assertEqual(result["action"], "pay_card")
        self.assertEqual(result["cashAmount"], 0)
        self.assertEqual(result["tripAmount"], 0)
        self.assertEqual(result["cashCurrency"], "XYZ")
        self.assertEqual(result["reason"], "card_accepted")

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            cash_needed(),
            cash_needed(None),
            cash_needed("not-json"),
            cash_needed([]),
            cash_needed("{"),
            cash_needed({"merchant": {"name": "Cafe", "acceptsCard": False, "amount": "nope", "currency": "JPY"}}),
            cash_needed({"merchant": {"name": "Cafe", "acceptsCard": False, "amount": True, "currency": "USD"}}),
            cash_needed({"merchant": {"name": "Cafe", "acceptsCard": False, "currency": "USD"}}),
            cash_needed({"merchant": {"acceptsCard": False, "amount": float("nan"), "currency": "USD"}}),
            cash_needed({"merchant": {"acceptsCard": False, "amount": float("inf"), "currency": "EUR"}}),
        ]
        for result in cases:
            self.assertEqual(
                set(result),
                {
                    "merchant",
                    "action",
                    "cashAmount",
                    "cashCurrency",
                    "tripAmount",
                    "tripCurrency",
                    "reason",
                },
            )
            self.assertEqual(result["cashAmount"], 0)
            self.assertIsNone(result["tripAmount"])
            self.assertEqual(result["reason"], "invalid_amount")

    def test_tool_spec_is_cash_needed(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "cash_needed")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["merchant"])
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["properties"]["merchant"]["required"],
            ["name", "acceptsCard", "amount", "currency"],
        )
        self.assertEqual(TOOL_SPEC["inputSchema"]["properties"]["tripCurrency"]["default"], "USD")
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            [
                "merchant",
                "action",
                "cashAmount",
                "cashCurrency",
                "tripAmount",
                "tripCurrency",
                "reason",
            ],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("cash_needed", description)
        self.assertIn("AgentCore", description)
        self.assertIn("USD 1", description)
        self.assertIn("EUR 1.08", description)
        self.assertIn("GBP 1.27", description)
        self.assertIn("JPY 0.0067", description)
        self.assertIn("6.70 USD", description)
        self.assertIn("unknown_currency", description)
        self.assertIn("invalid_amount", description)
        self.assertIn("no ATM", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "cash_needed")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_cash_needed(self) -> None:
        payload = _merchant("Market", False, 1000, "JPY")
        self.assertEqual(handler(payload), cash_needed(payload))
        self.assertEqual(handler(json.dumps(payload)), cash_needed(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___cash_needed"))
        self.assertEqual(wrapped["tripAmount"], 6.7)
        self.assertEqual(wrapped["action"], "withdraw_cash")

        nested = handler({"input": payload})
        self.assertEqual(nested["tripAmount"], 6.7)

        rejected = handler(payload, _AgentCoreContext("quote_fx"))
        self.assertEqual(rejected["action"], "")
        self.assertEqual(rejected["cashAmount"], 0)
        self.assertIsNone(rejected["tripAmount"])
        self.assertEqual(rejected["merchant"], "Market")
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected cash_needed")

    def test_does_not_call_the_network_or_an_atm(self) -> None:
        source = inspect.getsource(cash_mod) + inspect.getsource(tool_mod)
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
            "quote_fx",
            "booking.assist.fx",
        ):
            self.assertNotIn(banned, source)
        with _network_forbidden():
            result = cash_needed(_merchant("Market", False, 1000, "JPY"))
        self.assertEqual(result["tripAmount"], 6.7)
        self.assertEqual(f"{result['tripAmount']:.2f}", "6.70")


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("cash_needed opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
