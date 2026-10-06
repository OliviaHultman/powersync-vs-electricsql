# Synchronization latency experiment

The experiment measures the time from a Postgres insert to the event becoming
visible in a second client's local database. Toxiproxy adds a deterministic,
one-way delay to server-to-client traffic so synchronization latency can be
compared at several network conditions.

## Run a latency sweep

Install Node dependencies, then create the local PowerSync configuration once:

```sh
npm ci
cd experiments/powersync
node generate-secrets.mjs > .env
printf 'POWERSYNC_PG_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> .env
printf 'POWERSYNC_STORAGE_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> .env
```

Start both engine stacks from the repository root:

```sh
docker compose --env-file experiments/powersync/.env -f experiments/powersync/docker-compose.yml up -d
docker compose -f experiments/electricsql/docker-compose.yml up -d
```

Start the clients in separate terminals. For PowerSync, generate a development
token in `experiments/powersync` with the same `POWERSYNC_JWT_SECRET` used by
the service, then pass it to the client:

```sh
cd experiments/powersync
set -a
. ./.env
set +a
POWERSYNC_TOKEN="$(node generate-dev-token.mjs)" npm run start --workspace @sync-experiment/powersync-client
```

Start the ElectricSQL client from the repository root:

```sh
npm run start --workspace @sync-experiment/electricsql-client
```

Run one sweep per engine. The default levels are listed explicitly here to
make the experiment configuration clear:

```sh
npm run start --workspace @sync-experiment/orchestrator -- --engine powersync --networkLatenciesMs 0,25,50,100
npm run start --workspace @sync-experiment/orchestrator -- --engine electricsql --networkLatenciesMs 0,25,50,100
```

`networkLatenciesMs` is the additional delay in milliseconds on the
server-to-client path; it is not round-trip latency. The default is `0`.
Use the same levels, iteration count, warmup count, and polling interval for
both engines. Each resulting CSV records `network_latency_ms` for every
measurement. The orchestrator removes the injected delay when a sweep ends.

Analyze the latest CSV from each engine:

```sh
python -m pip install -r analysis/requirements.txt
python analysis/analyze_latency.py
```

The analysis writes a summary by engine and network-delay level, baseline
engine-comparison figures, and `latency-by-network-latency.png` plus a linear
trend estimate for each engine to `results/analysis`.
