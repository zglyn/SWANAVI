"""Master loop with the capability packages present or missing."""

from __future__ import annotations

import json
import sys
import types
import unittest
from typing import Any

from booking.master.demo import FIXTURE, main
from booking.master.service import MAX_TICKS, handle_payload, segment_accepted

SAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _booked(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    del travelers, trip_id
    return {
        "segmentId": segment["segmentId"],
        "kind": segment["kind"],
        "status": "booked",
        "confirmationCode": f"SANDBOX-{segment['segmentId']}",
        "price": {"amount": "10.00", "currency": "USD"},
        "error": None,
    }


def _email(segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str) -> dict[str, str]:
    del travelers, trip_id
    return {
        "from": "sandbox@example.test",
        "to": "traveler@example.test",
        "subject": f"{segment['segmentId']} confirmed",
        "body": confirmation_code,
        "receivedAt": "2026-11-01T00:00:00Z",
    }


def _verify_match(email: dict[str, Any], segment: dict[str, Any], confirmation_code: str, travelers: list[Any]) -> dict[str, Any]:
    del travelers
    verified = isinstance(email, dict) and email.get("body") == confirmation_code
    return {
        "segmentId": segment.get("segmentId"),
        "kind": segment.get("kind"),
        "verified": verified,
        "reason": "matched" if verified else "mismatch",
    }


class _Modules(unittest.TestCase):
    def setUp(self) -> None:
        self._saved: dict[str, types.ModuleType | None] = {}

    def tearDown(self) -> None:
        for name, previous in reversed(list(self._saved.items())):
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def install(self, name: str, **attrs: Any) -> types.ModuleType:
        if name not in self._saved:
            self._saved[name] = sys.modules.get(name)
        module = types.ModuleType(name)
        module.__package__ = name.rpartition(".")[0]
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and child:
            if parent_name not in self._saved:
                self._saved[parent_name] = parent
            setattr(parent, child, module)
        return module

    def hide(self, *names: str) -> None:
        """Treat these modules as not installed. ``tearDown`` puts them back."""

        for name in names:
            if name not in self._saved:
                self._saved[name] = sys.modules.get(name)
            sys.modules[name] = None


class MissingCapabilityTests(_Modules):
    def test_missing_verifiers_do_not_crash(self) -> None:
        self.hide(
            "booking.verify",
            "booking.verify.flights",
            "booking.verify.hotels",
            "booking.verify.attractions",
            "booking.progress",
        )

        result = handle_payload(SAMPLE)

        self.assertEqual(result["tripId"], "sample-kyoto")
        self.assertIsNone(result["error"])
        self.assertEqual(
            [item["segmentId"] for item in result["results"]],
            ["flight-1", "hotel-1", "attraction-1"],
        )
        for item in result["results"]:
            self.assertFalse(item["emailVerified"])
            self.assertFalse(segment_accepted(item))
            if item["status"] == "booked":
                self.assertIsInstance(item["confirmationCode"], str)
                self.assertTrue(item["confirmationCode"].startswith("SANDBOX-"))
                self.assertEqual(item["reason"], "verifier_not_installed")
        self.assertTrue(any(item["status"] == "booked" for item in result["results"]))

    def test_missing_progress_records_one_update_and_stops(self) -> None:
        self.hide("booking.progress")
        result = handle_payload(SAMPLE)

        self.assertEqual(result["loopStopped"], "progress_not_installed")
        self.assertEqual(result["maxTicks"], MAX_TICKS)
        self.assertEqual(len(result["ticks"]), 1)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        tick = result["ticks"][0]
        self.assertEqual(tick["tick"], 1)
        self.assertEqual(tick["clock"], {"tick": 1, "now": "2026-11-02T08:00:00Z"})
        self.assertEqual(
            tick["updates"],
            [{"segmentId": None, "kind": None, "issue": "progress_not_installed", "action": "none"}],
        )

    def test_invalid_plan_does_not_raise(self) -> None:
        result = handle_payload({"tripId": "bad", "flights": []})
        self.assertEqual(result["error"], "invalid_plan")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["ticks"], [])
        self.assertEqual(handle_payload(["nope"])["error"], "invalid_plan")

    def test_verifier_exception_does_not_crash(self) -> None:
        def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            raise RuntimeError("parser blew up")

        self.hide("booking.progress")
        self.install("booking.providers.flights", book=_booked)
        self.install("booking.providers.hotels", book=_booked)
        self.install("booking.providers.attractions", book=_booked)
        self.install("booking.verify.flights", sample_email=explode, verify=explode)
        self.install("booking.verify.hotels", sample_email=_email, verify=explode)
        self.install("booking.verify.attractions", sample_email=_email, verify=_verify_match)

        result = handle_payload(SAMPLE)
        by_id = {item["segmentId"]: item for item in result["results"]}

        self.assertFalse(by_id["flight-1"]["emailVerified"])
        self.assertEqual(by_id["flight-1"]["reason"], "parser blew up")
        self.assertFalse(by_id["hotel-1"]["emailVerified"])
        self.assertEqual(by_id["hotel-1"]["reason"], "parser blew up")
        self.assertTrue(by_id["attraction-1"]["emailVerified"])
        self.assertTrue(segment_accepted(by_id["attraction-1"]))
        self.assertEqual(result["loopStopped"], "progress_not_installed")


