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
grep -v '^POWERSYNC_JWT_SECRET=' .env.example > .env
node generate-secrets.mjs >> .env
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

Run three sweeps per engine with the same network-latency levels (`0`, `25`,
`50`, and `100` ms), with the default warmup of 30 inserts per level (`--warmup N` changes it) and reversing the order in one sweep
so time effects are not confounded with the delay level:

```sh
npm run start --workspace @sync-experiment/orchestrator -- --engine powersync --networkLatenciesMs 0,25,50,100
npm run start --workspace @sync-experiment/orchestrator -- --engine powersync --networkLatenciesMs 100,50,25,0
npm run start --workspace @sync-experiment/orchestrator -- --engine powersync --networkLatenciesMs 0,25,50,100
npm run start --workspace @sync-experiment/orchestrator -- --engine electricsql --networkLatenciesMs 0,25,50,100
npm run start --workspace @sync-experiment/orchestrator -- --engine electricsql --networkLatenciesMs 100,50,25,0
npm run start --workspace @sync-experiment/orchestrator -- --engine electricsql --networkLatenciesMs 0,25,50,100
```

`networkLatenciesMs` is the additional delay in milliseconds on the
server-to-client path; it is not round-trip latency. The default is `0`.
Use the same levels, iteration count, warmup count, and polling interval for
both engines. Each resulting CSV records `network_latency_ms` for every
measurement. The orchestrator removes the injected delay when a sweep ends.

Analyze the latest CSV from each engine:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r analysis/requirements.txt
python analysis/analyze_latency.py --runs 3
```

`--runs N` combines the N newest sweeps per engine into one dataset (default 1).

The virtual environment only needs to be created and populated once. Next time,
run `source .venv/bin/activate` before `python analysis/analyze_latency.py`.

The analysis writes a summary by engine and network-delay level, baseline
engine-comparison figures, and `latency-by-network-latency.png` plus a linear
trend estimate for each engine to `results/analysis`.
