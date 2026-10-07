import { Client } from 'pg';
import { readFileSync, existsSync, mkdirSync, appendFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';

type Engine = 'powersync' | 'electricsql';

interface Args {
  engine: Engine;
  iterations: number;
  pgConnectionString: string;
  resultsFile: string;
  outputFile: string;
  delayMs: number;
  pollMs: number;
  warmup: number;
  networkLatenciesMs: number[];
}

function parseArgs(): Args {
  const args = process.argv.slice(2);
  const get = (name: string, fallback?: string): string | undefined => {
    const idx = args.indexOf(`--${name}`);
    return idx >= 0 ? args[idx + 1] : fallback;
  };

  const engine = get('engine') as Engine | undefined;
  if (engine !== 'powersync' && engine !== 'electricsql') {
    throw new Error(
      'Usage: tsx run-experiment.ts --engine powersync|electricsql [--networkLatenciesMs 0,25,50,100] [--iterations N] [--warmup N] [--delayMs N] [--pollMs N] [--pg CONNECTION_STRING] [--resultsFile PATH] [--outputFile PATH]'
    );
  }

  const defaultPg =
    engine === 'powersync'
      ? 'postgresql://postgres:postgres@localhost:5433/testdb'
      : 'postgresql://postgres:postgres@localhost:5434/testdb';

  return {
    engine,
    iterations: Number(get('iterations', '100')),
    pgConnectionString: get('pg', defaultPg)!,
    resultsFile: get('resultsFile', `../results/${engine}-received.ndjson`)!,
    outputFile: get('outputFile', `../results/${engine}-latency-${Date.now()}.csv`)!,
    delayMs: Number(get('delayMs', '500')),
    pollMs: Number(get('pollMs', '5')),
    warmup: Number(get('warmup', '30')),
    networkLatenciesMs: parseNetworkLatencies(get('networkLatenciesMs', '0')!),
  };
}

function parseNetworkLatencies(value: string): number[] {
  const parts = value.split(',').map((part) => part.trim());
  const latencies = parts.map(Number);
  if (
    parts.some((part) => !part) ||
    latencies.some((latency) => !Number.isInteger(latency) || latency < 0) ||
    new Set(latencies).size !== latencies.length
  ) {
    throw new Error(
      '--networkLatenciesMs must be a comma-separated list of unique non-negative integers'
    );
  }
  return latencies;
}

interface ProxyConfig {
  apiUrl: string;
  name: string;
  listen: string;
  upstream: string;
}

function proxyConfig(engine: Engine): ProxyConfig {
  if (engine === 'powersync') {
    return {
      apiUrl: process.env.TOXIPROXY_API_URL ?? 'http://localhost:8474',
      name: 'powersync',
      listen: '0.0.0.0:8081',
      upstream: 'powersync:8080',
    };
  }
  return {
    apiUrl: process.env.TOXIPROXY_API_URL ?? 'http://localhost:8475',
    name: 'electricsql',
    listen: '0.0.0.0:3001',
    upstream: 'electric:3000',
  };
}

// Toxiproxy reports wildcard listeners as "[::]:port" even when configured as "0.0.0.0:port".
function normalizeListen(listen: string): string {
  return listen.replace(/^(\[::\]|0\.0\.0\.0):/, '*:');
}

async function ensureProxy(config: ProxyConfig): Promise<void> {
  const proxiesUrl = `${config.apiUrl}/proxies`;
  let response: Response | undefined;
  let lastError: unknown;
  for (let attempt = 0; attempt < 30; attempt++) {
    try {
      response = await fetch(proxiesUrl);
      break;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  if (!response) {
    throw new Error(`Toxiproxy API unavailable at ${proxiesUrl}`, { cause: lastError });
  }
  if (!response.ok) {
    throw new Error(`Toxiproxy API returned ${response.status}: ${await response.text()}`);
  }

  const proxies = (await response.json()) as Record<
    string,
    { listen: string; upstream: string }
  >;
  const existing = proxies[config.name];
  if (existing) {
    if (
      normalizeListen(existing.listen) !== normalizeListen(config.listen) ||
      existing.upstream !== config.upstream
    ) {
      throw new Error(
        `Toxiproxy proxy ${config.name} has unexpected configuration (${existing.listen} -> ${existing.upstream})`
      );
    }
    return;
  }

  response = await fetch(proxiesUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      name: config.name,
      listen: config.listen,
      upstream: config.upstream,
      enabled: true,
    }),
  });
  if (!response.ok) {
    throw new Error(`Could not create Toxiproxy proxy: ${response.status} ${await response.text()}`);
  }
}

