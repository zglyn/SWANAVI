"""Traveler notices: one message names the event and includes every note.

These tests stay in-process. They do not call AWS, open a connection, or deliver a message.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.notify import AGENTCORE_TOOL, TOOL_SPEC, handler, trip_notice
from booking.notify import notice as notice_mod
from booking.notify import tool as tool_mod

TRIP = "sample-kyoto"
CANCELLED_NOTES = (
    "marked temple removed",
    "shifted garden earlier by 120 minutes",
)


def _payload(event: str, notes, segment_id: str = "temple", trip_id: str = TRIP) -> dict:
    return {
        "tripId": trip_id,
        "event": event,
        "notes": list(notes),
        "segmentId": segment_id,
    }


class TripNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_cancelled_with_two_notes_includes_both(self) -> None:
        result = trip_notice(_payload("cancelled", CANCELLED_NOTES))

        self.assertEqual(set(result), {"tripId", "subject", "body"})
        self.assertEqual(result["tripId"], TRIP)
        self.assertIn("cancelled", result["subject"])
        self.assertIn("cancelled", result["body"])
        for note in CANCELLED_NOTES:
            self.assertIn(note, result["subject"])
            self.assertIn(note, result["body"])
        self.assertEqual(result["body"].count("marked temple removed"), 1)
        self.assertIn("temple", result["subject"])
        self.assertIn("temple", result["body"])

    def test_empty_notes_still_returns_a_body(self) -> None:
        result = trip_notice(_payload("cancelled", []))

        self.assertEqual(result["tripId"], TRIP)
        self.assertTrue(result["subject"])
        self.assertTrue(result["body"])
        self.assertIn("cancelled", result["subject"])
        self.assertIn("cancelled", result["body"])
        self.assertNotIn("marked temple removed", result["body"])

    def test_each_event_is_named_when_notes_are_empty(self) -> None:
        events = (
            "cancelled",
            "ended_early",
            "ended_late",
            "booked",
            "over_capture_rejected",
        )
        for event in events:
            result = trip_notice(_payload(event, [], segment_id=""))
            self.assertIn(event, result["subject"])
            self.assertIn(event, result["body"])
            self.assertTrue(result["body"])

    def test_over_capture_rejected_includes_the_refusal_note(self) -> None:
        note = "refused capture above the authorized amount"
        result = trip_notice(
            _payload("over_capture_rejected", [note], segment_id="hotel-1")
        )
        self.assertIn("over_capture_rejected", result["subject"])
        self.assertIn("over_capture_rejected", result["body"])
        self.assertIn(note, result["subject"])
        self.assertIn(note, result["body"])
        self.assertIn("hotel-1", result["body"])

    def test_one_message_holds_every_note(self) -> None:
        result = trip_notice(_payload("ended_late", ["gate change", "dinner moved"]))
        self.assertIsInstance(result, dict)
        self.assertEqual(result["subject"].count("gate change"), 1)
        self.assertEqual(result["body"].count("dinner moved"), 1)

    def test_missing_fields_do_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"notes": None},
            {"event": "cancelled"},
            {"tripId": "sample-kyoto", "event": "booked", "notes": "one note"},
            {"tripId": "sample-kyoto", "event": "ended_early", "notes": [None, "kept"]},
            {
                "arguments": {
                    "tripId": "sample-kyoto",
                    "event": "ended_late",
                    "notes": ["train delayed"],
                    "segmentId": "flight-1",
                }
            },
        ]
        for case in cases:
            result = trip_notice(case)
            self.assertEqual(set(result), {"tripId", "subject", "body"})
            self.assertIsInstance(result["tripId"], str)
            self.assertIsInstance(result["subject"], str)
            self.assertTrue(result["subject"])
            self.assertIsInstance(result["body"], str)
            self.assertTrue(result["body"])

        booked = trip_notice({"tripId": "sample-kyoto", "event": "booked", "notes": "one note"})
        self.assertIn("booked", booked["subject"])
        self.assertIn("one note", booked["subject"])
        self.assertIn("one note", booked["body"])

        kept = trip_notice({"event": "ended_early", "notes": [None, "kept"]})
        self.assertIn("ended_early", kept["body"])
        self.assertIn("kept", kept["subject"])
        self.assertIn("kept", kept["body"])

    def test_json_object_is_one_notice(self) -> None:
        raw = (
            '{"tripId":"sample-kyoto","event":"cancelled","notes":["first","second"],'
            '"segmentId":"temple"}'
        )
        result = trip_notice(raw)
        self.assertEqual(result["tripId"], TRIP)
        self.assertIn("first", result["body"])
        self.assertIn("second", result["subject"])

    def test_tool_spec_is_trip_notice(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "trip_notice")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["tripId", "event", "notes", "segmentId"],
        )
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["properties"]["event"]["enum"],
            [
                "cancelled",
                "ended_early",
                "ended_late",
                "booked",
                "over_capture_rejected",
            ],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["tripId", "subject", "body"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("one message", TOOL_SPEC["description"])
        self.assertIn("does not deliver", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "trip_notice")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_trip_notice(self) -> None:
        payload = _payload("cancelled", CANCELLED_NOTES)
        self.assertEqual(handler(payload), trip_notice(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___trip_notice"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), trip_notice(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___replan_cancel"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(set(ignored), {"tripId", "subject", "body"})
        self.assertTrue(ignored["subject"])
        self.assertTrue(ignored["body"])
        self.assertNotIn("marked temple removed", ignored["body"])

    def test_sandbox_sources_do_not_touch_network_or_delivery(self) -> None:
        for module in (notice_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("smtplib", source)
            self.assertNotIn("subprocess", source)
            self.assertNotIn("datetime.now", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("trip_notice opened a connection")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
