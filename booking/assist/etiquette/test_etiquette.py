"""Etiquette card: fixed sandbox phrases for Japan, France, and the United States.

These tests stay in-process. They do not call a translation API, open a
connection, or call AWS. The card is etiquette, not medical, legal, or
safety advice, and not a map.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.etiquette import AGENTCORE_TOOL, TOOL_SPEC, etiquette_card, handler
from booking.assist.etiquette import card as card_mod
from booking.assist.etiquette import tool as tool_mod

FIELDS = {
    "country",
    "kind",
    "rules",
    "phrase",
    "phraseLanguage",
    "phraseMeaning",
    "reason",
}
JAPAN_WORSHIP_RULES = [
    "shoes off before the hall",
    "bow once at the gate",
    "photography of the inner hall is restricted",
]
JAPAN_RESTAURANT_RULES = [
    "no tipping",
    "shoes off only at a tatami room",
]
FRANCE_MUSEUM_RULES = [
    "quiet inside",
    "shoulders covered",
]
WRONG_FRENCH = "Bonjour, un s'il vous plaît"


def _payload(country: str, place_name: str, kind: str) -> dict:
    return {"country": country, "placeName": place_name, "kind": kind}


class EtiquetteCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_japan_shrine_has_the_photo_card(self) -> None:
        result = etiquette_card(_payload("Japan", "Fushimi Inari", "shrine"))

        self.assertEqual(
            result,
            {
                "country": "Japan",
                "kind": "shrine",
                "rules": JAPAN_WORSHIP_RULES,
                "phrase": "写真は大丈夫ですか",
                "phraseLanguage": "ja",
                "phraseMeaning": "May I take a photo?",
                "reason": "none",
            },
        )
        self.assertNotIn(WRONG_FRENCH, json.dumps(result))

    def test_japan_temple_uses_the_same_card(self) -> None:
        result = etiquette_card("Japan", "Kiyomizu-dera", "temple")

        self.assertEqual(result["country"], "Japan")
        self.assertEqual(result["kind"], "temple")
        self.assertEqual(result["rules"], JAPAN_WORSHIP_RULES)
        self.assertEqual(result["phrase"], "写真は大丈夫ですか")
        self.assertEqual(result["phraseLanguage"], "ja")
        self.assertEqual(result["phraseMeaning"], "May I take a photo?")
        self.assertEqual(result["reason"], "none")

    def test_japan_restaurant_has_the_reservation_card(self) -> None:
        result = etiquette_card(
            country="Japan",
            placeName="Ishikawa",
            kind="restaurant",
        )

        self.assertEqual(result["rules"], JAPAN_RESTAURANT_RULES)
        self.assertEqual(result["phrase"], "予約しています")
        self.assertEqual(result["phraseLanguage"], "ja")
        self.assertEqual(result["phraseMeaning"], "I have a reservation.")
        self.assertEqual(result["reason"], "none")
        self.assertNotEqual(result["phrase"], "写真は大丈夫ですか")

    def test_france_museum_asks_before_a_photo(self) -> None:
        result = etiquette_card(_payload("France", "Sainte-Chapelle", "museum"))

        self.assertEqual(result["country"], "France")
        self.assertEqual(result["kind"], "museum")
        self.assertEqual(result["rules"], FRANCE_MUSEUM_RULES)
        self.assertEqual(result["phrase"], "Pardon, une photo est-elle permise ?")
        self.assertEqual(result["phraseLanguage"], "fr")
        self.assertEqual(result["phraseMeaning"], "Excuse me, are photos allowed?")
        self.assertEqual(result["reason"], "none")
        self.assertNotIn(WRONG_FRENCH, result["phrase"])
        self.assertNotIn("shoes off", " ".join(result["rules"]))

    def test_united_states_stop_has_no_card(self) -> None:
        result = etiquette_card(_payload("United States", "The Met", "museum"))

        self.assertEqual(set(result), FIELDS)
        self.assertEqual(result["country"], "United States")
        self.assertEqual(result["kind"], "museum")
        self.assertEqual(result["rules"], [])
        self.assertIsNone(result["phrase"])
        self.assertIsNone(result["phraseLanguage"])
        self.assertIsNone(result["phraseMeaning"])
        self.assertEqual(result["reason"], "none")
        self.assertIsNone(json.loads(json.dumps(result))["phrase"])

    def test_unknown_country_has_no_card(self) -> None:
        result = etiquette_card(_payload("Wakanda", "Palace", "shrine"))

        self.assertEqual(result["country"], "Wakanda")
        self.assertEqual(result["kind"], "shrine")
        self.assertEqual(result["rules"], [])
        self.assertIsNone(result["phrase"])
        self.assertIsNone(result["phraseLanguage"])
        self.assertIsNone(result["phraseMeaning"])
        self.assertEqual(result["reason"], "unknown_country")

    def test_known_country_without_a_matching_kind_is_reason_none(self) -> None:
        japan_museum = etiquette_card(_payload("Japan", "Tokyo National Museum", "museum"))
        self.assertEqual(japan_museum["country"], "Japan")
        self.assertEqual(japan_museum["rules"], [])
        self.assertIsNone(japan_museum["phrase"])
        self.assertEqual(japan_museum["reason"], "none")

        france_general = etiquette_card(_payload("France", "A cafe", "general"))
        self.assertEqual(france_general["country"], "France")
        self.assertEqual(france_general["kind"], "general")
        self.assertEqual(france_general["rules"], [])
        self.assertIsNone(france_general["phrase"])
        self.assertEqual(france_general["reason"], "none")

    def test_country_aliases_stay_inside_the_sandbox_directory(self) -> None:
        self.assertEqual(etiquette_card(_payload("jp", "Meiji Jingu", "shrine"))["country"], "Japan")
        self.assertEqual(etiquette_card(_payload("FR", "Louvre", "museum"))["phraseLanguage"], "fr")
        self.assertEqual(etiquette_card(_payload("USA", "Times Square", "general"))["reason"], "none")
        self.assertEqual(etiquette_card(_payload("US", "Times Square", "general"))["rules"], [])
        self.assertEqual(
            etiquette_card(_payload("United States of America", "Times Square", "restaurant"))["country"],
            "United States",
        )

    def test_place_name_does_not_change_the_card(self) -> None:
        first = etiquette_card(_payload("Japan", "Fushimi Inari", "shrine"))
        second = etiquette_card(_payload("Japan", "A different gate", "shrine"))
        self.assertEqual(first, second)

        named_like_a_shrine = etiquette_card(_payload("Japan", "Shrine Cafe", "restaurant"))
        self.assertEqual(named_like_a_shrine["rules"], JAPAN_RESTAURANT_RULES)

    def test_missing_fields_do_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"placeName": "Fushimi Inari"},
            {"country": "Japan"},
            {"country": None, "placeName": None, "kind": None},
            {"arguments": {"country": "Japan", "placeName": "Fushimi Inari", "kind": "shrine"}},
            {"input": {"country": "France", "place_name": "Louvre", "kind": "museum"}},
        ]
        for case in cases:
            result = etiquette_card(case)
            self.assertEqual(set(result), FIELDS)
            self.assertIsInstance(result["country"], str)
            self.assertIsInstance(result["kind"], str)
            self.assertIsInstance(result["rules"], list)
            self.assertTrue(result["phrase"] is None or isinstance(result["phrase"], str))
            self.assertIn(result["reason"], {"none", "unknown_country"})

        named = etiquette_card({"country": "Japan", "placeName": "Fushimi Inari", "kind": "SHRINE"})
        self.assertEqual(named["kind"], "shrine")
        self.assertEqual(named["rules"], JAPAN_WORSHIP_RULES)

        missing_country = etiquette_card({"kind": "shrine"})
        self.assertEqual(missing_country["rules"], [])
        self.assertIsNone(missing_country["phrase"])
        self.assertEqual(missing_country["reason"], "unknown_country")

    def test_json_object_is_one_card(self) -> None:
        raw = '{"country":"Japan","placeName":"Fushimi Inari","kind":"shrine"}'
        result = etiquette_card(raw)
        self.assertEqual(result["phrase"], "写真は大丈夫ですか")
        self.assertEqual(result["rules"], JAPAN_WORSHIP_RULES)

    def test_tool_spec_is_etiquette_card(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "etiquette_card")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["country", "placeName", "kind"])
        self.assertEqual(TOOL_SPEC["inputSchema"]["properties"]["kind"]["enum"], [
            "shrine",
            "temple",
            "museum",
            "restaurant",
            "general",
        ])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["country", "kind", "rules", "phrase", "phraseLanguage", "phraseMeaning", "reason"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("AgentCore", description)
        self.assertIn("unknown_country", description)
        self.assertIn("写真は大丈夫ですか", description)
        self.assertIn("Pardon, une photo est-elle permise ?", description)
        self.assertNotIn(WRONG_FRENCH, description)
        self.assertIn("no translation API", description)
        self.assertIn("not a map", description.lower())
        self.assertIn("Not medical, legal, or safety advice", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "etiquette_card")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_etiquette_card(self) -> None:
        payload = _payload("Japan", "Fushimi Inari", "shrine")
        self.assertEqual(handler(payload), etiquette_card(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___etiquette_card"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), etiquette_card(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___phrase_card"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(set(ignored), FIELDS)
        self.assertEqual(ignored["rules"], [])
        self.assertIsNone(ignored["phrase"])
        self.assertEqual(ignored["reason"], "unknown_country")

    def test_sandbox_sources_do_not_touch_network_translation_or_aws(self) -> None:
        for module in (card_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("httpx", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("subprocess", source)
            self.assertNotIn("booking.master", source)
            self.assertNotIn("booking.assist.phrase", source)
            self.assertNotIn(WRONG_FRENCH, source)
            lowered = source.lower()
            self.assertNotIn("deepl", lowered)
            self.assertNotIn("googletrans", lowered)
            self.assertNotIn("translate.google", lowered)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("etiquette_card opened a connection")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
