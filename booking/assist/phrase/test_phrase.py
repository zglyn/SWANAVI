"""Driver phrase card: Japanese prefix, French prefix, empty when the place is missing.

These tests stay in-process. They do not call a translation API, AWS, or open a socket.
"""

from __future__ import annotations

import inspect
import socket
import unittest

from booking.assist.phrase import AGENTCORE_TOOL, TOOL_SPEC, handler, phrase_card
from booking.assist.phrase import phrase as phrase_mod
from booking.assist.phrase import tool as tool_mod

JA_PREFIX = "こちらまでお願いします"
FR_PREFIX = "À cette adresse, s'il vous plaît"

PLACE = "金閣寺"
ADDRESS = "京都府京都市北区金閣寺町1"
ARRIVE = "2026-11-03 09:00"


def _payload(language: str, place: str | None = PLACE) -> dict:
    payload = {
        "language": language,
        "address": ADDRESS,
        "arriveAt": ARRIVE,
    }
    if place is not None:
        payload["placeName"] = place
    return payload


class PhraseCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_japanese_prefix(self) -> None:
        result = phrase_card(_payload("ja"))

        self.assertEqual(set(result), {"language", "card"})
        self.assertEqual(result["language"], "ja")
        self.assertEqual(
            result["card"],
            f"{JA_PREFIX}\n{PLACE}\n{ADDRESS}\n{ARRIVE}",
        )
        self.assertTrue(result["card"].startswith(JA_PREFIX))
        self.assertNotIn(FR_PREFIX, result["card"])

    def test_french_prefix(self) -> None:
        result = phrase_card(
            language="fr",
            placeName="Musée d'Orsay",
            address="1 Rue de la Légion d'Honneur, 75007 Paris",
            arriveAt="2026-11-04 14:30",
        )

        self.assertEqual(result["language"], "fr")
        self.assertEqual(
            result["card"],
            "À cette adresse, s'il vous plaît\n"
            "Musée d'Orsay\n"
            "1 Rue de la Légion d'Honneur, 75007 Paris\n"
            "2026-11-04 14:30",
        )
        self.assertTrue(result["card"].startswith(FR_PREFIX))
        self.assertNotIn(JA_PREFIX, result["card"])

    def test_missing_place_returns_an_empty_card(self) -> None:
        cases = (
            {"language": "ja", "address": ADDRESS, "arriveAt": ARRIVE},
            {"language": "fr", "placeName": "", "address": ADDRESS, "arriveAt": ARRIVE},
            {"language": "ja", "placeName": "   ", "address": ADDRESS, "arriveAt": ARRIVE},
            {"language": "en", "placeName": None, "address": ADDRESS, "arriveAt": ARRIVE},
            {"address": ADDRESS, "arriveAt": ARRIVE},
            {},
            None,
        )
        for case in cases:
            result = phrase_card(case)
            self.assertEqual(set(result), {"language", "card"})
            self.assertEqual(result["card"], "")
            self.assertNotIn(JA_PREFIX, result["card"])
            self.assertNotIn(FR_PREFIX, result["card"])

        self.assertEqual(phrase_card({"language": "ja"})["language"], "ja")
        self.assertEqual(phrase_card({"language": "fr", "placeName": ""})["language"], "fr")

    def test_other_language_has_no_prefix(self) -> None:
        result = phrase_card(_payload("en"))

        self.assertEqual(result["language"], "en")
        self.assertEqual(result["card"], f"{PLACE}\n{ADDRESS}\n{ARRIVE}")
        self.assertEqual(result["card"].count("\n"), 2)
        self.assertNotIn(JA_PREFIX, result["card"])
        self.assertNotIn("s'il vous plaît", result["card"])

    def test_partial_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            [],
            12,
            {"placeName": PLACE},
            {"language": "ja", "placeName": PLACE, "address": None, "arriveAt": None},
            {
                "arguments": {
                    "language": "ja",
                    "placeName": PLACE,
                    "address": ADDRESS,
                    "arriveAt": ARRIVE,
                }
            },
        ]
        for case in cases:
            result = phrase_card(case)
            self.assertEqual(set(result), {"language", "card"})
            self.assertIsInstance(result["language"], str)
            self.assertIsInstance(result["card"], str)

        wrapped = phrase_card(
            {
                "arguments": {
                    "language": "ja",
                    "placeName": PLACE,
                    "address": ADDRESS,
                    "arriveAt": ARRIVE,
                }
            }
        )
        self.assertEqual(wrapped["card"], f"{JA_PREFIX}\n{PLACE}\n{ADDRESS}\n{ARRIVE}")

        blank_lines = phrase_card(
            {"language": "en", "placeName": PLACE, "address": None, "arriveAt": None}
        )
        self.assertEqual(blank_lines["card"], f"{PLACE}\n\n")

    def test_tool_spec_is_phrase_card(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "phrase_card")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["language", "placeName", "address", "arriveAt"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["language", "card"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("requests a ride", TOOL_SPEC["description"])
        self.assertIn(JA_PREFIX, TOOL_SPEC["description"])
        self.assertIn(FR_PREFIX, TOOL_SPEC["description"])
        self.assertIn("no translation API", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "phrase_card")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_phrase_card(self) -> None:
        payload = _payload("ja")
        self.assertEqual(handler(payload), phrase_card(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___phrase_card"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), phrase_card(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___book_flight"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored, {"language": "", "card": ""})

    def test_sandbox_sources_do_not_touch_network_or_translation(self) -> None:
        banned = (
            "import boto",
            "import requests",
            "from requests",
            "import urllib",
            "http.client",
            "import socket",
            "subprocess",
            "import translate",
            "deepl",
            "openai",
        )
        for module in (phrase_mod, tool_mod):
            source = inspect.getsource(module)
            for word in banned:
                self.assertNotIn(word, source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("phrase_card opened a connection")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
