"""Hotel incidental hold: release the uncaptured remainder after checkout.

These tests stay in-process. They do not capture, charge a card, or open a network.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.hold import AGENTCORE_TOOL, TOOL_SPEC, handler, incidental_hold
from booking.assist.hold import hold as hold_mod
from booking.assist.hold import tool as tool_mod

_CHECKOUT = "2026-11-06T11:00:00Z"
_RELEASE = "2026-11-13T11:00:00Z"
_FIELDS = {
    "authorizedHold",
    "capturedAmount",
    "releaseAmount",
    "currency",
    "releaseBy",
    "payAmount",
    "reason",
}


def _call(authorized, captured, currency="USD", checkout=_CHECKOUT) -> dict:
    return incidental_hold(
        authorizedHold=authorized,
        capturedAmount=captured,
        currency=currency,
        checkoutAt=checkout,
    )


class IncidentalHoldTests(unittest.TestCase):
    def test_hold_200_capture_40_releases_160(self) -> None:
        result = _call(200, 40)
        self.assertEqual(
            result,
            {
                "authorizedHold": 200,
                "capturedAmount": 40,
                "releaseAmount": 160,
                "currency": "USD",
                "releaseBy": _RELEASE,
                "payAmount": 40,
                "reason": "held",
            },
        )

    def test_capture_equal_to_the_hold_releases_nothing(self) -> None:
        result = _call(200, 200)
        self.assertEqual(result["releaseAmount"], 0)
        self.assertEqual(result["payAmount"], 200)
        self.assertEqual(result["reason"], "captured_in_full")
        self.assertEqual(result["releaseBy"], _RELEASE)
        self.assertEqual(result["authorizedHold"], 200)
        self.assertEqual(result["capturedAmount"], 200)

    def test_capture_250_on_a_200_hold_is_over_capture(self) -> None:
        result = _call(200, 250)
        self.assertEqual(result["authorizedHold"], 200)
        self.assertEqual(result["capturedAmount"], 250)
        self.assertEqual(result["releaseAmount"], 0)
        self.assertEqual(result["payAmount"], 200)
        self.assertEqual(result["reason"], "over_capture")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["releaseBy"], _RELEASE)

    def test_nothing_captured_releases_the_whole_hold(self) -> None:
        result = _call(200, 0)
        self.assertEqual(result["releaseAmount"], 200)
        self.assertEqual(result["payAmount"], 0)
        self.assertEqual(result["reason"], "held")
        self.assertEqual(result["releaseBy"], _RELEASE)

    def test_release_by_is_checkout_plus_seven_days(self) -> None:
        year_end = incidental_hold(200, 40, "USD", "2026-12-28T15:30:00Z")
        self.assertEqual(year_end["releaseBy"], "2027-01-04T15:30:00Z")
        self.assertEqual(year_end["reason"], "held")

        offset = incidental_hold(200, 40, "EUR", "2026-11-06T20:00:00+09:00")
        self.assertEqual(offset["releaseBy"], "2026-11-13T11:00:00Z")

        fraction = incidental_hold(200, 40, "USD", "2026-11-06T11:00:00.5Z")
        self.assertEqual(fraction["releaseBy"], "2026-11-13T11:00:00.5Z")

    def test_rounds_half_up_to_two_decimals(self) -> None:
        result = _call("10.005", "0.004")
        self.assertEqual(result["authorizedHold"], 10.01)
        self.assertEqual(result["capturedAmount"], 0)
        self.assertEqual(result["releaseAmount"], 10.01)
        self.assertEqual(result["payAmount"], 0)
        self.assertEqual(result["reason"], "held")

        half = _call("1.005", "1.005")
        self.assertEqual(half["authorizedHold"], 1.01)
        self.assertEqual(half["capturedAmount"], 1.01)
        self.assertEqual(half["releaseAmount"], 0)
        self.assertEqual(half["payAmount"], 1.01)
        self.assertEqual(half["reason"], "captured_in_full")

    def test_jpy_rounds_to_zero_decimals(self) -> None:
        partial = _call("200.5", "40.4", "JPY")
        self.assertEqual(partial["authorizedHold"], 201)
        self.assertEqual(partial["capturedAmount"], 40)
        self.assertEqual(partial["releaseAmount"], 161)
        self.assertEqual(partial["payAmount"], 40)
        self.assertEqual(partial["reason"], "held")

        over = _call("200.4", "200.5", "jpy")
        self.assertEqual(over["currency"], "jpy")
        self.assertEqual(over["authorizedHold"], 200)
        self.assertEqual(over["capturedAmount"], 201)
        self.assertEqual(over["releaseAmount"], 0)
        self.assertEqual(over["payAmount"], 200)
        self.assertEqual(over["reason"], "over_capture")

    def test_negative_amounts_are_invalid(self) -> None:
        cases = [
            _call(-1, 40),
            _call(200, -0.01),
            _call("-5.126", "-1"),
            incidental_hold(authorizedHold=-5, capturedAmount=40, currency="USD", checkoutAt=_CHECKOUT),
        ]
        for result in cases:
            self.assertEqual(result["releaseAmount"], 0)
            self.assertEqual(result["payAmount"], 0)
            self.assertIsNone(result["releaseBy"])
            self.assertEqual(result["reason"], "invalid_amount")
            self.assertEqual(set(result), _FIELDS)

        echoed = _call("-5.126", "40.00")
        self.assertEqual(echoed["authorizedHold"], -5.13)
        self.assertEqual(echoed["capturedAmount"], 40)
        self.assertEqual(echoed["releaseAmount"], 0)
        self.assertEqual(echoed["reason"], "invalid_amount")

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            incidental_hold(),
            incidental_hold(None),
            incidental_hold("not-json"),
            incidental_hold([]),
            incidental_hold("{"),
            incidental_hold("[1]"),
            incidental_hold({"capturedAmount": 40, "currency": "USD", "checkoutAt": _CHECKOUT}),
            incidental_hold({"authorizedHold": True, "capturedAmount": 40, "currency": "USD"}),
            incidental_hold({"authorizedHold": float("nan"), "capturedAmount": 40, "currency": "USD"}),
            incidental_hold({"authorizedHold": float("inf"), "capturedAmount": 1, "currency": "USD"}),
            incidental_hold({"authorizedHold": {}, "capturedAmount": 1}),
            _call(200, "nope"),
        ]
        for result in cases:
            self.assertEqual(set(result), _FIELDS)
            self.assertEqual(result["releaseAmount"], 0)
            self.assertEqual(result["payAmount"], 0)
            self.assertEqual(result["reason"], "invalid_amount")
            self.assertIsNone(result["releaseBy"])

    def test_unreadable_checkout_keeps_the_money_and_nulls_release_by(self) -> None:
        result = _call(200, 40, checkout="2026-11-06")
        self.assertEqual(result["releaseAmount"], 160)
        self.assertEqual(result["payAmount"], 40)
        self.assertEqual(result["reason"], "held")
        self.assertIsNone(result["releaseBy"])

        blank = _call(200, 250, checkout="  ")
        self.assertEqual(blank["reason"], "over_capture")
        self.assertEqual(blank["payAmount"], 200)
        self.assertIsNone(blank["releaseBy"])

    def test_currency_is_passed_through(self) -> None:
        result = _call(200, 40, " usd ")
        self.assertEqual(result["currency"], "usd")
        self.assertEqual(result["releaseAmount"], 160)

    def test_payload_shapes(self) -> None:
        payload = {
            "authorizedHold": 200,
            "capturedAmount": 40,
            "currency": "USD",
            "checkoutAt": _CHECKOUT,
        }
        self.assertEqual(incidental_hold(payload)["releaseAmount"], 160)
        self.assertEqual(incidental_hold(json.dumps(payload))["reason"], "held")
        wrapped = incidental_hold({"arguments": payload})
        self.assertEqual(wrapped["payAmount"], 40)
        nested = incidental_hold({"input": payload})
        self.assertEqual(nested["releaseBy"], _RELEASE)

    def test_tool_spec_is_incidental_hold(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "incidental_hold")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["authorizedHold", "capturedAmount", "currency", "checkoutAt"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            [
                "authorizedHold",
                "capturedAmount",
                "releaseAmount",
                "currency",
                "releaseBy",
                "payAmount",
                "reason",
            ],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("hold is not a charge", description)
        self.assertIn("does not capture or charge", description)
        self.assertIn("7 days", description)
        self.assertIn("over_capture", description)
        self.assertIn("captured_in_full", description)
        self.assertIn("invalid_amount", description)
        self.assertIn("JPY", description)
        self.assertIn("no card network", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "incidental_hold")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_incidental_hold(self) -> None:
        payload = {
            "authorizedHold": 200,
            "capturedAmount": 40,
            "currency": "USD",
            "checkoutAt": _CHECKOUT,
        }
        self.assertEqual(handler(payload), incidental_hold(payload))
        self.assertEqual(handler(json.dumps(payload)), incidental_hold(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___incidental_hold"))
        self.assertEqual(wrapped["releaseAmount"], 160)
        self.assertEqual(wrapped["reason"], "held")

        nested = handler({"input": payload})
        self.assertEqual(nested["payAmount"], 40)

        rejected = handler(payload, _AgentCoreContext("authorize_spend"))
        self.assertEqual(rejected["releaseAmount"], 0)
        self.assertEqual(rejected["payAmount"], 0)
        self.assertIsNone(rejected["releaseBy"])
        self.assertEqual(rejected["authorizedHold"], 200)
        self.assertEqual(rejected["capturedAmount"], 40)
        self.assertEqual(
            rejected["reason"],
            "unsupported AgentCore tool; expected incidental_hold",
        )

    def test_does_not_charge_or_call_the_network(self) -> None:
        source = inspect.getsource(hold_mod) + inspect.getsource(tool_mod)
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
            "braintree",
            "adyen",
            "authorize_spend(",
            "booking.master",
            "booking.guard",
            "datetime.now",
            "date.today",
        ):
            self.assertNotIn(banned, source)
        with _network_forbidden():
            result = _call(200, 40)
        self.assertEqual(result["releaseAmount"], 160)
        self.assertEqual(result["reason"], "held")


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("incidental_hold opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
