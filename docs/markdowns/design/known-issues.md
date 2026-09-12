# Known Issues

Issues found while working through a single question: with no hedging in
the market making strategy, can it still make money? The answer turned
out to depend very little on hedging and a great deal on fees, fill
simulation, and inventory control, so the findings are recorded here
rather than in any one component's notes.

Each entry states what is wrong, why it matters, and what would resolve
it. Only open issues are listed: once something is fixed its entry is
removed, and the commit that fixed it is the record of what changed.

Arithmetic assumes BTC around $100,000 and the declared defaults of
`MarketMakingParameters`: `quote_size = 0.0005` and
`max_inventory = 0.01`. Where a quote offset matters, the figure given is
the one a paper session actually quotes:
`QuoteOffsetParameters.edge = 5.0`, which at that price asks $255 a side.

Every figure below is now a declared parameter that the dashboard can
change on a running engine, so these are the defaults an untuned session
starts from rather than the only values it can hold. See
[the parameters design note](parameters.md).

## Summary

| # | Issue | Severity |
|---|---|---|
| 1 | Fees exceed quoted edge by ~5x | Strategy cannot profit |
| 2 | Simulated queue position is always zero | Fill rate wildly overstated |
| 3 | Sweeps fill the whole remainder | Overstates size on adverse fills |
| 4 | No latency model | Queue position optimistic |
| 5 | Simulated book never reacts to our orders | Inherent to replay |
| 6 | A better fill model would be live-only | Cannot be backtested |

## 1. Fees exceed the quoted edge

`MarketMakingStrategy.on_bbo` quotes at `mid ±` whatever its
`IQuoteOffsetService` returns. Under the `StaticQuoteOffsetService`
default that is a flat `half_spread` on each side, and
`MidPriceFairPriceModel` returns mid on both sides, so the gross edge per
fill is `half_spread * quote_size` = $0.025 at `half_spread = 50.0`, or
5 bps of notional.

Kraken's base-tier maker fee is 0.25%, which is 25 bps, or $0.13 on the
same $50 notional. Every fill loses about $0.105 before adverse selection
is counted. Break-even `half_spread` is `maker_rate * price`:

| 30-day volume | Maker fee | Break-even `half_spread` |
|---|---|---|
| < $10k | 0.25% | $250 |
| $10k+ | 0.20% | $200 |
| $250k+ | 0.10% | $100 |
| $10M+ | 0.00% | $0 |

Widening the spread does not rescue this. Kraken's BTC-USD touch is a few
dollars wide, so a break-even quote would sit 50 to 100 times further from
mid than the actual market and would only ever be reached when price moves
$250 through the level. That is not market making, it is buying
dislocations, and it has worse selection.

The market's own quoted spread reveals what the winning makers pay. A pair
quoting fractions of a basis point wide is being made by participants at
the 0.00% tier. At base tier on BTC-USD the strategy is not at a
disadvantage, it is arithmetically excluded.

What would fix it, in order of effect: a better fee tier, which as of July
2026 can also be reached through Assets on Platform rather than traded
volume; or a pair whose natural spread is wide relative to the fee, where
the arithmetic can close; or an edge that comes from a signal rather than
from the spread, so the fee is a share of a larger number.

`FeeAwareQuoteOffsetService` does not fix this, since the arithmetic above
is a fact about the fee tier rather than about the code. What it does is
stop the strategy quoting below cost silently: it quotes at
`edge + maker_rate * price`, so the break-even column of the table above
is charged automatically and the resulting offset is recorded on the
`quote_offset` signal. The paper session now runs it at `edge = 5.0`, so
its quotes sit roughly five times further out than the static default's
and will almost certainly stop filling altogether. That is the arithmetic
above made visible rather than a regression, and it is why this issue
stays open.

Skewing the fair price cannot rescue it either. The inventory skew is
capped at the quoted edge of $5 while the offset itself is around $255,
so even a position at its cap moves the quote by about 2% of its
distance from mid. The fee term dominates the quote, so no fair price
signal can steer it much until the fee tier or the pair changes.

## 2. Simulated queue position is always zero

`_rest_order` sets `ahead_quantity` from the BBO only when the order price
exactly equals the current best bid or ask, and leaves it at `0.0`
otherwise. The strategy quotes at `mid ± 50`, always well behind a touch
that is a few dollars wide, so the condition never holds and
`ahead_quantity` is always zero. The simulator therefore believes the
strategy is first in queue at every level it ever quotes.

This is the largest single error in the fill model. Correcting it likely
drops the simulated fill count by an order of magnitude.

`OrderBook` now carries the resting size at any price, which is what the
starting estimate needs, but `_rest_order` still reads only the BBO. Even
once it reads depth, rank within a level stays out of reach: L2 aggregates
by price, so position inside the queue is known only at insertion and must
be modelled thereafter. When a level shrinks with no trade printed at that
price the cause was a cancellation, but whether it sat ahead or behind is
unknowable, and that choice materially swings fill rate. Kraken's `level3`
channel resolves this and is not implemented, because it requires an API
token.

## 3. Sweeps fill the whole remainder

In `_try_fill_resting_order`, a trade printing beyond the resting price is
treated as clearing the level and fills the entire remaining quantity. The
size is assumed rather than derived.

Now that depth is published, the fill can be capped at the quantity
actually consumed between the touch and the resting level. Note that this
branch is also the only one that fires in practice for quotes far behind
the touch, which means simulated fills arrive almost exclusively when the
market is moving through the quote. The adverse selection is real rather than a
simulation artifact, but its size is currently guessed.

## 4. No latency model

An order is decided on a BBO and rests instantly. Real quoting pays wire
time out, matching engine time, and market data time back in, so the
strategy joins each queue later than the simulation assumes and behind
orders the simulation places it in front of. For queue position accuracy
this is roughly as important as depth, and it is orthogonal to the depth
work.

## 5. The simulated book never reacts to our orders

The replayed book is the real market's, which never contained our quotes.
Trades that would have hit us hit whoever really stood there, and
participants who would have reacted to our presence do not. This is
inherent to replaying a market we did not trade in and is not fixable with
better data. It is recorded so that simulated results are read with it in
mind.

## 6. A better fill model would be live-only

Replay carries no depth: `HistoricalFeed` publishes market trades only,
and `BookFeatureRecorder` stores top of book, imbalance, and
depth-weighted price, which is deliberately too little to reconstruct a
book. An improved fill model would therefore run only in live paper mode,
while replay kept the behaviour described in issues 2 and 3.

That is the wrong way round for evaluating the strategy, since replay is
where weeks of data can be swept and live paper yields one slow real-time
sample. If fill realism is the goal rather than better signals, a compact
book writer belongs on the critical path. Nothing wires the book into the
Kraken mock either, whose fill model imports no `OrderBook` at all and
whose resting-order logic is untouched by the depth work.

## Reading results while these stand

Hedging is not what is missing. Hedging reduces the variance of the
inventory term rather than creating expectancy, and an unhedged maker
with a tight cap and skewed quotes is an ordinary arrangement. What the
original question turned on is everything above, not hedging.

Two questions are worth keeping apart. Whether the fair price model is any
good is measured by gross markout and edge, with fees excluded, and a
model with positive gross markout is a real result even when net is
negative. Whether the fee tier is viable is arithmetic and involves no
code. `jolteon/app/analytics.py` already computes gross and net markout
side by side, so both readings are available from the same fills.
