"""Cancellation refunds: a sandbox code refunds, a missing code fails, nothing raises.

These tests stay in-process. They do not call AWS, open a socket, or charge a card.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.refund import AGENTCORE_TOOL, TOOL_SPEC, handler, refund_booking
from booking.refund import refund as refund_mod
from booking.refund.refund import REASON_NO_CODE, REASON_NOT_SANDBOX
from booking.refund import tool as tool_mod

SEGMENT = "temple"
CODE = "SANDBOX-KYOTO123456"
AMOUNT = "48.00"
CURRENCY = "USD"


def _refund(**overrides):
    payload = {
        "segmentId": SEGMENT,
        "confirmationCode": CODE,
        "amount": AMOUNT,
        "currency": CURRENCY,
        "event": "cancelled",
    }
    payload.update(overrides)
    return refund_booking(payload)


class RefundBookingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_cancelled_sandbox_code_refunds(self) -> None:
        result = _refund()

        self.assertEqual(result["segmentId"], SEGMENT)
        self.assertEqual(result["status"], "refunded")
        self.assertIsInstance(result["refundCode"], str)
        self.assertTrue(result["refundCode"].startswith("SANDBOX-REF-"))
        self.assertEqual(result["amount"], AMOUNT)
        self.assertEqual(result["currency"], CURRENCY)
        self.assertIsNone(result["reason"])

        again = refund_booking(SEGMENT, CODE, AMOUNT, CURRENCY, "cancelled")
        self.assertEqual(again, result)

    def test_numeric_amount_is_echoed(self) -> None:
        result = _refund(amount=48)

        self.assertEqual(result["status"], "refunded")
        self.assertEqual(result["amount"], 48)
        self.assertTrue(result["refundCode"].startswith("SANDBOX-REF-"))

    def test_missing_code_fails_without_raising(self) -> None:
        cases = [
            {"confirmationCode": None},
            {"confirmationCode": ""},
            {"confirmationCode": "   "},
            {"confirmationCode": 12345},
        ]
        for overrides in cases:
            payload = {
                "segmentId": SEGMENT,
                "confirmationCode": CODE,
                "amount": AMOUNT,
                "currency": CURRENCY,
                "event": "cancelled",
            }
            payload.update(overrides)
            if overrides["confirmationCode"] is None:
                del payload["confirmationCode"]
            result = refund_booking(payload)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["refundCode"])
            self.assertEqual(result["reason"], REASON_NO_CODE)
            self.assertEqual(result["segmentId"], SEGMENT)
            self.assertEqual(result["amount"], AMOUNT)
            self.assertEqual(set(result), {"segmentId", "status", "refundCode", "amount", "currency", "reason"})

    def test_non_sandbox_code_fails_without_raising(self) -> None:
        result = _refund(confirmationCode="LIVE-998877")

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["refundCode"])
        self.assertEqual(result["reason"], REASON_NOT_SANDBOX)
        self.assertEqual(result["amount"], AMOUNT)

    def test_other_failures_do_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            [],
            {},
            {"event": "ended_early", "confirmationCode": CODE, "amount": AMOUNT},
            {"event": "cancelled", "confirmationCode": CODE},
            {"event": "cancelled", "confirmationCode": CODE, "amount": ""},
            {"event": "cancelled", "confirmationCode": CODE, "amount": "-5.00"},
            {"segmentId": SEGMENT, "event": "cancelled", "confirmationCode": CODE, "amount": "nope"},
            {"arguments": {"event": "cancelled"}},
        ]
        for case in cases:
            result = refund_booking(case)
            self.assertEqual(set(result), {"segmentId", "status", "refundCode", "amount", "currency", "reason"})
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["refundCode"])
            self.assertIsInstance(result["reason"], str)
            self.assertTrue(result["reason"])

    def test_tool_spec_is_refund_booking(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "refund_booking")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["segmentId", "confirmationCode", "amount", "currency", "event"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"], ["refunded", "failed"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "status", "refundCode", "amount", "currency", "reason"],
        )
        self.assertIn("after replan_cancel", TOOL_SPEC["description"])
        self.assertIn("SANDBOX-REF-", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "refund_booking")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_refund_booking(self) -> None:
        payload = {
            "segmentId": SEGMENT,
            "confirmationCode": CODE,
            "amount": AMOUNT,
            "currency": CURRENCY,
            "event": "cancelled",
        }
        self.assertEqual(handler(payload), refund_booking(payload))
        self.assertEqual(handler(json.dumps(payload)), refund_booking(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___refund_booking"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), refund_booking(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___replan_cancel"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["status"], "failed")
        self.assertIsNone(ignored["refundCode"])

    def test_sandbox_sources_do_not_touch_network_card_or_aws(self) -> None:
        for module in (refund_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("stripe", source)
            self.assertNotIn("amadeus", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("refund_booking opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
