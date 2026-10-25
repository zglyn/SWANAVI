# Emergency card

Returns sandbox emergency and embassy phone numbers. The master agent calls `emergency_card` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when the traveler asks for help. This package does not run that loop.

It returns phone numbers only, not medical guidance. It does not give doses or treatment steps.

Sandbox only. The tool reads a fixed directory for Japan, France, and the United States. It does not open the network or call AWS. Other assist agents and the master loop stay with their own packages.

```python
from booking.assist.emergency import AGENTCORE_TOOL, TOOL_SPEC, emergency_card, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns an emergency_card tool call, call handler(tool_input).
```

Tool name: `emergency_card`.

## Input

| Field | Meaning |
| --- | --- |
| `country` | Country the traveler is in. Japan, France, and the United States are the sandbox directory. |
| `travelerName` | Traveler name. Copied into the note. This tool does not look the traveler up. |

`JP`, `FR`, and `US` (and `USA`) select the same three directory rows. Any other country is unknown.

## Output

```json
{
  "country": "Japan",
  "emergencyNumber": "110",
  "embassyPhone": "+81-3-3224-5000",
  "note": "Emergency and embassy phone numbers for Ada Lovelace. Phone numbers only."
}
```

| Field | Meaning |
| --- | --- |
| `country` | `Japan`, `France`, or `United States` when the directory matches. Otherwise the country text the caller sent. |
| `emergencyNumber` | Sandbox emergency phone. `110` for Japan, `112` for France, `911` for the United States. |
| `embassyPhone` | Sandbox embassy phone for a known country. `null` when the country is unknown. |
| `note` | Includes `travelerName`. Includes `unknown_country` when the country is not in the directory. Phone numbers only. |

### Sandbox directory

| Country | Emergency number | Embassy phone |
| --- | --- | --- |
| Japan | 110 | +81-3-3224-5000 |
| France | 112 | +33-1-4312-2222 |
| United States | 911 | +1-202-555-0100 |

An unknown country returns emergency number `112`, embassy phone `null`, and a note that includes `unknown_country` and `travelerName`.

```json
{
  "country": "Wakanda",
  "emergencyNumber": "112",
  "embassyPhone": null,
  "note": "unknown_country for Ada Lovelace. Phone numbers only."
}
```

A partial input returns a result and does not raise. An empty traveler name still returns the numbers. The unknown-country note is `unknown_country` when no name was sent.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.emergency.test_emergency
```

Japan returns `110`. An unknown country returns `112` and a null embassy phone.
