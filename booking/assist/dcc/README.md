# Dynamic currency conversion refusal

Refuses a terminal offer to pay in a currency other than the merchant's. The tourist rule is to pay the merchant's currency. Dynamic currency conversion is the prompt that charges the traveler in some other currency, usually their home currency, at the terminal's rate. That rate is the acquirer's markup. This tool refuses the offer. It pays the merchant amount in the merchant currency. It does not convert, and it ignores the offered amount.

There is no live terminal. The caller passes the two amounts and the two currencies. Sandbox only. The tool does not charge a card, open the network, or call AWS.

This package does not wire the master loop. A later integrator registers `refuse_dcc` on the master.

```python
from booking.assist.dcc import AGENTCORE_TOOL, TOOL_SPEC, handler, refuse_dcc

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a refuse_dcc tool call, call handler(tool_input).
```

Tool name: `refuse_dcc`.

## Why DCC is refused

A merchant in Japan prices a bill in yen. The terminal then offers to charge US dollars instead. Accepting that offer locks in the terminal's conversion, which is worse for the traveler than paying yen and letting the card network convert. The rule is to decline the offer and pay the merchant's currency. `offeredAmount` is not the payment and is not run through a rate.

When the offered currency is already the merchant currency, nothing was converted, so the charge is local and is not refused.

## Input

| Field | Meaning |
| --- | --- |
| `merchantAmount` | Amount on the merchant bill. A number or a decimal string. Zero or more. |
| `merchantCurrency` | Currency the merchant charged, such as `JPY`. This is the currency to pay. |
| `offeredAmount` | Amount the terminal offered. A number or a decimal string. Zero or more. Ignored for the payment. |
| `offeredCurrency` | Currency the terminal offered. Compared to `merchantCurrency` without case. |

## Output

```json
{
  "payAmount": 1500,
  "payCurrency": "JPY",
  "refused": true,
  "reason": "dcc_refused"
}
```

That result is a ¥1500 bill with a USD offer. The payment stays ¥1500.

| Field | Meaning |
| --- | --- |
| `payAmount` | `merchantAmount`, rounded. `0` when an amount is bad or negative. |
| `payCurrency` | `merchantCurrency`, trimmed. Empty when it was missing. |
| `refused` | `false` when the currencies match. `true` when they differ or an amount is bad. |
| `reason` | `local_currency`, `dcc_refused`, or `invalid_amount`. |

## Rules

`offeredCurrency` equal to `merchantCurrency`, compared without case: `refused` is `false`, `payAmount` is `merchantAmount`, `payCurrency` is `merchantCurrency`, and `reason` is `local_currency`.

The currencies differ: `refused` is `true`, `payAmount` is `merchantAmount`, `payCurrency` is `merchantCurrency`, and `reason` is `dcc_refused`. `offeredAmount` is ignored. Do not convert.

A bad or negative `merchantAmount` or `offeredAmount`: `payAmount` is `0`, `refused` is `true`, and `reason` is `invalid_amount`. Zero is allowed. A partial payload returns a result and does not raise.

Money is rounded half up. JPY uses 0 decimal places, so `1500.5` JPY pays `1501`. Every other currency uses 2 decimal places, so `10.005` USD pays `10.01`. A whole number is returned as an integer.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.dcc.test_dcc
```

The tests cover a local-currency accept, a USD offer on a JPY bill, and an invalid amount. They stay in-process. They do not call a live terminal.
