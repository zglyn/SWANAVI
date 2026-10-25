# Card choice

Picks a sandbox Mastercard for a merchant charge. Register `pick_card` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run the master loop and does not charge a card. A later integrator wires `pick_card` into the master.

Sandbox only. Cards in the input are fake fixtures. The tool does not open the network, does not read real card data, and does not call AWS.

```python
from booking.assist.card import AGENTCORE_TOOL, TOOL_SPEC, handler, pick_card

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a pick_card tool call, call handler(tool_input).
```

Tool name: `pick_card`.

## Input

| Field | Meaning |
| --- | --- |
| `merchantCountry` | Merchant country as an ISO-ish name or code. `Japan` and `JP` match. `France` and `FR` match. `US` matches `US`. |
| `amount` | Charge before the foreign-exchange fee. A number or a decimal string. Zero or more. |
| `currency` | Currency code, passed through unchanged except for surrounding whitespace. |
| `cards` | Fake fixture cards. An empty list is allowed. |

Each card:

| Field | Meaning |
| --- | --- |
| `id` | Fixture id. Not a real card number. |
| `network` | Card network. `mastercard` is matched case-insensitively. |
| `fxFeePercent` | Foreign-exchange fee percent used when the country is not covered. |
| `noFxCountries` | Countries where this fixture charges no foreign-exchange fee. |

## Output

```json
{
  "cardId": "mc-japan",
  "fxFeePercent": 0,
  "feeAmount": 0,
  "payAmount": 1000,
  "currency": "JPY",
  "reason": "no_fx_fee"
}
```

| Field | Meaning |
| --- | --- |
| `cardId` | Id of the chosen fixture Mastercard. `null` when none is chosen. |
| `fxFeePercent` | `0` when the merchant country is covered. The chosen card's percent otherwise. `null` when no Mastercard is chosen. |
| `feeAmount` | `amount * fxFeePercent / 100`, rounded half up. `0` when the fee does not apply or the amount is negative. |
| `payAmount` | `amount + feeAmount`, rounded half up. `0` when the amount is not usable. |
| `currency` | Currency from the input. Empty when the caller did not send one. |
| `reason` | `no_fx_fee`, `lowest_fee`, `no_mastercard`, or `invalid_amount`. |
| `status` | `needs_user` when no Mastercard is available. Present only on that result. |

## Selection rule

Only a card whose network is `mastercard` (any case, spaces ignored) can be chosen. Visa and Amex are never selected.

1. Prefer a Mastercard whose `noFxCountries` includes the merchant country. `Japan` and `JP` are the same country, `France` and `FR` are the same country, and `US` matches `US`. The result uses `fxFeePercent` 0, `feeAmount` 0, and reason `no_fx_fee`. The first matching Mastercard in the list wins.
2. Otherwise pick the Mastercard with the lowest `fxFeePercent`. `feeAmount` is `amount * fxFeePercent / 100`. Reason is `lowest_fee`. Equal percents keep the first card.
3. When the list has no Mastercard, the result is needs_user: `status` is `needs_user`, `cardId` is null, and `reason` is `no_mastercard`. `feeAmount` is 0. `payAmount` is the rounded amount. Do not charge: `cardId` is null.
4. A negative, missing, or non-numeric amount returns `feeAmount` 0, `payAmount` 0, and reason `invalid_amount`. No card is chosen.

`payAmount` is `amount + feeAmount`. Both money fields round half up to 2 decimal places. Currency `JPY` (any case) rounds to 0 decimal places. `100` JPY at 2.5% is a fee of `3` and a payment of `103`. `10` USD at 1.25% is a fee of `0.13` and a payment of `10.13`.

A partial payload returns a result and does not raise.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.card.test_card
```

The tests cover Japan on a no-FX Mastercard, a 3% fallback, and a Visa-only needs_user result. Fixture ids are fake.
