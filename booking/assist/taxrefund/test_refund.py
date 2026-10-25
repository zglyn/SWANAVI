"""Tax refund quote: Japan 10%, France 20%, minimums, and a missed departure.

These tests stay in-process. They do not call a tax authority, open a socket, or call AWS.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.taxrefund import AGENTCORE_TOOL, TOOL_SPEC, handler, tax_refund
from booking.assist.taxrefund import refund as refund_mod
from booking.assist.taxrefund import tool as tool_mod

DEPART = "2026-11-06T16:00:00Z"
BEFORE = "2026-11-06T15:00:00Z"
AFTER = "2026-11-06T16:00:01Z"

_OUTPUT_KEYS = {"status", "refundAmount", "refundCurrency", "eligibleSpend", "claimBefore", "reason"}


def _quote(**overrides) -> dict:
    payload = {
        "country": "Japan",
        "purchases": [{"amount": 10000, "currency": "JPY", "eligible": True}],
        "departAt": DEPART,
        "now": BEFORE,
    }
    payload.update(overrides)
    return payload


class TaxRefundTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_japan_10000_jpy_refunds_1000(self) -> None:
        result = tax_refund(**_quote())

        self.assertEqual(
            result,
            {
                "status": "eligible",
                "refundAmount": 1000,
                "refundCurrency": "JPY",
                "eligibleSpend": 10000,
                "claimBefore": DEPART,
                "reason": "quoted",
            },
        )
        self.assertEqual(tax_refund(_quote()), result)

    def test_japan_4000_jpy_is_too_small(self) -> None:
        result = tax_refund(**_quote(purchases=[{"amount": 4000, "currency": "JPY", "eligible": True}]))

        self.assertEqual(
            result,
            {
                "status": "too_small",
                "refundAmount": 0,
                "refundCurrency": "JPY",
                "eligibleSpend": 4000,
                "claimBefore": None,
                "reason": "below_minimum",
            },
        )

    def test_france_100_eur_refunds_20(self) -> None:
        result = tax_refund(
            **_quote(
                country="France",
                purchases=[{"amount": 100, "currency": "EUR", "eligible": True}],
            )
        )

        self.assertEqual(
            result,
            {
                "status": "eligible",
                "refundAmount": 20,
                "refundCurrency": "EUR",
                "eligibleSpend": 100,
                "claimBefore": DEPART,
                "reason": "quoted",
            },
        )

    def test_after_departure_is_missed_and_still_shows_the_refund(self) -> None:
        result = tax_refund(**_quote(now=AFTER))

        self.assertEqual(
            result,
            {
                "status": "missed",
                "refundAmount": 1000,
                "refundCurrency": "JPY",
                "eligibleSpend": 10000,
                "claimBefore": DEPART,
                "reason": "departed",
            },
        )

    def test_sums_only_eligible_lines_in_the_refund_currency(self) -> None:
        result = tax_refund(
            **_quote(
                purchases=[
                    {"amount": 6000, "currency": "JPY", "eligible": True},
                    {"amount": 4000, "currency": "jpy", "eligible": True},
                    {"amount": 9000, "currency": "JPY", "eligible": False},
                    {"amount": 80, "currency": "EUR", "eligible": True},
                    {"amount": "500", "currency": "USD", "eligible": True},
                ]
            )
        )

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["eligibleSpend"], 10000)
        self.assertEqual(result["refundAmount"], 1000)
        self.assertEqual(result["refundCurrency"], "JPY")

    def test_japan_minimum_is_5000_and_jpy_rounds_half_up(self) -> None:
        at_minimum = tax_refund(**_quote(purchases=[{"amount": 5000, "currency": "JPY", "eligible": True}]))
        self.assertEqual(at_minimum["status"], "eligible")
        self.assertEqual(at_minimum["eligibleSpend"], 5000)
        self.assertEqual(at_minimum["refundAmount"], 500)

        rounded = tax_refund(**_quote(purchases=[{"amount": 10005, "currency": "JPY", "eligible": True}]))
        self.assertEqual(rounded["eligibleSpend"], 10005)
        self.assertEqual(rounded["refundAmount"], 1001)

    def test_france_rounds_eur_to_two_decimals(self) -> None:
        result = tax_refund(
            **_quote(
                country="fr",
                purchases=[{"amount": "100.13", "currency": "EUR", "eligible": True}],
            )
        )

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["refundCurrency"], "EUR")
        self.assertEqual(result["eligibleSpend"], 100.13)
        self.assertEqual(result["refundAmount"], 20.03)

    def test_other_country_is_none(self) -> None:
        result = tax_refund(
            **_quote(
                country="Germany",
                purchases=[{"amount": 10000, "currency": "EUR", "eligible": True}],
            )
        )

        self.assertEqual(
            result,
            {
                "status": "none",
                "refundAmount": 0,
                "refundCurrency": "",
                "eligibleSpend": 0,
                "claimBefore": None,
                "reason": "unsupported_country",
            },
        )

    def test_departure_instant_is_still_eligible(self) -> None:
        result = tax_refund(**_quote(now=DEPART))

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["refundAmount"], 1000)
        self.assertEqual(result["claimBefore"], DEPART)

    def test_spend_under_the_minimum_stays_too_small_after_departure(self) -> None:
        result = tax_refund(
            **_quote(
                purchases=[{"amount": 4000, "currency": "JPY", "eligible": True}],
                now=AFTER,
            )
        )

        self.assertEqual(result["status"], "too_small")
        self.assertEqual(result["refundAmount"], 0)
        self.assertIsNone(result["claimBefore"])

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            tax_refund(),
            tax_refund(None),
            tax_refund("not-json"),
            tax_refund("{"),
            tax_refund([]),
            tax_refund({"purchases": "nope", "country": "Japan", "departAt": DEPART, "now": BEFORE}),
            tax_refund(**_quote(departAt="tomorrow")),
            tax_refund(**_quote(purchases=[{"amount": -1, "currency": "JPY", "eligible": True}])),
        ]
        for result in cases:
            self.assertEqual(set(result), _OUTPUT_KEYS)
            self.assertIn(result["status"], {"none", "too_small"})
            self.assertEqual(result["refundAmount"], 0)

    def test_tool_spec_is_tax_refund(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "tax_refund")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["country", "purchases", "departAt", "now"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["status", "refundAmount", "refundCurrency", "eligibleSpend", "claimBefore", "reason"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"],
            ["eligible", "too_small", "missed", "none"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("tax_refund", description)
        self.assertIn("5000", description)
        self.assertIn("not tax advice", description)
        self.assertIn("no tax-authority API", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "tax_refund")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_tax_refund(self) -> None:
        payload = _quote()
        self.assertEqual(handler(payload), tax_refund(payload))
        self.assertEqual(handler(json.dumps(payload)), tax_refund(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___tax_refund"))
        self.assertEqual(wrapped["refundAmount"], 1000)
        self.assertEqual(wrapped["status"], "eligible")

        rejected = handler(payload, _AgentCoreContext("quote_fx"))
        self.assertEqual(rejected["status"], "none")
        self.assertEqual(rejected["refundAmount"], 0)
        self.assertIsNone(rejected["claimBefore"])
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected tax_refund")

    def test_sandbox_source_has_no_network_client(self) -> None:
        source = inspect.getsource(refund_mod) + inspect.getsource(tool_mod)
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


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("tax_refund opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
