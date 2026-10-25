# Tax refund quote

This is a quote, not tax advice.

Quotes a departure tax refund from eligible purchases. The master agent calls `tax_refund` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run that loop. A later integrator wires this tool into the master.

Sandbox only. The rates below are fixed in this package. The tool does not call a tax-authority API, submit a claim, open the network, or call AWS. The caller supplies `now`. The tool does not read the clock.

```python
from booking.assist.taxrefund import AGENTCORE_TOOL, TOOL_SPEC, handler, tax_refund

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a tax_refund tool call, call handler(tool_input).
```

Tool name: `tax_refund`.

## Input

| Field | Meaning |
| --- | --- |
| `country` | `Japan` (`JP`) or `France` (`FR`). Any other country is status `none`. |
| `purchases` | Lines of `{amount, currency, eligible}`. `amount` is a number or a decimal string. |
| `departAt` | ISO-8601 departure time, such as `2026-11-06T16:00:00Z`. The claim deadline. |
| `now` | ISO-8601 instant of the quote, supplied by the caller. |

## Output

```json
{
  "status": "eligible",
  "refundAmount": 1000,
  "refundCurrency": "JPY",
  "eligibleSpend": 10000,
  "claimBefore": "2026-11-06T16:00:00Z",
  "reason": "quoted"
}
```

| Field | Meaning |
| --- | --- |
| `status` | `eligible`, `too_small`, `missed`, or `none`. |
| `refundAmount` | Rate times eligible spend. `0` when status is `too_small` or `none`. Still the quoted amount when status is `missed`. |
| `refundCurrency` | `JPY` for Japan, `EUR` for France. Empty when the country is not supported. |
| `eligibleSpend` | Eligible lines in the refund currency, after rounding. `0` when the country is not supported. |
| `claimBefore` | `departAt` in UTC (`YYYY-MM-DDTHH:MM:SSZ`) when status is `eligible` or `missed`. `null` otherwise. |
| `reason` | `quoted`, `below_minimum`, `departed`, `unsupported_country`, `invalid_time`, or `invalid_input`. |

## Rates

Only eligible lines whose currency is the refund currency are summed. Other currencies are ignored and are not converted. A line counts only when `eligible` is true.

The sum is rounded half up first (JPY to 0 decimals, EUR to 2). That rounded total is `eligibleSpend`. It must meet the minimum. `refundAmount` is that total times the rate, rounded the same way.

| Country | Rate | Minimum eligible spend | Currency | Rounding |
| --- | --- | --- | --- | --- |
| Japan (`JP`) | 10% | 5000 JPY | JPY | 0 decimals |
| France (`FR`) | 20% | 100 EUR | EUR | 2 decimals |
| Anything else | none | — | — | `refundAmount` 0 |

`10000` eligible JPY is status `eligible` and `refundAmount` `1000`. `4000` eligible JPY is status `too_small` and `refundAmount` `0`. `5000` JPY is enough and refunds `500`.

`100` eligible EUR is status `eligible` and `refundAmount` `20`.

Spend under the minimum is `too_small` even when `now` is after `departAt`, and `refundAmount` stays `0`.

When the spend meets the minimum and `now` is after `departAt`, status is `missed`, `claimBefore` is `departAt`, and `refundAmount` is still the quoted amount. `now` equal to `departAt` is still `eligible`.

Any other country, including a blank country, returns status `none`, `refundAmount` `0`, and `reason` `unsupported_country`. A partial payload, bad JSON, and any other input return a result and do not raise.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.taxrefund.test_refund
```
