"""Card choice: sandbox Mastercard fixtures, no live charge.

These tests stay in-process. They do not charge a card, call a ledger, or call AWS.
Cards in the fixtures are fake ids, not real card numbers.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.card import AGENTCORE_TOOL, TOOL_SPEC, handler, pick_card
from booking.assist.card import pick as pick_mod
from booking.assist.card import tool as tool_mod


def _japan_cards() -> list:
    return [
        {
            "id": "visa-japan",
            "network": "visa",
            "fxFeePercent": 0,
            "noFxCountries": ["Japan", "JP"],
        },
        {
            "id": "amex-japan",
            "network": "amex",
            "fxFeePercent": 0,
            "noFxCountries": ["Japan"],
        },
        {
            "id": "mc-japan",
            "network": "Mastercard",
            "fxFeePercent": 2.5,
            "noFxCountries": ["Japan"],
        },
        {
            "id": "mc-fee",
            "network": "mastercard",
            "fxFeePercent": 1,
            "noFxCountries": ["US"],
        },
    ]


def _call(merchant, amount, currency, cards) -> dict:
    return pick_card(
        {
            "merchantCountry": merchant,
            "amount": amount,
            "currency": currency,
            "cards": cards,
        }
    )


class PickCardTests(unittest.TestCase):
    def test_japan_no_fx_mastercard(self) -> None:
        result = _call("Japan", 1000, "JPY", _japan_cards())
        self.assertEqual(
            result,
            {
                "cardId": "mc-japan",
                "fxFeePercent": 0,
                "feeAmount": 0,
                "payAmount": 1000,
                "currency": "JPY",
                "reason": "no_fx_fee",
            },
        )
        self.assertNotIn("status", result)

        by_code = _call("JP", 1000, "JPY", _japan_cards())
        self.assertEqual(by_code["cardId"], "mc-japan")
        self.assertEqual(by_code["reason"], "no_fx_fee")
        self.assertEqual(by_code["feeAmount"], 0)
        self.assertEqual(by_code["fxFeePercent"], 0)

        listed_as_code = _call(
            "Japan",
            1000,
            "JPY",
            [
                {
                    "id": "mc-code",
                    "network": "MASTERCARD",
                    "fxFeePercent": 4,
                    "noFxCountries": ["JP"],
                }
            ],
        )
        self.assertEqual(listed_as_code["cardId"], "mc-code")
        self.assertEqual(listed_as_code["reason"], "no_fx_fee")
        self.assertEqual(listed_as_code["payAmount"], 1000)

    def test_three_percent_fallback_when_country_is_not_covered(self) -> None:
        cards = [
            {
                "id": "visa-zero",
                "network": "visa",
                "fxFeePercent": 0,
                "noFxCountries": ["Japan"],
            },
            {
                "id": "amex-one",
                "network": "Amex",
                "fxFeePercent": 1,
                "noFxCountries": ["JP"],
            },
            {
                "id": "mc-high",
                "network": "master card",
                "fxFeePercent": 5,
                "noFxCountries": ["France"],
            },
            {
                "id": "mc-standard",
                "network": "MasterCard",
                "fxFeePercent": 3,
                "noFxCountries": ["FR"],
            },
        ]
        result = _call("Japan", 100, "USD", cards)
        self.assertEqual(
            result,
            {
                "cardId": "mc-standard",
                "fxFeePercent": 3,
                "feeAmount": 3,
                "payAmount": 103,
                "currency": "USD",
                "reason": "lowest_fee",
            },
        )
        self.assertNotEqual(result["cardId"], "visa-zero")
        self.assertNotEqual(result["cardId"], "amex-one")

    def test_visa_only_needs_user(self) -> None:
        cards = [
            {
                "id": "visa-only",
                "network": "visa",
                "fxFeePercent": 0,
                "noFxCountries": ["Japan", "JP", "France", "US"],
            },
            {
                "id": "amex-only",
                "network": "american express",
                "fxFeePercent": 0,
                "noFxCountries": ["Japan"],
            },
        ]
        result = _call("JP", 1000, "JPY", cards)
        self.assertEqual(
            result,
            {
                "cardId": None,
                "fxFeePercent": None,
                "feeAmount": 0,
                "payAmount": 1000,
                "currency": "JPY",
                "reason": "no_mastercard",
                "status": "needs_user",
            },
        )
        self.assertNotIn(result["cardId"], {"visa-only", "amex-only"})

    def test_france_and_us_match_name_or_code(self) -> None:
        cards = [
            {
                "id": "mc-fr",
                "network": "mastercard",
                "fxFeePercent": 3,
                "noFxCountries": ["France"],
            },
            {
                "id": "mc-us",
                "network": "mastercard",
                "fxFeePercent": 3,
                "noFxCountries": ["US"],
            },
        ]
        france = _call("FR", 10, "EUR", cards)
        self.assertEqual(france["cardId"], "mc-fr")
        self.assertEqual(france["reason"], "no_fx_fee")
        self.assertEqual(france["feeAmount"], 0)
        self.assertEqual(france["payAmount"], 10)

        united = _call("US", 10, "USD", cards)
        self.assertEqual(united["cardId"], "mc-us")
        self.assertEqual(united["reason"], "no_fx_fee")
        self.assertEqual(united["fxFeePercent"], 0)
        self.assertEqual(united["payAmount"], 10)

    def test_negative_amount_is_invalid(self) -> None:
        result = _call("Japan", -5, "JPY", _japan_cards())
        self.assertEqual(
            result,
            {
                "cardId": None,
                "fxFeePercent": None,
                "feeAmount": 0,
                "payAmount": 0,
                "currency": "JPY",
                "reason": "invalid_amount",
            },
        )
        self.assertNotIn("status", result)

    def test_rounds_half_up_and_jpy_has_zero_decimals(self) -> None:
        yen = _call(
            "US",
            "100",
            "JPY",
            [
                {
                    "id": "mc-yen",
                    "network": "mastercard",
                    "fxFeePercent": "2.5",
                    "noFxCountries": [],
                }
            ],
        )
        self.assertEqual(yen["fxFeePercent"], 2.5)
        self.assertEqual(yen["feeAmount"], 3)
        self.assertEqual(yen["payAmount"], 103)
        self.assertEqual(yen["reason"], "lowest_fee")

        cents = _call(
            "US",
            "10",
            "USD",
            [
                {
                    "id": "mc-cents",
                    "network": "mastercard",
                    "fxFeePercent": "1.25",
                    "noFxCountries": [],
                }
            ],
        )
        self.assertEqual(cents["feeAmount"], 0.13)
        self.assertEqual(cents["payAmount"], 10.13)

        whole = _call(
            "US",
            "33.33",
            "EUR",
            [
                {
                    "id": "mc-eur",
                    "network": "mastercard",
                    "fxFeePercent": 3,
                    "noFxCountries": [],
                }
            ],
        )
        self.assertEqual(whole["feeAmount"], 1)
        self.assertEqual(whole["payAmount"], 34.33)

        half_yen = _call("Japan", "10.5", "jpy", _japan_cards())
        self.assertEqual(half_yen["feeAmount"], 0)
        self.assertEqual(half_yen["payAmount"], 11)
        self.assertEqual(half_yen["currency"], "jpy")

    def test_zero_amount_still_picks(self) -> None:
        result = _call(
            "Japan",
            0,
            "USD",
            [
                {
                    "id": "mc-zero",
                    "network": "mastercard",
                    "fxFeePercent": 3,
                    "noFxCountries": [],
                }
            ],
        )
        self.assertEqual(result["cardId"], "mc-zero")
        self.assertEqual(result["feeAmount"], 0)
        self.assertEqual(result["payAmount"], 0)
        self.assertEqual(result["reason"], "lowest_fee")

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            pick_card(),
            pick_card(None),
            pick_card("not-json"),
            pick_card([]),
            pick_card("{"),
            pick_card("[1]"),
            pick_card({"merchantCountry": "Japan", "currency": "JPY", "cards": []}),
            pick_card({"amount": "nope", "merchantCountry": "Japan", "currency": "USD", "cards": []}),
            pick_card({"amount": True, "merchantCountry": "JP", "cards": []}),
            pick_card({"amount": float("nan"), "currency": "USD", "cards": []}),
            pick_card({"amount": float("inf"), "merchantCountry": "US", "cards": []}),
            pick_card({"amount": {}, "cards": "nope"}),
            pick_card(merchantCountry="Japan", currency="JPY"),
        ]
        for result in cases:
            self.assertIsNone(result["cardId"])
            self.assertEqual(result["feeAmount"], 0)
            self.assertEqual(result["payAmount"], 0)
            self.assertEqual(result["reason"], "invalid_amount")
            self.assertEqual(
                set(result),
                {"cardId", "fxFeePercent", "feeAmount", "payAmount", "currency", "reason"},
            )

    def test_tool_spec_is_pick_card(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "pick_card")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["merchantCountry", "amount", "currency", "cards"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["cardId", "fxFeePercent", "feeAmount", "payAmount", "currency", "reason"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("no_fx_fee", description)
        self.assertIn("lowest_fee", description)
        self.assertIn("no_mastercard", description)
        self.assertIn("needs_user", description)
        self.assertIn("invalid_amount", description)
        self.assertIn("Visa and Amex", description)
        self.assertIn("fake fixtures", description)
        self.assertIn("later integrator", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "pick_card")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_pick_card(self) -> None:
        payload = {
            "merchantCountry": "Japan",
            "amount": 1000,
            "currency": "JPY",
            "cards": _japan_cards(),
        }
        self.assertEqual(handler(payload), pick_card(payload))
        self.assertEqual(handler(json.dumps(payload)), pick_card(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("runtime___pick_card"))
        self.assertEqual(wrapped["cardId"], "mc-japan")
        self.assertEqual(wrapped["reason"], "no_fx_fee")

        nested = handler({"input": payload})
        self.assertEqual(nested["payAmount"], 1000)

        named = pick_card(
            merchantCountry="JP",
            amount=1000,
            currency="JPY",
            cards=_japan_cards(),
        )
        self.assertEqual(named["cardId"], "mc-japan")

        rejected = handler(payload, _AgentCoreContext("authorize_spend"))
        self.assertIsNone(rejected["cardId"])
        self.assertEqual(rejected["feeAmount"], 0)
        self.assertEqual(rejected["payAmount"], 0)
        self.assertEqual(rejected["currency"], "JPY")
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected pick_card")

    def test_does_not_charge_or_call_the_network(self) -> None:
        source = inspect.getsource(pick_mod) + inspect.getsource(tool_mod)
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
            result = _call("Japan", 1000, "JPY", _japan_cards())
        self.assertEqual(result["cardId"], "mc-japan")
        self.assertEqual(result["feeAmount"], 0)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("pick_card opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
