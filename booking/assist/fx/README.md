# Currency quote

Quotes a vendor charge into the trip currency. The master agent calls `quote_fx` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime before `authorize_spend` when the vendor currency is not the trip currency.

Sandbox only. Rates are fixed in this package. The tool does not fetch a live rate, submit an XRPL transaction, or call AWS. Entry checks, opening hours, transfers, weather, emergency numbers, and the master loop stay with their own tools.

```python
from booking.assist.fx import AGENTCORE_TOOL, TOOL_SPEC, handler, quote_fx

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a quote_fx tool call, call handler(tool_input).
```

Tool name: `quote_fx`.

## Input

| Field | Meaning |
| --- | --- |
| `amount` | Vendor charge. A number or a decimal string. Zero or more. |
| `fromCurrency` | Currency the vendor charged, such as `JPY`. |
| `toCurrency` | Trip currency to quote into, such as `USD`. |

## Output

```json
{
  "amount": 6.7,
  "currency": "USD",
  "rate": 0.0067,
  "source": "sandbox",
  "reason": "quoted"
}
```

| Field | Meaning |
| --- | --- |
| `amount` | Quoted amount in `toCurrency`, rounded to 2 decimal places. `null` when the currency is unknown or the amount is not usable. |
| `currency` | Trip currency the amount is quoted in. |
| `rate` | Units of `toCurrency` for one unit of `fromCurrency`. `1` when the currencies match. `null` when the quote cannot be made. |
| `source` | Always `sandbox`. |
| `reason` | `quoted`, `same_currency`, `unknown_currency`, or `invalid_amount`. |

## Rates

Sandbox rates are how many USD one unit of that currency buys.

| Currency | USD per 1 unit |
| --- | --- |
| USD | 1 |
| EUR | 1.08 |
| GBP | 1.27 |
| JPY | 0.0067 |

`1000` JPY quoted to USD is `6.70` (`1000 * 0.0067`), returned as `6.7`. A quote into a trip currency other than USD crosses these rates: divide the USD value by the trip currency's USD rate. The amount is rounded half up to 2 decimal places.

The same currency returns rate `1` and the same amount after that rounding. `1000` USD to USD stays `1000`.

An unknown currency returns `amount` `null`, `rate` `null`, and `reason` `unknown_currency`. A negative, missing, or non-numeric amount returns `amount` `null` and `reason` `invalid_amount`. A partial payload returns a result and does not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.fx.test_quote
```
