# Known Issues

Issues found while working through a single question: with no hedging in
the market making strategy, can it still make money? The answer turned
out to depend very little on hedging and a great deal on fees, fill
simulation, and inventory control, so the findings are recorded here
rather than in any one component's notes.

Each entry states what is wrong, why it matters, and what would resolve
it; the few marked fixed record what changed. Arithmetic assumes BTC
around $100,000 and the declared defaults of `MarketMakingParameters`:
`quote_size = 0.0005` and `max_inventory = 0.01`. Where a quote offset
matters, the figure given is the one a paper session actually quotes:
`QuoteOffsetParameters.edge = 5.0`, which at that price asks $255 a side.

Every figure below is now a declared parameter that the dashboard can
change on a running engine, so these are the defaults an untuned session
starts from rather than the only values it can hold. See
[the parameters design note](parameters.md).

Issues 1 to 8 come from that original question. Issues 9 to 12 come from
the later sweep that made those figures tunable. Two of those were
already in the engine; the other two were introduced while building it
and caught before it landed, recorded because they are the traps anyone
touching the parameter service would meet again.

## Summary

| # | Issue | Severity |
|---|---|---|
| 1 | Fees exceed quoted edge by ~5x | Strategy cannot profit |
| 2 | ~~Fee constant is stale and conflates maker with taker~~ | Fixed |
| 3 | Simulated queue position is always zero | Fill rate wildly overstated |
| 4 | Sweeps fill the whole remainder | Overstates size on adverse fills |
| 5 | No latency model | Queue position optimistic |
| 6 | Simulated book never reacts to our orders | Inherent to replay |
| 7 | ~~No inventory skew wired in; cap is not a control~~ | Fixed |
| 8 | A better fill model would be live-only | Cannot be backtested |
| 9 | ~~Inventory skew decoupled from the cap it defends~~ | Fixed |
| 10 | ~~Validating a revision counted as a component reading it~~ | Fixed |
| 11 | ~~A missing parameter store advanced the revision forever~~ | Fixed |
| 12 | ~~Heartbeat timeout equalled the heartbeat interval~~ | Fixed |

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
above made visible rather than a regression, and it is why issue 1 stays
open.

## 2. The fee constant is stale and conflates maker with taker (fixed)

`kraken/mock_execution_service.py` hardcoded
`fee = filled_price * filled_quantity * 0.0026` in `_generate_order_fill`,
citing a Kraken schedule that no longer applies. Kraken charges 0.25%
maker and 0.40% taker at base tier.

Both rates now live on a `FeeSchedule`, and `_generate_order_fill` takes a
`maker` flag that its two callers set: a resting order that a print
crosses is charged the maker rate, a market order that fills immediately
the taker rate. `FeeAwareQuoteOffsetService` reads the same schedule, so
the fee a quote is priced against and the fee a simulated fill is charged
cannot drift apart.

`FeeSchedule` is itself the parameter group for the rates, rather than
having a second group describing it: its two fields are exactly the
tunables, and its declared defaults are Kraken's base tier. That keeps
the mock execution service's route to them a plain `FeeSchedule` it is
handed, while the dashboard can still retune them. Running a replay at a
chosen tier is a matter of passing a different schedule; picking the tier
up from the account automatically is not done.

## 3. Simulated queue position is always zero

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

## 4. Sweeps fill the whole remainder

In `_try_fill_resting_order`, a trade printing beyond the resting price is
treated as clearing the level and fills the entire remaining quantity. The
size is assumed rather than derived.

Now that depth is published, the fill can be capped at the quantity
actually consumed between the touch and the resting level. Note that this
branch is also the only one that fires in practice for quotes far behind
the touch, which means simulated fills arrive almost exclusively when the
market is moving through the quote. The adverse selection is real rather than a
simulation artifact, but its size is currently guessed.

## 5. No latency model

An order is decided on a BBO and rests instantly. Real quoting pays wire
time out, matching engine time, and market data time back in, so the
strategy joins each queue later than the simulation assumes and behind
orders the simulation places it in front of. For queue position accuracy
this is roughly as important as depth, and it is orthogonal to the depth
work.

## 6. The simulated book never reacts to our orders

The replayed book is the real market's, which never contained our quotes.
Trades that would have hit us hit whoever really stood there, and
participants who would have reacted to our presence do not. This is
inherent to replaying a market we did not trade in and is not fixable with
better data. It is recorded so that simulated results are read with it in
mind.

## 7. No inventory skew was wired in, and the cap was not a control (fixed)

`InventoryAdjustment` existed and shifted fair price against the current
position, but `cli.py` registered only `MomentumAdjustment` and
`OrderFlowImbalanceAdjustment`, both of which lean into recent flow and so
accumulate inventory in the direction of the trend. Nothing pushed it back
toward flat, and the only remaining control was a hard cap of 1 BTC, which
against a 0.0005 quote size is 2,000 fills away: a backstop rather than a
control. For scale, one round trip earns $0.05 gross, while a full 1 BTC
position through a $500 move is $500, or 10,000 round trips of spread
capture.

The paper session now registers `InventoryAdjustment` alongside the two
flow adjustments, and `DEFAULT_MAX_INVENTORY` is 20 times quote size
rather than a flat 1 BTC, so the cap binds in tens of fills rather than
thousands. The skew is scaled `max_adjustment / max_inventory`, so a
position at the cap asks for the entire adjustment the model is allowed to
apply and can always outvote the flow adjustments at the point where
inventory matters most. That scaling was computed once at construction,
which turned out to be its own bug; see issue 9.

