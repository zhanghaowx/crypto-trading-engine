# Local background stack

The default Docker Compose stack runs two background services:

- `engine-kraken-btc-usd` consumes Kraken market data and paper trades BTC/USD.
- `dashboard` reads the engine's recordings and serves Streamlit on port 8501.

Both services mount the `jolteon-data` named volume at `/data`. This keeps the
SQLite recordings, logs, and shared parameters when containers are recreated.

## Start and inspect

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs -f
```

Open <http://localhost:8501>. To follow one process, append its service name:

```bash
docker compose logs -f engine-kraken-btc-usd
docker compose logs -f dashboard
```

## Stop and update

Stop the processes while preserving their data:

```bash
docker compose down
```

After pulling code changes, rebuild and recreate the services:

```bash
docker compose up --build -d
```

To deliberately delete all local recordings and parameters:

```bash
docker compose down --volumes
```

## Live trading

Live trading requires an explicit profile. Put `KRAKEN_API_KEY` and
`KRAKEN_API_SECRET` in `.env`, then select the live engine and dashboard:

```bash
docker compose --profile live up --build -d engine-kraken-btc-usd-live dashboard
```

The live engine uses `restart: "no"`, so Docker does not resume trading after a
failure or host restart. Stop the default paper engine before using the live
engine if it is already running:

```bash
docker compose stop engine-kraken-btc-usd
```

## Optional Sentry reporting

Set `SENTRY_DSN` in `.env` to report uncaught process failures and handled order
submission or cancellation failures. Leave it blank to disable the SDK without
network traffic. `JOLTEON_ENVIRONMENT` distinguishes deployments, and
`JOLTEON_RELEASE` should contain the deployed commit SHA.

Events carry exchange, symbol, mode, component, release, and service identity.
The client disables traces and PII collection and removes request data, user
data, credentials, signed values, and stack-frame locals. It does not submit
ticks, trades, order or fill payloads, balances, API responses, or heartbeats.
The local SQLite recording and logs remain the authoritative operational record.
