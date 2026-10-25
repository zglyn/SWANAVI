"""Dynamic currency conversion: pay the merchant currency.

These tests stay in-process. They do not charge a card, call a terminal, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.dcc import AGENTCORE_TOOL, TOOL_SPEC, handler, refuse_dcc
from booking.assist.dcc import dcc as dcc_mod
from booking.assist.dcc import tool as tool_mod


class RefuseDccTests(unittest.TestCase):
    def test_local_currency_is_accepted(self) -> None:
        result = refuse_dcc(18.5, "EUR", 20, "eur")
        self.assertEqual(
            result,
            {
                "payAmount": 18.5,
                "payCurrency": "EUR",
                "refused": False,
                "reason": "local_currency",
            },
        )
        self.assertIs(result["refused"], False)
        self.assertIsInstance(result["payAmount"], float)
        self.assertEqual(
            refuse_dcc(
                merchantAmount=18.5,
                merchantCurrency="EUR",
                offeredAmount=20,
                offeredCurrency="eur",
            ),
            result,
        )
        same_bill = {
            "merchantAmount": 18.5,
            "merchantCurrency": "EUR",
            "offeredAmount": 20,
            "offeredCurrency": "EUR",
        }
        self.assertEqual(refuse_dcc(same_bill), result)

    def test_usd_offer_on_a_jpy_bill_is_refused(self) -> None:
        result = refuse_dcc(1500, "JPY", 12, "USD")
        self.assertEqual(
            result,
            {
                "payAmount": 1500,
                "payCurrency": "JPY",
                "refused": True,
                "reason": "dcc_refused",
            },
        )
        self.assertIs(result["refused"], True)
        self.assertIsInstance(result["payAmount"], int)
        self.assertNotEqual(result["payAmount"], 12)

        converted_looking = refuse_dcc(1000, "JPY", 6.7, "USD")
        self.assertEqual(converted_looking["payAmount"], 1000)
        self.assertEqual(converted_looking["payCurrency"], "JPY")
        self.assertEqual(converted_looking["reason"], "dcc_refused")
        self.assertNotEqual(converted_looking["payAmount"], 6.7)

    def test_invalid_amount(self) -> None:
        cases = [
            refuse_dcc(-1, "JPY", 12, "USD"),
            refuse_dcc(1500, "JPY", -12, "USD"),
            refuse_dcc(None, "JPY", 12, "USD"),
            refuse_dcc(1500, "JPY", None, "USD"),
            refuse_dcc("nope", "JPY", 12, "USD"),
            refuse_dcc(True, "JPY", 12, "USD"),
            refuse_dcc(float("nan"), "JPY", 12, "USD"),
            refuse_dcc(float("inf"), "EUR", 1, "USD"),
            refuse_dcc({"merchantAmount": {}, "merchantCurrency": "JPY", "offeredAmount": 12, "offeredCurrency": "USD"}),
            refuse_dcc({"merchantCurrency": "JPY", "offeredAmount": 12, "offeredCurrency": "USD"}),
            refuse_dcc(),
            refuse_dcc(None),
            refuse_dcc("not-json"),
            refuse_dcc([]),
        ]
        for result in cases:
            self.assertEqual(result["payAmount"], 0)
            self.assertIs(result["refused"], True)
            self.assertEqual(result["reason"], "invalid_amount")
            self.assertEqual(set(result), {"payAmount", "payCurrency", "refused", "reason"})
            self.assertIsInstance(result["payAmount"], int)

        priced = refuse_dcc(-5, "JPY", 12, "USD")
        self.assertEqual(priced["payCurrency"], "JPY")

    def test_jpy_rounds_to_zero_decimals(self) -> None:
        local = refuse_dcc("1500.5", "jpy", "1500", "JPY")
        self.assertEqual(local["payAmount"], 1501)
        self.assertEqual(local["payCurrency"], "jpy")
        self.assertIs(local["refused"], False)
        self.assertEqual(local["reason"], "local_currency")

        down = refuse_dcc("1500.4", "JPY", "1", "JPY")
        self.assertEqual(down["payAmount"], 1500)
        self.assertEqual(down["reason"], "local_currency")

        refused = refuse_dcc("1500.5", "JPY", "12.99", "USD")
        self.assertEqual(refused["payAmount"], 1501)
        self.assertEqual(refused["payCurrency"], "JPY")
        self.assertEqual(refused["reason"], "dcc_refused")
        self.assertNotEqual(refused["payAmount"], 12.99)

    def test_other_currencies_round_to_two_decimals(self) -> None:
        up = refuse_dcc("10.005", "USD", "10.005", "USD")
        self.assertEqual(up["payAmount"], 10.01)
        self.assertEqual(up["reason"], "local_currency")
        self.assertIs(up["refused"], False)

        down = refuse_dcc("10.004", "USD", "1", "usd")
        self.assertEqual(down["payAmount"], 10)
        self.assertIsInstance(down["payAmount"], int)
        self.assertEqual(down["payCurrency"], "USD")

        whole = refuse_dcc("99.995", "EUR", "1", "GBP")
        self.assertEqual(whole["payAmount"], 100)
        self.assertEqual(whole["payCurrency"], "EUR")
        self.assertEqual(whole["reason"], "dcc_refused")

    def test_zero_is_a_valid_amount(self) -> None:
        local = refuse_dcc(0, "USD", 0, "USD")
        self.assertEqual(local["payAmount"], 0)
        self.assertIs(local["refused"], False)
        self.assertEqual(local["reason"], "local_currency")

        refused = refuse_dcc(0, "JPY", 12, "USD")
        self.assertEqual(refused["payAmount"], 0)
        self.assertIs(refused["refused"], True)
        self.assertEqual(refused["reason"], "dcc_refused")
        self.assertEqual(refused["payCurrency"], "JPY")

    def test_tool_spec_is_refuse_dcc(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "refuse_dcc")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["merchantAmount", "merchantCurrency", "offeredAmount", "offeredCurrency"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["payAmount", "payCurrency", "refused", "reason"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("pay the merchant's currency", description)
        self.assertIn("dcc_refused", description)
        self.assertIn("local_currency", description)
        self.assertIn("invalid_amount", description)
        self.assertIn("Do not convert", description)
        self.assertIn("no live terminal", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "refuse_dcc")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_refuse_dcc(self) -> None:
        payload = {
            "merchantAmount": 1500,
            "merchantCurrency": "JPY",
            "offeredAmount": 12,
            "offeredCurrency": "USD",
        }
        self.assertEqual(handler(payload), refuse_dcc(payload))
        self.assertEqual(handler(json.dumps(payload)), refuse_dcc(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___refuse_dcc"))
        self.assertEqual(wrapped["payAmount"], 1500)
        self.assertEqual(wrapped["reason"], "dcc_refused")
        self.assertIs(wrapped["refused"], True)

        rejected = handler(payload, _AgentCoreContext("quote_fx"))
        self.assertEqual(rejected["payAmount"], 0)
        self.assertEqual(rejected["payCurrency"], "JPY")
        self.assertIs(rejected["refused"], True)
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected refuse_dcc")

    def test_does_not_charge_or_call_the_network(self) -> None:
        source = inspect.getsource(dcc_mod) + inspect.getsource(tool_mod)
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
            result = refuse_dcc(1500, "JPY", 12, "USD")
        self.assertEqual(result["payAmount"], 1500)
        self.assertEqual(result["reason"], "dcc_refused")


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("refuse_dcc opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
