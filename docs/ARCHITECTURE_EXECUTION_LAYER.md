# The execution layer — the first component that can touch real capital

## Read this before using anything in `brokers/` or `agents/execution_engine.py`

Everything else in this platform is research: it produces reports,
scores, backtests, and proposed allocations, none of which can move
money on their own. This is different. `brokers/alpaca_connector.py`
can place real orders. That changes what "tested" means here.

## The safety model, in full

**1. Paper trading is the only default, anywhere.** Constructing
`AlpacaConnector` with just an API key and secret always uses Alpaca's
paper endpoint (`paper-api.alpaca.markets`), regardless of anything in
`.env` or the environment.

**2. Live trading requires a literal Python `True`, written in code,
every time.** `live_trading_confirmed=True` is the only way to reach the
live endpoint. This is checked with `is not True`, not a truthy check —
proven directly with a parametrized test covering `1`, `"True"`,
`"true"`, `"yes"`, `"live"`, a non-empty list, a non-empty dict, and
`1.0`. Every one of them still results in paper trading. Only the exact
boolean `True` works.

**3. This is deliberately NOT configurable via `.env` or any environment
variable.** Every other credential in this project lives in `.env` —
API keys, tokens, thresholds. A live-trading switch does not, on
purpose. A config value can sit forgotten in a file for months (this
project already found exactly that failure mode once today, with a
duplicated `TELEGRAM_BOT_TOKEN` line silently breaking something else).
A decision this consequential needs a human to consciously write it in
code each time, not something that persists silently.

**4. `execute_rebalance()` defaults to `dry_run=True`.** This is a
SEPARATE layer of protection from paper-vs-live — it applies even
against a paper-configured broker. In dry-run mode, no order is ever
submitted; planned orders are computed and returned with
`status=PENDING` only. Proven directly with a broker that raises an
exception if any of its methods are called at all — the dry-run path
never touches it, even without an explicit `dry_run=True` argument (the
default already protects you).

**5. `scripts/demo_execution_engine.py` never offers a live-trading flag
at all.** Three levels, each an explicit opt-in beyond the last: plan
with fake data (no network) → connect to real paper account, read-only
→ submit to paper only. Enabling live trading isn't a CLI flag away from
any script this platform ships — it requires writing
`live_trading_confirmed=True` directly into your own code.

## Live verification status

A real Alpaca paper account was used to test this connector directly —
the first genuine live exercise of anything in the execution layer,
using a real 1-share AAPL buy order. Everything tested passed on the
first attempt:

**Confirmed working against real Alpaca responses:**
- `get_account()` — real equity ($100,000.00) and cash matched the
  Alpaca dashboard exactly; `is_paper` correctly reported `True` with
  real credentials, confirming the paper-by-default safety property
  holds under genuinely live conditions, not just mocked tests
- `get_positions()` — confirmed against both an empty account (before
  the test order) and a real populated one afterward
  (`BrokerPosition(symbol='AAPL', quantity=1.0, average_entry_price=303.37,
  current_price=303.37)`), consistent with the fill reported separately
  by `get_order_status()` — two different endpoints agreeing on the
  same real transaction
- `submit_order()` — a real order was placed and accepted; Alpaca
  returned a genuine UUID order ID, correctly mapped to
  `OrderStatus.SUBMITTED` with `rejection_reason` correctly `None`
- `get_order_status()` — correctly reported the order as filled
  (`OrderStatus.FILLED`, `filled_quantity=1.0`,
  `average_fill_price=303.37`), the first real confirmation that `Fill`
  construction and the `Order.filled_quantity`/`average_fill_price`
  properties (previously only exercised with synthetic test data) work
  correctly with a real response flowing through the entire chain

**Still genuinely unverified:**
- `cancel_order()` — not yet exercised against a real order
- A REAL Alpaca rejection response — the mocked tests prove the code's
  own error-handling logic is internally correct (reading the response
  body for a real `message` field before reporting, mirroring
  `telegram_alerter.py`'s earlier fix), but no genuine rejection from
  Alpaca has been seen yet to confirm the exact shape matches

**Practical implication for what's left**: treat `cancel_order()` and
the rejection path with the same caution the rest of this module had
before today — test them against paper before relying on them, and
still long before ever considering `live_trading_confirmed=True`.

## What's built

- **`models/order.py`** — `Order`/`Fill`, with real validation (a
  negative or zero quantity raises immediately; a `LIMIT` order without
  a `limit_price` raises immediately), and `average_fill_price` computed
  correctly across multiple partial fills, not just the first one.
- **`brokers/broker_interface.py`** — an abstract interface any broker
  connector must implement, so the execution engine and everything
  above it stays broker-agnostic. A second broker later means one new
  connector against this interface, not a rewrite of anything
  downstream.
- **`brokers/alpaca_connector.py`** — the concrete Alpaca implementation.
  A rejected order returns cleanly with `status=REJECTED` and a real
  reason — proven directly, including for a genuine network failure
  during submission — never an uncaught exception that could crash an
  unattended loop. Error responses are read for their real `message`
  field before being reported, the same fix already applied to
  `telegram/telegram_alerter.py` earlier in this project.
- **`agents/execution_engine.py`** — `plan_rebalance()` converts a
  target allocation (the output shape of
  `agents.portfolio_construction.apply_position_constraints()`) plus
  current broker positions into planned orders. A symbol with a current
  position but no target weight gets a full closing order — an
  allocation that no longer mentions something means "don't hold this,"
  not "leave it untouched," proven directly. A missing price for a
  target symbol means that symbol is SKIPPED, never estimated. Orders
  below `min_order_value` are filtered out, avoiding cost-inefficient
  micro-rebalancing.

## Testing

41 new tests across `tests/test_order_model.py`,
`tests/test_alpaca_connector.py`, and `tests/test_execution_engine.py`.
The safety-model tests are the most important tests in this entire
project — every truthy-but-not-`True` value proven unable to enable live
trading, the dry-run default proven against a broker that would raise
if touched at all, and order rejection/network-failure paths proven to
return cleanly rather than propagate an uncaught exception.

**698 tests total, all passing.**
