# Parameters

Every tunable the engine reads is declared in one form, read through one
service, and editable from the dashboard while the engine is running.
Before this, the numbers lived as default arguments and class constants
across roughly twenty-five files, with `cli.py` acting as the de-facto
config file; changing any of them meant editing source and restarting.

## Declaring a tunable

A component owns a `ParameterGroup` — a frozen dataclass whose fields are
declared with `parameter()`, which records the default alongside the
bounds, step, display format, unit and description:

```python
@dataclass(frozen=True)
class MarketMakingParameters(ParameterGroup):
    quote_size: float = parameter(
        0.0005,
        minimum=0.00001,
        maximum=10.0,
        step=0.0001,
        number_format="%.5f",
        unit="BTC",
        description="How much base currency each resting quote offers.",
    )
```

That declaration is the only place the value is described. The dashboard
builds its editor from it — widget type from the field's type, bounds and
step from the declaration, the tooltip from the description — so adding a
tunable is one line in the component's `parameters.py` and needs no
change to the dashboard at all. A brand new group needs one further line,
its class added to `GROUPS` in `parameter_catalog.py`.

Two constraints are worth knowing before adding one:

* **Every field must have a default.** `parameter()` has to be annotated
  `-> Any`, because mypy only treats a literal `dataclasses.field()` call
  as supplying a default and cannot follow a wrapper around one. That
  also means mypy cannot catch a field declared without a default, so
  `test_parameter_catalog` asserts it instead.
* **Groups live in a leaf `parameters.py`** importing nothing but
  `parameter_specification`. The dashboard imports the catalog to draw
  its editor, in a process with no market data feed or exchange client to
  load, so a group declared inside `public_feed.py` would drag
  `websockets` in with it.

### What a group deliberately does not say

A group says nothing about when a change to it takes effect. Where a
component reads a value is a property of that component's code and
changes with it, so a declared claim would go stale silently and nobody
would know to update it. The question is answered from what actually
happened at runtime instead — see *Observation* below — which stays true
on its own and also catches a case no declaration could: a parameter
nothing reads at all.

## Reading a tunable

`IParameterService.get(Group, symbol)` is what almost every caller uses.
`values()` returns every group at one revision, and exists only for a
caller that needs two groups to agree with each other:
`InventoryAdjustment` divides one group's field by another's, and two
separate `get()` calls could fall either side of a background refresh and
pair a new skew with an old cap.

Components the application wires by hand are handed a service. The layers
underneath them — logging, retries, the SQLite writer, heartbeats — are
reached from everywhere and have nowhere to receive one, so they read the
module-level `parameter_service()` accessor, the same shape
`time_manager()` and `id_generator()` already use here.

Every component keeps its own constructor argument as an explicit
override, which wins over anything stored. A caller that wants one fixed
number says so, and a test reads as it always did.

## Pushing a change

```
dashboard process                        engine process
─────────────────                        ──────────────
Parameters page                          StoredParameterService
  stage edits in session state             poller thread, every ~1s
  [Push] ─write─> jolteon.params.sqlite ─read (mode=ro)─> rebuild on change
                  (dashboard = sole writer)                     │
                                                   parameter_applied
                                                                │
  page reads what the engine ran <─read─ jolteon.sqlite <────────┘
                                         (engine = sole writer)
```

Each file has exactly one writer, which is the same reasoning that gives
the engine's logs a database of their own: neither process can take the
lock the other one needs. The engine opens the parameter store read-only
(`mode=ro`) so it cannot write to it even by accident.

That read-only connection stays open for as long as the engine polls,
since `data_version` only moves on a connection that does, and
`StoredParameterService.stop()` closes it once the polling thread has
joined. Holding it past that point costs nothing on POSIX, where a file
can be unlinked while a handle is open, but on Windows it makes the file
impossible to remove.

The poller wakes on `ParameterPollParameters.interval_in_seconds` and
issues one `PRAGMA data_version`, which costs about 17µs and moves only
when another connection has committed. **`data_version` is only an
optimisation**: what the rows say decides a rebuild. It reports nothing
at all until the dashboard has created the file, which is the normal
state of an engine nobody is tuning, and treating that as a change
advanced the revision on every tick.

The engine's own threads never touch the store. The quoting path reads an
already-built immutable object: two dictionary lookups, no allocation, no
I/O. The poller builds a wholly new set of values and rebinds one
attribute, so readers need no lock — build then rebind, and never mutate
what has been published.

### Refusing a push

Validation happens on the poller thread, not at a read site: a bad value
must never raise where the strategy quotes. A push that breaks a field's
declared bounds, or a constraint that spans two fields, leaves the engine
on the values it was already running, raises a WARN heartbeat, and comes
back as a rejected status with a reason.

`parameter_catalog.validate()` also carries the constraints no single
field can state, because they are about how two sit together — the
heartbeat monitor's staleness timeout has to exceed the heartbeat
interval, or any jitter marks a healthy component a zombie.

### Observation

`ParameterValues` carries a `revision` and an `observed` map. Reading a
group through `get()` records `observed[group] = revision`; `peek()` is
the same read without recording, for validating and reporting, which must
not make a revision look picked up. Each new set of values inherits the
previous map, so it holds the last revision at which each group was
genuinely read.

That is the whole mechanism behind what the page shows. A group read
every tick converges in milliseconds and reads *applied*; one read only
at construction stays behind and reads *not read yet* until the engine
restarts; a stored value no engine has echoed at all reads *not picked
up*; and a refused one reads *rejected* with the engine's reason.

## What is not a parameter

* `database_name`, `logfile_name` and `symbol` stay CLI arguments.
  Repointing the engine's output database from the dashboard while the
  dashboard is reading it is a footgun, not a tunable.
* `PostTradeService._HORIZONS` derives the column names
  `fair_price_100ms/1s/5s/30s`, which are written out again in
  `decorated_order_fill.py`, `app/analytics.py` and
  `app/signal_evaluation.py`. Changing it live desyncs two processes'
  schemas.
* `PublicFeed.CHECKSUM_DEPTH` is fixed by Kraken at ten levels whatever
  depth is subscribed to.

A replay does not poll either. It installs fake time and has to produce
the same result twice, which it cannot if a dashboard can retune it
halfway through, so only a live session is given a store.
