# Cash needed

Decides whether a merchant needs cash, and quotes that cash into the trip currency. The master agent calls `cash_needed` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime when a merchant may not take a card.

A later integrator wires this tool into the master. This package does not edit the master, does not run that loop, and does not call `quote_fx`.

Sandbox only. Rates are fixed in this package and match the fx quote table. The tool does not fetch a live rate, open the network, or call an ATM API.

```python
from booking.assist.cash import AGENTCORE_TOOL, TOOL_SPEC, cash_needed, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a cash_needed tool call, call handler(tool_input).
```

Tool name: `cash_needed`.

## Input

| Field | Meaning |
| --- | --- |
| `merchant.name` | Merchant name, copied into the result. |
| `merchant.acceptsCard` | `true` pays by card. `false` withdraws cash. |
| `merchant.amount` | Merchant charge. A number or a decimal string. Zero or more. |
| `merchant.currency` | Currency the merchant charged, such as `JPY`. |
| `tripCurrency` | Trip currency to quote the cash into. Defaults to `USD`. |

## Output

```json
{
  "merchant": "Market",
  "action": "withdraw_cash",
  "cashAmount": 1000,
  "cashCurrency": "JPY",
  "tripAmount": 6.7,
  "tripCurrency": "USD",
  "reason": "quoted"
}
```

| Field | Meaning |
| --- | --- |
| `merchant` | Merchant name. Empty when the input has no name. |
| `action` | `pay_card` when the merchant takes a card. `withdraw_cash` when the traveler needs cash. Empty when the amount is not usable. |
| `cashAmount` | Cash to withdraw in the merchant currency. `0` when the merchant takes a card or the amount is not usable. |
| `cashCurrency` | Merchant currency. |
| `tripAmount` | `cashAmount` quoted into `tripCurrency`. `0` when the merchant takes a card. `null` when the currency is unknown or the amount is not usable. `1000` JPY quoted to USD is `6.70`, returned as `6.7`. |
| `tripCurrency` | Trip currency. `USD` when the caller did not send one. |
| `reason` | `card_accepted`, `quoted`, `unknown_currency`, or `invalid_amount`. |

## Rates

Sandbox rates are how many USD one unit of that currency buys. The numbers match the fx quote table.

| Currency | USD per 1 unit |
| --- | --- |
| USD | 1 |
| EUR | 1.08 |
| GBP | 1.27 |
| JPY | 0.0067 |

`1000` JPY quoted to USD is `6.70` (`1000 * 0.0067`). A quote into a trip currency other than USD crosses these rates: divide the USD value by the trip currency's USD rate. `1000` JPY into EUR is `6.20` (`1000 * 0.0067 / 1.08`).

USD, EUR, and GBP round half up to 2 decimal places. JPY rounds half up to 0 decimal places. The merchant amount is rounded to that currency first, and `tripAmount` quotes the rounded cash.

## Rules

- `acceptsCard` true: `action` is `pay_card`, `cashAmount` is 0, `tripAmount` is 0, and `reason` is `card_accepted`. The currency is not quoted.
- `acceptsCard` false: `action` is `withdraw_cash`, `cashAmount` is the merchant amount in `cashCurrency`, and `tripAmount` is that cash in `tripCurrency`. `reason` is `quoted`.
- An unknown merchant currency or trip currency: `action` is `withdraw_cash`, `tripAmount` is null, and `reason` is `unknown_currency`.
- A negative, missing, or non-numeric amount: `reason` is `invalid_amount`, `cashAmount` is 0, and `tripAmount` is null. This wins even when the merchant accepts a card.
- `tripCurrency` defaults to USD. A partial payload returns a result and does not raise.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.cash.test_cash
```
