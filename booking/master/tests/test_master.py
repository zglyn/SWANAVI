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

    def test_missing_replan_package_records_and_continues(self) -> None:
        calls = self._providers()
        self.hide(
            "booking.replan",
            "booking.replan.cancel",
            "booking.replan.early",
            "booking.replan.late",
        )
        signals = [
            ("cancelled", "flight-1", "flight", None),
            ("ended_early", "hotel-1", "hotel", 60),
            ("ended_late", "attraction-1", "attraction", 45),
        ]
        seen: list[str] = []

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del results
            seen.append(plan["hotels"][0]["checkOut"])
            tick = clock["tick"]
            if tick > len(signals):
                return {"phase": "in_progress", "onTrack": True, "updates": []}
            event, segment_id, kind, delta = signals[tick - 1]
            update: dict[str, Any] = {
                "segmentId": segment_id,
                "kind": kind,
                "issue": event,
                "action": "replan",
                "event": event,
            }
            if delta is not None:
                update["deltaMinutes"] = delta
            return {"phase": "in_progress", "onTrack": False, "updates": [update]}

        self.install("booking.progress", trip_progress=trip_progress)
        original = json.loads(json.dumps(SAMPLE))
        result = handle_payload(SAMPLE)

        self.assertEqual(SAMPLE, original)
        self.assertEqual(result["maxTicks"], MAX_TICKS)
        self.assertEqual(result["loopStopped"], "on_track")
        self.assertEqual(len(result["ticks"]), len(signals) + 1)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        self.assertEqual(seen, ["2026-11-06"] * (len(signals) + 1))
        self.assertEqual(calls["flight"], ["flight-1"])
        self.assertEqual(calls["hotel"], ["hotel-1"])
        self.assertEqual(calls["attraction"], ["attraction-1"])
        for tick, (event, segment_id, kind, delta) in zip(result["ticks"], signals):
            update = tick["updates"][0]
            self.assertEqual(update["action"], "replan")
            self.assertEqual(update["event"], event)
            self.assertEqual(update["segmentId"], segment_id)
            self.assertEqual(update["kind"], kind)
            self.assertEqual(update.get("deltaMinutes"), delta)
            self.assertEqual(update["replan"], "replan_not_installed")
        for item in result["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertTrue(segment_accepted(item))

    def test_replan_tool_shifts_a_segment(self) -> None:
        self._providers()
        booked_times: list[str] = []

        def book_attraction(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
            booked_times.append(segment["time"])
            return _booked(segment, travelers, trip_id)

        self.install(
            "booking.providers.attractions",
            book=book_attraction,
            book_attraction=book_attraction,
        )
        calls: list[tuple[Any, ...]] = []

        def replan_late(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> dict[str, Any]:
            calls.append((trip_id, now, disruption, plan["attractions"][0]["time"]))
            shifted = json.loads(json.dumps(plan))
            hour, minute = shifted["attractions"][0]["time"].split(":")
            total = int(hour) * 60 + int(minute) + disruption["deltaMinutes"]
            shifted["attractions"][0]["time"] = f"{total // 60:02d}:{total % 60:02d}"
            return {
                "changed": True,
                "plan": shifted,
                "notes": ["shifted attraction-1 by 45 minutes"],
            }

        self.install("booking.replan")
        self.install("booking.replan.late", replan_late=replan_late)
        seen: list[str] = []

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del results
            seen.append(plan["attractions"][0]["time"])
            if clock["tick"] == 1:
                return {
                    "phase": "in_progress",
                    "onTrack": False,
                    "updates": [
                        {
                            "segmentId": "attraction-1",
                            "kind": "attraction",
                            "issue": "segment ended late",
                            "action": "replan",
                            "event": "ended_late",
                            "deltaMinutes": 45,
                        }
                    ],
                }
            if clock["tick"] == 2:
                return {
                    "phase": "in_progress",
                    "onTrack": False,
                    "updates": [
                        {
                            "segmentId": "attraction-1",
                            "kind": "attraction",
                            "issue": "book the shifted visit",
                            "action": "rebook",
                        }
                    ],
                }
            return {"phase": "in_progress", "onTrack": True, "updates": []}

        self.install("booking.progress", trip_progress=trip_progress)
        original = json.loads(json.dumps(SAMPLE))
        result = handle_payload(SAMPLE)

        self.assertEqual(SAMPLE, original)
        self.assertEqual(SAMPLE["attractions"][0]["time"], "09:00")
        self.assertEqual(
            calls,
            [
                (
                    "sample-kyoto",
                    "2026-11-02T08:00:00Z",
                    {
                        "segmentId": "attraction-1",
                        "kind": "attraction",
                        "event": "ended_late",
                        "deltaMinutes": 45,
                    },
                    "09:00",
                )
            ],
        )
        self.assertEqual(seen, ["09:00", "09:45", "09:45"])
        self.assertEqual(booked_times, ["09:00", "09:45"])
        self.assertEqual(result["loopStopped"], "on_track")
        self.assertEqual(result["maxTicks"], MAX_TICKS)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        shifted = result["ticks"][0]["updates"][0]
        self.assertEqual(shifted["replan"], "changed")
        self.assertEqual(shifted["notes"], ["shifted attraction-1 by 45 minutes"])
        self.assertEqual(result["results"][2]["reason"], "rebooked")
        self.assertFalse(segment_accepted(result["results"][2]))
        self.assertTrue(segment_accepted(result["results"][0]))
        self.assertTrue(segment_accepted(result["results"][1]))

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

    def test_missing_guard_packages_do_not_crash(self) -> None:
        self._providers()
        self.hide(
            "booking.guard",
            "booking.guard.budget",
            "booking.guard.spend",
            "booking.guard.conflicts",
            "booking.refund",
            "booking.notify",
        )

        def replan_cancel(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> dict[str, Any]:
            del trip_id, now, disruption
            shifted = json.loads(json.dumps(plan))
            shifted["hotels"][0]["checkOut"] = "2026-11-05"
            return {"changed": True, "plan": shifted, "notes": ["cancelled flight-1"]}

        self.install("booking.replan.cancel", replan_cancel=replan_cancel)

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del plan, results
            if clock["tick"] > 1:
                return {"phase": "in_progress", "onTrack": True, "updates": []}
            return {
                "phase": "in_progress",
                "onTrack": False,
                "updates": [
                    {
                        "segmentId": "flight-1",
                        "kind": "flight",
                        "issue": "segment cancelled",
                        "action": "replan",
                        "event": "cancelled",
                    }
                ],
            }

        self.install("booking.progress", trip_progress=trip_progress)
        result = handle_payload(SAMPLE)

        self.assertIsNone(result["error"])
        self.assertEqual(result["maxTicks"], MAX_TICKS)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        self.assertEqual(result["loopStopped"], "on_track")
        self.assertEqual(result["spend"]["authorizedAmount"], 10)
        self.assertEqual(result["spend"]["requestedAmount"], 12)
        self.assertEqual(result["spend"]["currency"], "USD")
        self.assertIsNone(result["spend"]["payAmount"])
        self.assertEqual(result["spend"]["reason"], "authorize_spend_not_installed")
        for item in result["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertTrue(segment_accepted(item))
            self.assertEqual(item["budget"], "check_budget_not_installed")
        cancelled = result["ticks"][0]["updates"][0]
        self.assertEqual(cancelled["replan"], "changed")
        self.assertEqual(cancelled["refund"], "refund_booking_not_installed")
        self.assertEqual(cancelled["conflicts"], "check_conflicts_not_installed")
        self.assertEqual(result["ticks"][0]["notice"], "trip_notice_not_installed")

    def test_budget_rejection_is_not_accepted(self) -> None:
        self._providers()
        self.hide("booking.progress", "booking.guard.spend", "booking.notify")

        def check_budget(trip_id: str, segment: dict[str, Any], price: dict[str, Any] | None) -> dict[str, Any]:
            del trip_id, price
            return {"allowed": segment.get("segmentId") != "hotel-1"}

        self.install("booking.guard.budget", check_budget=check_budget)
        result = handle_payload(SAMPLE)
        by_id = {item["segmentId"]: item for item in result["results"]}

        self.assertEqual(by_id["hotel-1"]["status"], "needs_user")
        self.assertTrue(by_id["hotel-1"]["emailVerified"])
        self.assertFalse(segment_accepted(by_id["hotel-1"]))
        self.assertEqual(by_id["hotel-1"]["budget"]["allowed"], False)
        self.assertTrue(segment_accepted(by_id["flight-1"]))
        self.assertTrue(segment_accepted(by_id["attraction-1"]))
        self.assertEqual(result["loopStopped"], "progress_not_installed")

    def test_fake_authorize_spend_result_is_recorded(self) -> None:
        self._providers()
        self.hide("booking.progress")
        seen: list[tuple[Any, ...]] = []

        def authorize_spend(authorizedAmount: int, requestedAmount: int, currency: str) -> dict[str, Any]:
            seen.append((authorizedAmount, requestedAmount, currency))
            return {"payAmount": 10, "reason": "over_capture_rejected", "marker": "fake-spend"}

        def trip_notice(trip_id: str, event: dict[str, Any]) -> dict[str, Any]:
            return {"tripId": trip_id, "type": event["type"], "payAmount": event["payAmount"]}

        self.install("booking.guard.spend", authorize_spend=authorize_spend)
        self.install("booking.notify", trip_notice=trip_notice)
        result = handle_payload(SAMPLE)

        self.assertEqual(seen, [(10, 12, "USD")])
        self.assertEqual(result["spend"]["payAmount"], 10)
        self.assertEqual(result["spend"]["reason"], "over_capture_rejected")
        self.assertEqual(result["spend"]["marker"], "fake-spend")
        self.assertEqual(result["spend"]["authorizedAmount"], 10)
        self.assertEqual(result["spend"]["requestedAmount"], 12)
        self.assertEqual(result["spend"]["currency"], "USD")
        self.assertEqual(
            result["ticks"][0]["notice"],
            {"tripId": "sample-kyoto", "type": "over_capture_rejected", "payAmount": 10},
        )
        self.assertEqual(result["maxTicks"], MAX_TICKS)
        self.assertEqual(len(result["ticks"]), 1)
        for item in result["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertTrue(segment_accepted(item))


class AssistTests(_Modules):
    def test_missing_assist_packages_do_not_crash(self) -> None:
        self.hide("booking.progress")
        result = handle_payload(SAMPLE)

        self.assertIsNone(result["error"])
        self.assertEqual(result["maxTicks"], MAX_TICKS)
        self.assertEqual(len(result["ticks"]), 1)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        self.assertEqual(result["loopStopped"], "progress_not_installed")
        self.assertEqual(result["entry"], "check_entry_not_installed")
        self.assertEqual(result["emergency"], "emergency_card_not_installed")
        self.assertEqual(result["fx"], "quote_fx_not_installed")
        self.assertEqual(result["tip"], "tip_policy_not_installed")
        self.assertEqual(result["transfer"], "check_transfer_not_installed")
        self.assertEqual(result["luggage"], "luggage_drop_not_installed")
        self.assertEqual(result["checkout"], "late_checkout_not_installed")
        self.assertEqual(result["spend"]["authorizedAmount"], 10)
        self.assertEqual(result["spend"]["requestedAmount"], 12)
        self.assertEqual(result["spend"]["currency"], "USD")
        tick = result["ticks"][0]
        self.assertEqual(tick["watch"], "watch_not_installed")
        self.assertEqual(tick["warnings"], [])
        self.assertEqual(tick["airport"], "airport_leave_not_installed")
        self.assertEqual(tick["wallet"], "trip_wallet_not_installed")
        self.assertNotIn("afterDark", tick)

    def test_missing_request_ride_does_not_crash(self) -> None:
        self.hide("booking.progress", "booking.assist.ride", "booking.assist.phrase")
        plan = json.loads(json.dumps(SAMPLE))
        plan["attractions"].append(
            {
                "segmentId": "attraction-dawn",
                "kind": "attraction",
                "name": "Dawn gate",
                "city": "Kyoto",
                "date": "2026-11-02",
                "partySize": 1,
                "time": "00:30",
                "end": "2026-11-02T01:00:00Z",
            }
        )

        result = handle_payload(plan)

        self.assertIsNone(result["error"])
        self.assertEqual(result["loopStopped"], "progress_not_installed")
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        rides = result["ticks"][0]["rides"]
        self.assertEqual(rides[0]["segmentId"], "attraction-dawn")
        self.assertEqual(rides[0]["pickupAt"], "2026-11-02T01:00:00Z")
        self.assertEqual(rides[0]["result"], "request_ride_not_installed")
        self.assertIsNone(rides[0]["rideCode"])
        self.assertEqual(result["ticks"][0]["phrase"], "phrase_card_not_installed")

    def test_scripted_entry_fx_and_tip_ceiling(self) -> None:
        self.hide("booking.progress")
        seen: dict[str, Any] = {}

        def check_entry(source: dict[str, Any]) -> dict[str, Any]:
            seen["entry"] = source
            return {"ok": False, "issues": ["visaOnFile is false"]}

        def quote_fx(amount: int, fromCurrency: str, toCurrency: str) -> dict[str, Any]:
            seen["fx"] = (amount, fromCurrency, toCurrency)
            return {"amount": 6.7, "currency": toCurrency, "reason": "quoted"}

        def tip_policy(tripId: str, country: str, currency: str, requestedAmount: int) -> dict[str, Any]:
            del tripId
            seen["tip"] = (country, currency, requestedAmount)
            return {"authorizedAmount": 8}

        def authorize_spend(authorizedAmount: int, requestedAmount: int, currency: str) -> dict[str, Any]:
            seen["spend"] = (authorizedAmount, requestedAmount, currency)
            return {"payAmount": authorizedAmount, "reason": "within_limit"}

        self.install("booking.assist.entry", check_entry=check_entry)
        self.install("booking.assist.fx", quote_fx=quote_fx)
        self.install("booking.assist.tip", tip_policy=tip_policy)
        self.install("booking.guard.spend", authorize_spend=authorize_spend)

        result = handle_payload(SAMPLE)

        self.assertEqual(seen["entry"]["passportExpiry"], "2026-12-06")
        self.assertEqual(seen["entry"]["tripEnd"], "2026-11-06")
        self.assertIs(seen["entry"]["visaOnFile"], False)
        self.assertEqual(seen["fx"], (1000, "JPY", "USD"))
        self.assertEqual(seen["tip"], ("Japan", "USD", 12))
        self.assertEqual(seen["spend"], (8, 12, "USD"))
        self.assertEqual(result["spend"]["authorizedAmount"], 8)
        self.assertEqual(result["tip"]["authorizedAmount"], 8)

    def test_watch_warnings_act_in_the_same_tick(self) -> None:
        order: list[str] = []

        def book(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
            return _booked(segment, travelers, trip_id)

        self.install("booking.providers.flights", book=book, book_flight=book)
        self.install("booking.providers.hotels", book=book)
        self.install("booking.providers.attractions", book=book, book_attraction=book)
        self.install("booking.verify.flights", sample_email=_email, verify=_verify_match)
        self.install("booking.verify.hotels", sample_email=_email, verify=_verify_match)
        self.install("booking.verify.attractions", sample_email=_email, verify=_verify_match)

        def watch_trip(now: str, plan: dict[str, Any], rides: list[Any], signals: list[Any], tripId: str = "") -> dict[str, Any]:
            del now, plan, rides, signals, tripId
            order.append("watch")
            return {
                "ok": False,
                "warnings": [
                    {
                        "segmentId": "flight-1",
                        "issue": "cancelled",
                        "severity": "act",
                        "action": "replan",
                        "event": "cancelled",
                    },
                    {
                        "segmentId": "attraction-1",
                        "issue": "storm",
                        "severity": "act",
                        "action": "shift",
                        "condition": "storm",
                        "event": "ended_late",
                        "deltaMinutes": 15,
                    },
                    {
                        "segmentId": "flight-1",
                        "issue": "need a ride",
                        "severity": "act",
                        "action": "request_ride",
                    },
                    {
                        "segmentId": "flight-1",
                        "issue": "tight transfer",
                        "severity": "act",
                        "action": "check_transfer",
                    },
                    {
                        "segmentId": "hotel-1",
                        "issue": "note only",
                        "severity": "info",
                        "action": "request_ride",
                    },
                ],
            }

        def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
            del plan, results, clock
            order.append("progress")
            return {"phase": "day-of", "onTrack": True, "updates": []}

        def replan_cancel(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> dict[str, Any]:
            del trip_id, now, disruption
            order.append("replan")
            return {"changed": False, "plan": plan, "notes": []}

        def replan_late(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> dict[str, Any]:
            del trip_id, now, disruption
            order.append("shift")
            return {"changed": False, "plan": plan, "notes": []}

        def check_weather(segmentId: str, outdoor: bool, condition: str) -> dict[str, Any]:
            order.append("weather")
            return {"segmentId": segmentId, "outdoor": outdoor, "ok": False, "action": "shift", "reason": condition}

        def request_ride(pickupAt: str, dropoffName: str, segmentId: str = "", toSegmentId: str = "", tripId: str = "") -> dict[str, Any]:
            del pickupAt, dropoffName, toSegmentId, tripId
            order.append("ride:" + segmentId)
            return {"rideCode": "SANDBOX-RIDE-9"}

        def check_transfer(fromSegmentId: str, toSegmentId: str, fromEnd: str, toStart: str, travelMinutes: int) -> dict[str, Any]:
            del fromEnd, toStart, travelMinutes
            order.append("transfer:" + fromSegmentId + ":" + toSegmentId)
            return {"ok": False, "reason": "shortfall"}

        self.install("booking.assist.watch", watch_trip=watch_trip)
        self.install("booking.progress", trip_progress=trip_progress)
        self.install("booking.replan.cancel", replan_cancel=replan_cancel)
        self.install("booking.replan.late", replan_late=replan_late)
        self.install("booking.assist.weather", check_weather=check_weather)
        self.install("booking.assist.ride", request_ride=request_ride)
        self.install("booking.assist.transfers", check_transfer=check_transfer)

        result = handle_payload(SAMPLE)

        self.assertIsNone(result["error"])
        self.assertEqual(result["loopStopped"], "on_track")
        self.assertEqual(len(result["ticks"]), 1)
        self.assertLessEqual(len(result["ticks"]), MAX_TICKS)
        self.assertLess(order.index("watch"), order.index("progress"))
        self.assertLess(order.index("replan"), order.index("progress"))
        self.assertLess(order.index("weather"), order.index("progress"))
        self.assertLess(order.index("shift"), order.index("progress"))
        self.assertLess(order.index("ride:flight-1"), order.index("progress"))
        self.assertNotIn("ride:hotel-1", order)
        tick = result["ticks"][0]
        self.assertEqual(len(tick["warnings"]), 5)
        self.assertEqual(tick["warnings"][0]["replan"], "unchanged")
        self.assertEqual(tick["rides"][0]["rideCode"], "SANDBOX-RIDE-9")
        self.assertEqual(tick["warnings"][3]["transfer"]["reason"], "shortfall")

    def test_airport_not_ok_is_recorded_on_the_tick(self) -> None:
        self.hide("booking.progress")

        def airport_leave(tripId: str, segmentId: str, date: str, now: str, origin: str = "", destination: str = "") -> dict[str, Any]:
            del tripId, origin, destination
            return {"ok": False, "segmentId": segmentId, "date": date, "now": now}

        self.install("booking.assist.airport", airport_leave=airport_leave)
        result = handle_payload(SAMPLE)
        airport = result["ticks"][0]["airport"]
        self.assertIs(airport["ok"], False)
        self.assertEqual(airport["segmentId"], "flight-1")
        self.assertEqual(airport["date"], "2026-11-02")

    def test_after_dark_request_ride_uses_the_walk(self) -> None:
        self.hide("booking.progress")
        plan = json.loads(json.dumps(SAMPLE))
        plan["attractions"].append(
            {
                "segmentId": "attraction-walk",
                "kind": "attraction",
                "name": "Night walk",
                "city": "Kyoto",
                "date": "2026-11-02",
                "partySize": 1,
                "time": "21:00",
                "walk": True,
            }
        )
        seen: list[str] = []

        def after_dark(segmentId: str, name: str, start: str, end: str, now: str = "", tripId: str = "") -> dict[str, Any]:
            del name, start, end, now, tripId
            seen.append(segmentId)
            return {"action": "request_ride", "segmentId": segmentId}

        def request_ride(pickupAt: str, dropoffName: str, segmentId: str = "", toSegmentId: str = "", tripId: str = "") -> dict[str, Any]:
            del pickupAt, toSegmentId, tripId
            seen.append(dropoffName)
            return {"rideCode": "SANDBOX-RIDE-WALK", "segmentId": segmentId}

        self.install("booking.assist.afterdark", after_dark=after_dark)
        self.install("booking.assist.ride", request_ride=request_ride)
        result = handle_payload(plan)

        self.assertEqual(seen[0], "attraction-walk")
        self.assertIn("Sample temple visit", seen)
        self.assertEqual(result["ticks"][0]["afterDark"]["action"], "request_ride")
        self.assertEqual(result["ticks"][0]["rides"][0]["rideCode"], "SANDBOX-RIDE-WALK")
        self.assertEqual(result["loopStopped"], "progress_not_installed")


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
                "replan_cancel",
                "replan_early",
                "replan_late",
                "check_budget",
                "authorize_spend",
                "refund_booking",
                "check_conflicts",
                "trip_notice",
                "check_entry",
                "check_hours",
                "check_transfer",
                "quote_fx",
                "check_weather",
                "emergency_card",
                "request_ride",
                "hold_table",
                "luggage_drop",
                "watch_trip",
                "airport_leave",
                "after_dark",
                "late_checkout",
                "tip_policy",
                "phrase_card",
                "trip_wallet",
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
        replan_updates = [
            (tick.get("tick"), update)
            for tick in printed["ticks"]
            if isinstance(tick, dict)
            for update in tick.get("updates", [])
            if isinstance(update, dict) and update.get("action") == "replan"
        ]
        self.assertEqual(
            [
                (tick, update.get("event"), update.get("deltaMinutes"), update.get("replan"))
                for tick, update in replan_updates
            ],
            [
                (1, "cancelled", None, "changed"),
                (2, "ended_early", 60, "changed"),
                (3, "ended_late", 45, "changed"),
            ],
        )
        notes = {update.get("event"): update.get("notes") for _tick, update in replan_updates}
        self.assertIn("marked flight-1 removed", notes["cancelled"])
        self.assertIn("shifted hotel-1 earlier by 180 minutes", notes["cancelled"])
        self.assertIn("shifted attraction-4 earlier by 60 minutes", notes["ended_early"])
        self.assertIn("shifted attraction-3 later by 45 minutes", notes["ended_late"])
        self.assertIn("tick 1", trace)
        self.assertIn("action=rebook", trace)
        self.assertIn("event=cancelled", trace)
        self.assertIn("event=ended_early", trace)
        self.assertIn("event=ended_late", trace)
        self.assertIn("deltaMinutes=60", trace)
        self.assertIn("deltaMinutes=45", trace)
        self.assertIn("replan=changed", trace)
        self.assertNotIn("replan_not_installed", trace)
        self.assertNotIn("progress_not_installed", trace)
        self.assertNotIn("verifier_not_installed", trace)
        for item in printed["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertIs(item["emailVerified"], True)


if __name__ == "__main__":
    unittest.main()
