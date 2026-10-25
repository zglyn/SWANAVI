# Tip policy

Sets the country tip ceiling for a sandbox charge. The master agent calls `tip_policy` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime before `authorize_spend`, so a vendor cannot add a tip past the country rule.

`authorizedAmount` from this tool is the ceiling the spend guard must use. Pass it as `authorizedAmount` on `authorize_spend`. This package does not call `authorize_spend`, does not run the master loop, and does not charge a card.

Sandbox only. The percents are fixed below. The tool does not open the network and does not call AWS.

```python
from booking.assist.tip import AGENTCORE_TOOL, TOOL_SPEC, handler, tip_policy

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a tip_policy tool call, call handler(tool_input).
```

Tool name: `tip_policy`.

## Input

| Field | Meaning |
| --- | --- |
| `country` | Country for the sandbox tip percent. |
| `subtotal` | Charge before the tip. A number or a decimal string. |
| `currency` | Currency code, passed through unchanged. |

## Output

```json
{
  "maxTipPercent": 20,
  "tipAmount": 2,
  "authorizedAmount": 12,
  "currency": "USD",
  "reason": "country_rule"
}
```

| Field | Meaning |
| --- | --- |
| `maxTipPercent` | Sandbox percent for the country. |
| `tipAmount` | `subtotal * maxTipPercent / 100`, rounded to 2 decimals. `null` when the subtotal is missing or not a usable amount. |
| `authorizedAmount` | `subtotal + tipAmount`, rounded to 2 decimals. The ceiling the spend guard must use. `null` when `tipAmount` is null. |
| `currency` | Currency from the input. Empty when the caller did not send one. |
| `reason` | `country_rule` when the ceiling was computed. `missing_subtotal` when the subtotal is missing. `invalid_subtotal` when the subtotal is not a finite amount of zero or more. |

## Rules

Sandbox percents:

| Country | `maxTipPercent` |
| --- | --- |
| Japan | 0 |
| United States (`US`, `USA`) | 20 |
| France | 0 |
| Anything else | 10 |

Japan at subtotal 10: `tipAmount` is 0 and `authorizedAmount` is 10.

United States at subtotal 10: `maxTipPercent` is 20, `tipAmount` is 2, and `authorizedAmount` is 12.

France at subtotal 10: `tipAmount` is 0 and `authorizedAmount` is 10.

A missing subtotal, including a payload that omits it, returns `tipAmount` null and `reason` `missing_subtotal`. `maxTipPercent` is still the country percent. A partial payload, bad JSON, and any other input return a result and do not raise.

Amounts use decimal arithmetic and round half up to 2 decimals.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.tip.test_tip
```
