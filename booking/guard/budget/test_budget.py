"""Trip budget: under the cap, exactly at the cap, and one cent over.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.guard.budget import AGENTCORE_TOOL, TOOL_SPEC, check_budget, handler
from booking.guard.budget import budget as budget_mod
from booking.guard.budget import tool as tool_mod
from booking.guard.budget.budget import REASON_EXCEEDS, REASON_WITHIN


def _charge(**overrides) -> dict:
    payload = {
        "tripId": "sample-kyoto",
        "currency": "USD",
        "budgetAmount": "500.00",
        "spentAmount": "320.00",
        "proposedAmount": "150.00",
    }
    payload.update(overrides)
    return payload


class CheckBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_under_budget_allowed(self) -> None:
        result = check_budget(_charge())

        self.assertEqual(
            result,
            {
                "allowed": True,
                "remaining": "30.00",
                "currency": "USD",
                "reason": REASON_WITHIN,
            },
        )
        self.assertTrue(result["allowed"])

    def test_exactly_at_budget_allowed(self) -> None:
        result = check_budget(_charge(proposedAmount="180.00"))

        self.assertTrue(result["allowed"])
        self.assertEqual(result["remaining"], "0.00")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["reason"], REASON_WITHIN)

        numeric = check_budget(
            _charge(budgetAmount=100, spentAmount=40, proposedAmount=60)
        )
        self.assertTrue(numeric["allowed"])
        self.assertEqual(numeric["remaining"], "0.00")

    def test_one_cent_over_blocked(self) -> None:
        result = check_budget(_charge(proposedAmount="180.01"))

        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], "-0.01")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["reason"], REASON_EXCEEDS)

        by_a_cent = handler(
            _charge(budgetAmount="10.00", spentAmount="0.00", proposedAmount="10.01")
        )
        self.assertFalse(by_a_cent["allowed"])
        self.assertEqual(by_a_cent["remaining"], "-0.01")

    def test_missing_numbers_blocked(self) -> None:
        missing = check_budget(_charge(proposedAmount=None))
        self.assertFalse(missing["allowed"])
        self.assertIsNone(missing["remaining"])
        self.assertEqual(missing["currency"], "USD")
        self.assertIn("proposedAmount", missing["reason"])

        absent = check_budget({"tripId": "sample-kyoto", "currency": "USD"})
        self.assertFalse(absent["allowed"])
        self.assertIsNone(absent["remaining"])
        self.assertIn("budgetAmount", absent["reason"])
        self.assertIn("spentAmount", absent["reason"])
        self.assertIn("proposedAmount", absent["reason"])

        invalid = check_budget(_charge(budgetAmount="not-a-number"))
        self.assertFalse(invalid["allowed"])
        self.assertIsNone(invalid["remaining"])
        self.assertIn("budgetAmount", invalid["reason"])

    def test_bad_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            [],
            {},
            {"budgetAmount": True, "spentAmount": "1.00", "proposedAmount": "1.00"},
            {"budgetAmount": "nan", "spentAmount": "0", "proposedAmount": "0"},
            {"budgetAmount": "inf", "spentAmount": 0, "proposedAmount": 0},
            "{",
        ]
        for case in cases:
            result = check_budget(case)
            self.assertEqual(set(result), {"allowed", "remaining", "currency", "reason"})
            self.assertFalse(result["allowed"])
            self.assertIsInstance(result["reason"], str)
            self.assertTrue(result["reason"])

    def test_tool_spec_is_check_budget(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_budget")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["tripId", "currency", "budgetAmount", "spentAmount", "proposedAmount"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["allowed", "remaining", "currency", "reason"],
        )
        self.assertIn("before accepting a booking or a replan that adds cost", TOOL_SPEC["description"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("no network and no AWS", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_budget")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_budget(self) -> None:
        payload = _charge()
        self.assertEqual(handler(payload), check_budget(payload))
        self.assertEqual(handler(payload, _AgentCoreContext("guard___check_budget")), check_budget(payload))

        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertFalse(rejected["allowed"])
        self.assertEqual(rejected["reason"], "unsupported AgentCore tool; expected check_budget")

    def test_sandbox_source_has_no_network_client(self) -> None:
        for module in (budget_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("import boto", source)
            self.assertNotIn("import requests", source)
            self.assertNotIn("import urllib", source)
            self.assertNotIn("import httpx", source)
            self.assertNotIn("import socket", source)
            self.assertNotIn("amazonaws", source)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = self
        self.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("check_budget opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
