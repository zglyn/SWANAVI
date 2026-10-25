"""Trip wallet: one line per booking, refund, or ride code.

These tests stay in-process. They do not call AWS or open a connection.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.assist.wallet import AGENTCORE_TOOL, TOOL_SPEC, handler, trip_wallet
from booking.assist.wallet import tool as tool_mod
from booking.assist.wallet import wallet as wallet_mod

TRIP = "sample-kyoto"


def _item(kind, segment_id, code, amount="10.00", currency="USD"):
    return {
        "kind": kind,
        "segmentId": segment_id,
        "code": code,
        "amount": amount,
        "currency": currency,
    }


class TripWalletTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_two_items_become_two_lines(self) -> None:
        result = trip_wallet(
            {
                "tripId": TRIP,
                "items": [
                    _item("booking", "flight-1", "SANDBOX-FLIGHT", "120.00"),
                    _item("ride", "ride-1", "SANDBOX-RIDE", "18.00"),
                ],
            }
        )

        self.assertEqual(set(result), {"tripId", "lines", "count"})
        self.assertEqual(result["tripId"], TRIP)
        self.assertEqual(
            result["lines"],
            [
                "booking flight-1 SANDBOX-FLIGHT 120.00 USD",
                "ride ride-1 SANDBOX-RIDE 18.00 USD",
            ],
        )
        self.assertEqual(result["count"], 2)

    def test_item_without_a_code_is_omitted_from_lines_and_count(self) -> None:
        result = trip_wallet(
            {
                "tripId": TRIP,
                "items": [
                    _item("booking", "flight-1", "SANDBOX-FLIGHT", "120.00"),
                    _item("refund", "hotel-1", None, "48.00"),
                    {
                        "kind": "ride",
                        "segmentId": "ride-1",
                        "amount": "18.00",
                        "currency": "USD",
                    },
                    _item("booking", "temple", "", "10.00"),
                    _item("booking", "garden", "   ", "10.00"),
                ],
            }
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(
            result["lines"],
            ["booking flight-1 SANDBOX-FLIGHT 120.00 USD"],
        )
        joined = " ".join(result["lines"])
        self.assertNotIn("hotel-1", joined)
        self.assertNotIn("48.00", joined)
        self.assertNotIn("ride-1", joined)

    def test_empty_items_return_count_zero_and_no_lines(self) -> None:
        cases = [
            {"tripId": TRIP, "items": []},
            {"tripId": TRIP},
            {"tripId": TRIP, "items": None},
            {"tripId": TRIP, "items": ()},
        ]
        for case in cases:
            result = trip_wallet(case)
            self.assertEqual(result["tripId"], TRIP)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["lines"], [])

    def test_null_fields_are_skipped_on_the_line(self) -> None:
        result = trip_wallet(
            {
                "tripId": TRIP,
                "items": [
                    {
                        "kind": "refund",
                        "segmentId": "hotel-1",
                        "code": "SANDBOX-REF-1",
                        "amount": None,
                        "currency": None,
                    },
                    {
                        "kind": None,
                        "segmentId": None,
                        "code": "SANDBOX-RIDE",
                        "amount": True,
                        "currency": "USD",
                    },
                    {
                        "kind": "booking",
                        "segmentId": "flight-1",
                        "code": "SANDBOX-FLIGHT",
                        "amount": 18,
                        "currency": "USD",
                    },
                ],
            }
        )

        self.assertEqual(
            result["lines"],
            [
                "refund hotel-1 SANDBOX-REF-1",
                "SANDBOX-RIDE USD",
                "booking flight-1 SANDBOX-FLIGHT 18 USD",
            ],
        )
        self.assertEqual(result["count"], 3)
        for line in result["lines"]:
            self.assertNotIn("None", line)
            self.assertNotIn("null", line)
            self.assertNotIn("True", line)
            self.assertNotIn("  ", line)

    def test_unreadable_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            3,
            object(),
            [],
            {"items": "nope"},
            {"tripId": TRIP, "items": [None, "bad", 1, {"code": "SANDBOX-1"}]},
            {"arguments": {"tripId": TRIP, "items": [_item("refund", "hotel-1", "SANDBOX-REF-1")]}},
        ]
        for case in cases:
            result = trip_wallet(case)
            self.assertEqual(set(result), {"tripId", "lines", "count"})
            self.assertIsInstance(result["tripId"], str)
            self.assertIsInstance(result["lines"], list)
            self.assertIsInstance(result["count"], int)
            self.assertEqual(result["count"], len(result["lines"]))

        kept = trip_wallet(
            {"tripId": TRIP, "items": [None, {"code": "SANDBOX-1"}, "bad"]}
        )
        self.assertEqual(kept["lines"], ["SANDBOX-1"])
        self.assertEqual(kept["count"], 1)

        wrapped = trip_wallet(
            {"arguments": {"tripId": TRIP, "items": [_item("refund", "hotel-1", "SANDBOX-REF-1")]}}
        )
        self.assertEqual(wrapped["tripId"], TRIP)
        self.assertEqual(wrapped["lines"], ["refund hotel-1 SANDBOX-REF-1 10.00 USD"])
        self.assertEqual(wrapped["count"], 1)

    def test_json_object_is_one_list(self) -> None:
        raw = (
            '{"tripId":"sample-kyoto","items":['
            '{"kind":"booking","segmentId":"flight-1","code":"SANDBOX-FLIGHT",'
            '"amount":"120.00","currency":"USD"},'
            '{"kind":"ride","segmentId":"ride-1","code":"SANDBOX-RIDE",'
            '"amount":"18.00","currency":"USD"}]}'
        )
        result = trip_wallet(raw)
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["lines"]), 2)
        self.assertIn("SANDBOX-FLIGHT", result["lines"][0])
        self.assertIn("SANDBOX-RIDE", result["lines"][1])

    def test_tool_spec_is_trip_wallet(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "trip_wallet")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["tripId", "items"])
        item_props = TOOL_SPEC["inputSchema"]["properties"]["items"]["items"]["properties"]
        self.assertEqual(
            list(item_props),
            ["kind", "segmentId", "code", "amount", "currency"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["tripId", "lines", "count"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("end of a tick", TOOL_SPEC["description"])
        self.assertIn("booking, refund, and ride codes", TOOL_SPEC["description"])
        self.assertIn("no network", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "trip_wallet")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_trip_wallet(self) -> None:
        payload = {
            "tripId": TRIP,
            "items": [
                _item("booking", "flight-1", "SANDBOX-FLIGHT", "120.00"),
                _item("refund", "hotel-1", "SANDBOX-REF-1", "48.00"),
            ],
        }
        self.assertEqual(handler(payload), trip_wallet(payload))
        self.assertEqual(handler(None)["count"], 0)
        self.assertEqual(handler(None)["lines"], [])

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___trip_wallet"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), trip_wallet(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___refund_booking"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored, {"tripId": "", "lines": [], "count": 0})

    def test_sandbox_sources_do_not_touch_network(self) -> None:
        for module in (wallet_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("smtplib", source)
            self.assertNotIn("subprocess", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("trip_wallet opened a connection")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
