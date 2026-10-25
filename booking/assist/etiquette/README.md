# Etiquette card

Returns a fixed etiquette card for one stop. The master agent calls `etiquette_card` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime before a shrine, temple, museum, restaurant, or other stop. This package does not run that loop.

The cards are fixed sandbox phrases. A later integrator wires the master. This package does not import the master and does not edit it.

This is etiquette. It does not give medical, legal, or safety advice, and it is not a map. The stop name is not looked up.

Sandbox only. The tool does not call a translation API, open the network, or call AWS.

```python
from booking.assist.etiquette import AGENTCORE_TOOL, TOOL_SPEC, etiquette_card, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns an etiquette_card tool call, call handler(tool_input).
```

Tool name: `etiquette_card`.

## Input

| Field | Meaning |
| --- | --- |
| `country` | Country of the stop. Japan, France, and the United States are the sandbox directory. |
| `placeName` | Stop name, accepted as given. Not used to choose the card. |
| `kind` | `shrine`, `temple`, `museum`, `restaurant`, or `general`. A church-like stop in France is `museum`. |

`JP`, `FR`, and `US` (and `USA`) select the same three directory countries. Any other country is unknown.

## Output

```json
{
  "country": "Japan",
  "kind": "shrine",
  "rules": [
    "shoes off before the hall",
    "bow once at the gate",
    "photography of the inner hall is restricted"
  ],
  "phrase": "写真は大丈夫ですか",
  "phraseLanguage": "ja",
  "phraseMeaning": "May I take a photo?",
  "reason": "none"
}
```

| Field | Meaning |
| --- | --- |
| `country` | `Japan`, `France`, or `United States` when the directory matches. Otherwise the country text the caller sent. |
| `kind` | The kind, lowercased, when it is one of the five kinds. Empty when it is missing or not one of those kinds. |
| `rules` | Fixed sandbox lines. Empty when this country and kind have no card. |
| `phrase` | Fixed sandbox phrase. `null` when this stop has no card. |
| `phraseLanguage` | `ja` or `fr` when `phrase` is set. `null` when `phrase` is null. |
| `phraseMeaning` | English meaning of `phrase`. `null` when `phrase` is null. |
| `reason` | `none` when the country is in the sandbox directory. `unknown_country` otherwise. |

`reason` `none` means the country is known. It does not mean a card was found. The United States is in the directory and has no card: `rules` is empty, `phrase` is null, and `reason` is `none`.

### Sandbox cards

| Country | Kind | Rules | Phrase | Language | Meaning |
| --- | --- | --- | --- | --- | --- |
| Japan | `shrine` or `temple` | shoes off before the hall; bow once at the gate; photography of the inner hall is restricted | 写真は大丈夫ですか | `ja` | May I take a photo? |
| Japan | `restaurant` | no tipping; shoes off only at a tatami room | 予約しています | `ja` | I have a reservation. |
| France | `museum` | quiet inside; shoulders covered | Pardon, une photo est-elle permise ? | `fr` | Excuse me, are photos allowed? |
| United States | any | none | null | null | null |
| Any other country | any | none | null | null | null |

A church-like stop in France uses kind `museum` and the same card. Japan with kind `museum` or `general`, and France with any kind other than `museum`, are known countries with no card: empty `rules`, null `phrase`, reason `none`.

An unknown country returns empty `rules`, a null `phrase`, and reason `unknown_country`.

```json
{
  "country": "Wakanda",
  "kind": "shrine",
  "rules": [],
  "phrase": null,
  "phraseLanguage": null,
  "phraseMeaning": null,
  "reason": "unknown_country"
}
```

A United States stop:

```json
{
  "country": "United States",
  "kind": "museum",
  "rules": [],
  "phrase": null,
  "phraseLanguage": null,
  "phraseMeaning": null,
  "reason": "none"
}
```

A partial input returns a result and does not raise.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.etiquette.test_etiquette
```

The tests cover a Japan shrine, a United States stop, and an unknown country. They stay in-process.
