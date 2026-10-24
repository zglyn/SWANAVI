"""Spend guard: pay the authorized amount, never the extra.

These tests stay in-process. They do not charge a card, call a ledger, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.guard.spend import AGENTCORE_TOOL, TOOL_SPEC, authorize_spend, handler
from booking.guard.spend import spend as spend_mod
from booking.guard.spend import tool as tool_mod


def _call(authorized, requested, **extra) -> dict:
    payload = {
        "segmentId": "hotel-1",
        "currency": "USD",
        "authorizedAmount": authorized,
        "requestedAmount": requested,
        "reason": "hotel_rate",
    }
    payload.update(extra)
    return authorize_spend(payload)


class AuthorizeSpendTests(unittest.TestCase):
    def test_ten_authorized_twelve_requested_pays_ten(self) -> None:
        result = _call(10, 12)
        self.assertEqual(
            result,
            {
                "segmentId": "hotel-1",
                "decision": "pay",
                "payAmount": 10,
                "currency": "USD",
                "reason": "over_capture_rejected",
            },
        )

    def test_ten_authorized_eight_requested_pays_eight(self) -> None:
        result = _call(10, 8)
        self.assertEqual(
            result,
            {
                "segmentId": "hotel-1",
                "decision": "pay",
                "payAmount": 8,
                "currency": "USD",
                "reason": "hotel_rate",
            },
        )

    def test_equal_amounts_pay_the_requested_amount(self) -> None:
        result = _call(10, 10)
        self.assertEqual(result["decision"], "pay")
        self.assertEqual(result["payAmount"], 10)
        self.assertEqual(result["reason"], "hotel_rate")

    def test_decimal_strings_follow_the_same_limit(self) -> None:
        over = _call("10.00", "12.00")
        self.assertEqual(over["decision"], "pay")
        self.assertEqual(over["payAmount"], "10.00")
        self.assertEqual(over["reason"], "over_capture_rejected")

        within = _call("10.00", "8.50")
        self.assertEqual(within["decision"], "pay")
        self.assertEqual(within["payAmount"], "8.50")
        self.assertEqual(within["reason"], "hotel_rate")

    def test_bad_amount_rejects(self) -> None:
        cases = [
            _call(-1, 8),
            _call(10, -1),
            _call(None, 8),
            _call(10, None),
            authorize_spend({"segmentId": "hotel-1", "currency": "USD", "requestedAmount": 8}),
            authorize_spend({"segmentId": "hotel-1", "currency": "USD", "authorizedAmount": 10}),
            authorize_spend({"authorizedAmount": "nope", "requestedAmount": 8, "segmentId": "hotel-1", "currency": "USD"}),
            authorize_spend({"authorizedAmount": True, "requestedAmount": 8, "segmentId": "hotel-1", "currency": "USD"}),
            authorize_spend({"authorizedAmount": float("nan"), "requestedAmount": 8}),
            authorize_spend({"authorizedAmount": float("inf"), "requestedAmount": 1}),
            authorize_spend(),
            authorize_spend(None),
            authorize_spend("not-json"),
            authorize_spend([]),
            authorize_spend({"authorizedAmount": {}, "requestedAmount": 8}),
        ]
        for result in cases:
            self.assertEqual(result["decision"], "reject")
            self.assertEqual(result["payAmount"], 0)
            self.assertEqual(result["reason"], "invalid_amount")
            self.assertEqual(set(result), {"segmentId", "decision", "payAmount", "currency", "reason"})

    def test_zero_is_a_valid_amount(self) -> None:
        within = _call(10, 0)
        self.assertEqual(within["decision"], "pay")
        self.assertEqual(within["payAmount"], 0)
        self.assertEqual(within["reason"], "hotel_rate")

        over = _call(0, 10)
        self.assertEqual(over["decision"], "pay")
        self.assertEqual(over["payAmount"], 0)
        self.assertEqual(over["reason"], "over_capture_rejected")

    def test_tool_spec_is_authorize_spend(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "authorize_spend")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "currency", "authorizedAmount", "requestedAmount", "reason"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "decision", "payAmount", "currency", "reason"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["decision"]["enum"], ["pay", "reject"])
        description = TOOL_SPEC["description"]
        self.assertIn("Mastercard Agent Pay", description)
        self.assertIn("before a charge", description)
        self.assertIn("not asked to dispute the extra", description)
        self.assertIn("over_capture_rejected", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "authorize_spend")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_authorize_spend(self) -> None:
        payload = {
            "segmentId": "hotel-1",
            "currency": "USD",
            "authorizedAmount": 10,
            "requestedAmount": 12,
            "reason": "hotel_rate",
        }
        self.assertEqual(handler(payload), authorize_spend(payload))
        self.assertEqual(handler(json.dumps(payload)), authorize_spend(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___authorize_spend"))
        self.assertEqual(wrapped["payAmount"], 10)
        self.assertEqual(wrapped["reason"], "over_capture_rejected")

        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(rejected["decision"], "reject")
        self.assertEqual(rejected["payAmount"], 0)
        self.assertEqual(rejected["segmentId"], "hotel-1")
        self.assertEqual(rejected["currency"], "USD")
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected authorize_spend")

    def test_does_not_charge_or_call_the_network(self) -> None:
        source = inspect.getsource(spend_mod) + inspect.getsource(tool_mod)
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
            result = _call(10, 12)
        self.assertEqual(result["payAmount"], 10)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("authorize_spend opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