class ControlLoopTests(_Modules):
    def _providers(self, book: Any | None = None) -> dict[str, list[str]]:
        calls: dict[str, list[str]] = {"flight": [], "hotel": [], "attraction": []}

        def make(kind: str) -> Any:
            def book_segment(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
                calls[kind].append(segment["segmentId"])
                if book is not None:
                    return book(segment, travelers, trip_id)
                return _booked(segment, travelers, trip_id)

            return book_segment

        self.install("booking.providers.flights", book=make("flight"), book_flight=make("flight"))
        self.install("booking.providers.hotels", book=make("hotel"))
        self.install("booking.providers.attractions", book=make("attraction"), book_attraction=make("attraction"))
        self.install("booking.verify.flights", sample_email=_email, verify=_verify_match)
        self.install("booking.verify.hotels", sample_email=_email, verify=_verify_match)
        self.install("booking.verify.attractions", sample_email=_email, verify=_verify_match)
        return calls

    def test_accepts_segment_only_when_booked_and_verified(self) -> None:
        self._providers()

        def verify_hotel_only(
            email: dict[str, Any], segment: dict[str, Any], confirmation_code: str, travelers: list[Any]
        ) -> dict[str, Any]:
            del email, confirmation_code, travelers
            verified = segment.get("kind") == "hotel"
            return {
                "segmentId": segment.get("segmentId"),
                "kind": segment.get("kind"),
                "verified": verified,
                "reason": "matched" if verified else "mismatch",
            }

        self.install("booking.verify.flights", sample_email=_email, verify=verify_hotel_only)
        self.install("booking.verify.attractions", sample_email=_email, verify=verify_hotel_only)

        result = handle_payload(SAMPLE)
        by_id = {item["segmentId"]: item for item in result["results"]}

        self.assertEqual(by_id["flight-1"]["status"], "booked")
        self.assertFalse(by_id["flight-1"]["emailVerified"])
        self.assertFalse(segment_accepted(by_id["flight-1"]))
        self.assertTrue(segment_accepted(by_id["hotel-1"]))
        self.assertEqual(by_id["hotel-1"]["reason"], "matched")

    def test_rebook_and_verify_email_follow_progress_updates(self) -> None:
        calls = self._providers()
        verify_calls: list[str] = []

        def verify(email: dict[str, Any], segment: dict[str, Any], confirmation_code: str, travelers: list[Any]) -> dict[str, Any]:
            verify_calls.append(segment["segmentId"])
            return _verify_match(email, segment, confirmation_code, travelers)

        self.install("booking.verify.flights", sample_email=_email, verify=verify)
        self.install("booking.verify.hotels", sample_email=_email, verify=verify)
        clocks: list[dict[str, Any]] = []

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            self.assertEqual(plan["tripId"], "sample-kyoto")
            self.assertEqual(len(results), 3)
            clocks.append(clock)
            if clock["tick"] == 1:
                return {
                    "phase": "day-of",
                    "onTrack": False,
                    "updates": [
                        {"segmentId": "flight-1", "kind": "flight", "issue": "schedule slipped", "action": "rebook"},
                        {"segmentId": "hotel-1", "kind": "hotel", "issue": "check the mailbox", "action": "verify_email"},
                        {"segmentId": "attraction-1", "kind": "attraction", "issue": "quiet", "action": "none"},
                    ],
                }
            return {"phase": "day-of", "onTrack": True, "updates": []}

        self.install("booking.progress", trip_progress=trip_progress)
        original = json.loads(json.dumps(SAMPLE))
        result = handle_payload(SAMPLE)

        self.assertEqual(SAMPLE, original)
        self.assertEqual(clocks[0], {"tick": 1, "now": "2026-11-02T08:00:00Z"})
        self.assertEqual(clocks[1], {"tick": 2, "now": "2026-11-02T11:00:00Z"})
        self.assertEqual(len(result["ticks"]), 2)
        self.assertEqual(result["loopStopped"], "on_track")
        self.assertEqual(result["ticks"][0]["updates"][0]["issue"], "schedule slipped")
        self.assertEqual(calls["flight"], ["flight-1", "flight-1"])
        self.assertEqual(calls["hotel"], ["hotel-1"])
        self.assertEqual(calls["attraction"], ["attraction-1"])
        self.assertEqual(result["results"][0]["reason"], "rebooked")
        self.assertFalse(result["results"][0]["emailVerified"])
        self.assertFalse(segment_accepted(result["results"][0]))
        self.assertGreaterEqual(verify_calls.count("hotel-1"), 2)
        self.assertTrue(segment_accepted(result["results"][1]))
        self.assertEqual([item["segmentId"] for item in result["results"]], ["flight-1", "hotel-1", "attraction-1"])

    def test_unknown_segment_does_not_replan_or_crash(self) -> None:
        calls = self._providers()

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del plan, results
            if clock["tick"] > 1:
                return {"phase": "monitoring", "onTrack": True, "updates": []}
            return {
                "phase": "monitoring",
                "onTrack": False,
                "updates": [
                    {"segmentId": "flight-9", "kind": "flight", "issue": "new leg", "action": "rebook"},
                ],
            }

        self.install("booking.progress", trip_progress=trip_progress)
        result = handle_payload(SAMPLE)

        self.assertEqual([item["segmentId"] for item in result["results"]], ["flight-1", "hotel-1", "attraction-1"])
        self.assertEqual(calls["flight"], ["flight-1"])
        self.assertEqual(result["loopStopped"], "on_track")

    def test_loop_caps_at_five_ticks(self) -> None:
        calls = self._providers()

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del plan, results, clock
            return {
                "phase": "monitoring",
                "onTrack": False,
                "updates": [
                    {"segmentId": "flight-1", "kind": "flight", "issue": "still late", "action": "rebook"},
                ],
            }

        self.install("booking.progress", trip_progress=trip_progress)
        result = handle_payload(SAMPLE)

        self.assertEqual(len(result["ticks"]), MAX_TICKS)
        self.assertEqual(result["loopStopped"], "max_ticks")
        self.assertEqual(calls["flight"], ["flight-1"] * (1 + MAX_TICKS))
        self.assertEqual(result["results"][0]["reason"], "rebooked")
        self.assertFalse(segment_accepted(result["results"][0]))

    def test_failed_booking_skips_verifier(self) -> None:
        sample_calls: list[str] = []

        def fail(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
            del travelers, trip_id
            return {
                "segmentId": segment["segmentId"],
                "kind": segment["kind"],
                "status": "failed",
                "confirmationCode": None,
                "error": "no seats",
            }

        def sample_email(*args: Any) -> dict[str, str]:
            sample_calls.append("sample")
            return _email(*args)

        self.install("booking.providers.flights", book=fail)
        self.install("booking.providers.hotels", book=_booked)
        self.install("booking.providers.attractions", book=_booked)
        self.install("booking.verify.flights", sample_email=sample_email, verify=_verify_match)

        result = handle_payload(SAMPLE)
        flight = result["results"][0]

        self.assertEqual(sample_calls, [])
        self.assertEqual(flight["status"], "failed")
        self.assertFalse(flight["emailVerified"])
        self.assertEqual(flight["reason"], "no seats")
        self.assertIsNone(flight["confirmationCode"])
        self.assertFalse(segment_accepted(flight))

    def test_progress_exception_ends_the_loop(self) -> None:
        self._providers()

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del plan, results, clock
            raise RuntimeError("progress down")

        self.install("booking.progress", trip_progress=trip_progress)
        result = handle_payload(SAMPLE)

        self.assertEqual(result["loopStopped"], "progress_error")
        self.assertEqual(result["ticks"][0]["updates"][0]["issue"], "progress down")
        self.assertEqual(len(result["results"]), 3)
        self.assertIsNone(result["error"])


class RuntimeTests(unittest.TestCase):
    def test_entrypoint_registers_capability_tools(self) -> None:
        from booking.master.main import app, invoke

        self.assertIn("main", app.handlers)
        self.assertEqual(
            set(app.booking_tools),
            {
                "book_flight",
                "book_hotel",
                "book_attraction",
                "verify_flight_email",
                "verify_hotel_email",
                "verify_attraction_email",
                "trip_progress",
            },
        )
        result = invoke(SAMPLE, context=None)
        self.assertEqual(result["tripId"], "sample-kyoto")
        self.assertIsNone(result["error"])
        self.assertNotEqual(result["loopStopped"], "progress_not_installed")
        self.assertGreaterEqual(len(result["ticks"]), 1)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        for item in result["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertIs(item["emailVerified"], True)
            self.assertNotEqual(item["reason"], "verifier_not_installed")

    def test_demo_shows_a_tick_and_an_update(self) -> None:
        from io import StringIO
        from unittest.mock import patch

        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            status = main()
        self.assertEqual(status, 0)
        printed = json.loads(stdout.getvalue())
        trace = stderr.getvalue()
        self.assertEqual(printed["tripId"], "sample-kyoto")
        self.assertEqual(printed["maxTicks"], MAX_TICKS)
        self.assertGreaterEqual(len(printed["ticks"]), 1)
        self.assertLessEqual(len(printed["ticks"]), MAX_TICKS)
        self.assertNotEqual(printed["loopStopped"], "progress_not_installed")
        updates = [update for tick in printed["ticks"] for update in tick["updates"] if isinstance(update, dict)]
        self.assertTrue(any(update.get("action") == "rebook" for update in updates))
        self.assertIn("tick 1", trace)
        self.assertIn("action=rebook", trace)
        self.assertNotIn("progress_not_installed", trace)
        self.assertNotIn("verifier_not_installed", trace)
        for item in printed["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertIs(item["emailVerified"], True)


if __name__ == "__main__":
    unittest.main()