async function setNetworkLatency(config: ProxyConfig, latencyMs: number): Promise<void> {
  const toxicsUrl = `${config.apiUrl}/proxies/${config.name}/toxics`;
  const deleteResponse = await fetch(`${toxicsUrl}/downstream-latency`, { method: 'DELETE' });
  if (!deleteResponse.ok && deleteResponse.status !== 404) {
    throw new Error(
      `Could not remove existing network latency: ${deleteResponse.status} ${await deleteResponse.text()}`
    );
  }
  if (latencyMs === 0) return;

  const response = await fetch(toxicsUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      name: 'downstream-latency',
      type: 'latency',
      stream: 'downstream',
      toxicity: 1,
      attributes: { latency: latencyMs, jitter: 0 },
    }),
  });
  if (!response.ok) {
    throw new Error(
      `Could not set downstream network latency to ${latencyMs}ms: ${response.status} ${await response.text()}`
    );
  }
}

type Received = { receivedAt: number; notifiedAt?: number };

function findReceived(resultsFile: string, id: string): Received | undefined {
  if (!existsSync(resultsFile)) return undefined;
  const lines = readFileSync(resultsFile, 'utf-8').split('\n').filter(Boolean);
  // Search from the end - recent inserts are appended last.
  for (let i = lines.length - 1; i >= 0; i--) {
    const entry = JSON.parse(lines[i]);
    if (entry.id === id) return { receivedAt: entry.receivedAt, notifiedAt: entry.notifiedAt ?? undefined };
  }
  return undefined;
}

async function waitForRow(
  resultsFile: string,
  id: string,
  pollMs: number,
  timeoutMs = 30_000
): Promise<Received> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const received = findReceived(resultsFile, id);
    if (received !== undefined) return received;
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
  throw new Error(`Timed out waiting for row ${id} to sync to the client`);
}

async function main(): Promise<void> {
  const args = parseArgs();
  const proxy = proxyConfig(args.engine);
  await ensureProxy(proxy);
  const pg = new Client({ connectionString: args.pgConnectionString });
  await pg.connect();

  mkdirSync(dirname(args.outputFile), { recursive: true });
  writeFileSync(
    args.outputFile,
    'network_latency_ms,iteration,id,inserted_at_ms,received_at_ms,latency_ms,notified_at_ms\n'
  );

  console.log(
    `Running ${args.iterations} iterations against engine=${args.engine} for network latencies [${args.networkLatenciesMs.join(', ')}]ms (warmup=${args.warmup}, pollMs=${args.pollMs})`
  );

  try {
    for (const networkLatencyMs of args.networkLatenciesMs) {
      await setNetworkLatency(proxy, networkLatencyMs);
      console.log(`\nNetwork downstream latency: ${networkLatencyMs}ms`);

      for (let i = 0; i < args.warmup; i++) {
        const id = randomUUID();
        await pg.query(
          "INSERT INTO events (id, payload, inserted_at) VALUES ($1, $2, $3)",
          [id, `warmup-payload-${networkLatencyMs}-${i}`, new Date()]
        );
        await waitForRow(args.resultsFile, id, args.pollMs);
      }

      for (let i = 0; i < args.iterations; i++) {
        const id = randomUUID();
        const insertedAtMs = Date.now();
        await pg.query(
          "INSERT INTO events (id, payload, inserted_at) VALUES ($1, $2, $3)",
          [id, `test-payload-${networkLatencyMs}-${i}`, new Date(insertedAtMs)]
        );

        const { receivedAt: receivedAtMs, notifiedAt } = await waitForRow(args.resultsFile, id, args.pollMs);
        const latencyMs = receivedAtMs - insertedAtMs;

        appendFileSync(
          args.outputFile,
          `${networkLatencyMs},${i},${id},${insertedAtMs},${receivedAtMs},${latencyMs},${notifiedAt ?? ''}\n`
        );
        console.log(`[${i + 1}/${args.iterations}] latency=${latencyMs.toFixed(1)}ms`);

        await new Promise((resolve) => setTimeout(resolve, args.delayMs));
      }
    }
  } finally {
    try {
      await setNetworkLatency(proxy, 0);
    } finally {
      await pg.end();
    }
  }

  console.log(`Done. Results written to ${args.outputFile}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
