# Driver phrase card

Builds the card a traveler shows a driver. The master agent calls `phrase_card` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when it requests a ride. This package does not run that loop, does not request the ride, and does not translate the place name, the address, or the arrival text.

Sandbox only. The tool does not call a translation API, open the network, or call AWS.

```python
from booking.assist.phrase import AGENTCORE_TOOL, TOOL_SPEC, handler, phrase_card

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a phrase_card tool call, call handler(tool_input).
```

Tool name: `phrase_card`.

## Input

| Field | Meaning |
| --- | --- |
| `language` | `ja` adds the Japanese line. `fr` adds the French line. Any other code does not. |
| `placeName` | Place the driver is going. Copied as given. Missing or blank makes `card` an empty string. |
| `address` | Street address. Copied as given. |
| `arriveAt` | Arrival text. Copied as given. |

## Output

```json
{
  "language": "ja",
  "card": "こちらまでお願いします\n金閣寺\n京都府京都市北区金閣寺町1\n2026-11-03 09:00"
}
```

| Field | Meaning |
| --- | --- |
| `language` | From the input. Empty when the input has no language code. |
| `card` | Text the traveler can show a driver. Empty when `placeName` is missing. |

When `placeName` is present, `card` is three lines: `placeName`, `address`, then `arriveAt`. `ja` prefixes that card with `こちらまでお願いします`. `fr` prefixes it with `À cette adresse, s'il vous plaît`. The prefix is its own first line. Any other language has no prefix. A partial input returns a result and does not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.phrase.test_phrase
```