Hedging was never what was missing here. Hedging reduces the variance of
the inventory term rather than creating expectancy, and an unhedged maker
with a tight cap and skewed quotes is an ordinary arrangement.

What this does not fix is how little room the skew has to work in. The
adjustment is capped at the quoted edge of $5 while the offset itself is
around $255, so even a position at the cap moves the quote by about 2% of
its distance from mid. That ratio is issue 1 showing up again rather than
a flaw in the skew: the fee term dominates the quote, so no fair price
signal can steer much until the fee tier or the pair changes.

## 8. A better fill model would be live-only

Replay carries no depth: `HistoricalFeed` publishes market trades only,
and `BookFeatureRecorder` stores top of book, imbalance, and
depth-weighted price, which is deliberately too little to reconstruct a
book. An improved fill model would therefore run only in live paper mode,
while replay kept the behaviour described in issues 3 and 4.

That is the wrong way round for evaluating the strategy, since replay is
where weeks of data can be swept and live paper yields one slow real-time
sample. If fill realism is the goal rather than better signals, a compact
book writer belongs on the critical path. Nothing wires the book into the
Kraken mock either, whose fill model imports no `OrderBook` at all and
whose resting-order logic is untouched by the depth work.

## 9. Inventory skew decoupled from the cap it defends (fixed)

`cli.py` computed the skew's strength once, as
`InventoryAdjustment(scale=skew_at_max_inventory / max_inventory)`, and
handed the result to the constructor. The division was therefore frozen
at the cap that happened to be configured at startup.

Changing the cap after that moved the hard limit but left the skew sized
for the old one, and it breaks in both directions. With the defaults —
skew $5 at a cap of 0.01, so a scale of 500 — raising the cap to 0.02
leaves a full position asking for $10, which the model clamps to $5: the
skew now maxes out at 0.01, half way up the range, and stops responding
to inventory over the whole upper half. Lowering the cap to 0.005 leaves
a full position asking for $2.50, half the intended skew, so the defence
is weakest exactly where it should be strongest.

Either way it fails silently, because nothing in the wiring relates the
two numbers any more. That is the opposite of what issue 7 set the skew
up to do, which is to reach full strength precisely at the cap.

`InventoryAdjustmentParameters` now declares `skew_at_max_inventory` —
how far the fair price moves at a full position, rather than how far it
moves per unit — and `InventoryAdjustment.adjustment` divides by the
current cap on each call. The two can no longer drift, and the CLI is out
of the arithmetic business entirely. Both groups are read from a single
`values()` snapshot, since two separate reads could fall either side of a
background refresh and pair a new skew with an old cap.

## 10. Validating a revision counted as a component reading it (fixed)

The dashboard reports whether a pushed parameter has actually reached the
component that uses it, and it does so from what happened at runtime
rather than from anything declared: reading a group records the revision
it was read at, and the page compares that against the current revision.

`parameter_catalog.validate()` walked every group through the same read
used by components, so checking a new revision marked all of it observed.
Every push reported itself applied the instant it was accepted, whether
or not anything had looked at it — which is precisely the case the
mechanism exists to distinguish, and it would have reported the
comfortable answer every time.

Reading is now two operations: `get()`, which records that a component
has read this revision, and `peek()`, which does not. Validating and
reporting use `peek()`. The rule is that only a component consuming a
value may mark it observed; infrastructure inspecting one may not.

## 11. A missing parameter store advanced the revision forever (fixed)

The poller was gated on `PRAGMA data_version`, which increments when
another connection commits. Two things about it were wrong in the first
implementation.

It only moves on a connection that stays open. Connecting per poll
returns the same number regardless of what has been committed since, so
the gate never fired and every tick reloaded. The poller now holds one
read-only connection open, reopening it if the file is replaced.

The larger problem was the opposite. `data_version` reports nothing at
all while the file does not exist, which is the normal state of an engine
nobody has ever pushed to. Treating "no reading" as "something changed"
rebuilt the values and advanced the revision on every single tick — so an
engine running without a dashboard climbed through revisions forever, and
every parameter read as one revision further behind than the last.

What the rows say now decides a rebuild, and `data_version` is only an
optimisation that skips reading them. A missing or damaged store means
run on the declared defaults and retry, never a fault worth stopping an
engine for.

## 12. Heartbeat timeout equalled the heartbeat interval (fixed)

Six components each sent a heartbeat every ten seconds, and
`HeartbeatMonitor` treated a component as a zombie after ten seconds of
silence. A heartbeat arriving even slightly late therefore marked a
healthy component dead, and on a loaded machine the monitor would have
reported failures that were entirely its own threshold.

This was latent rather than live: nothing wires `HeartbeatMonitor` into
the application, and the dashboard's Health page applies its own
thirty-second threshold, which is why it was never seen. The two
disagreed with each other besides.

Catching it was itself a consequence of the parameter work: some
constraints are about how two fields sit together and cannot be stated on
either one, so the catalog gained a validation hook for them, and the
first constraint written into it rejected the shipped defaults. The
declared timeout is now the thirty seconds the dashboard had been using
all along, and a test asserts the declared defaults satisfy their own
validation — a default that breaks a constraint would otherwise reject
every later push too.

## Reading results while these stand

Two questions are worth keeping apart. Whether the fair price model is any
good is measured by gross markout and edge, with fees excluded, and a
model with positive gross markout is a real result even when net is
negative. Whether the fee tier is viable is arithmetic and involves no
code. `jolteon/app/analytics.py` already computes gross and net markout
side by side, so both readings are available from the same fills.
