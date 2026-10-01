import { Client } from 'pg';
import { readFileSync, existsSync, mkdirSync, appendFileSync } from 'node:fs';
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
      'Usage: tsx run-experiment.ts --engine powersync|electricsql [--iterations N] [--delayMs N] [--pg CONNECTION_STRING] [--resultsFile PATH] [--outputFile PATH]'
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
  };
}

function findReceivedAt(resultsFile: string, id: string): number | undefined {
  if (!existsSync(resultsFile)) return undefined;
  const lines = readFileSync(resultsFile, 'utf-8').split('\n').filter(Boolean);
  // Search from the end - recent inserts are appended last.
  for (let i = lines.length - 1; i >= 0; i--) {
    const entry = JSON.parse(lines[i]);
    if (entry.id === id) return entry.receivedAt;
  }
  return undefined;
}

async function waitForRow(resultsFile: string, id: string, timeoutMs = 30_000): Promise<number> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const receivedAt = findReceivedAt(resultsFile, id);
    if (receivedAt !== undefined) return receivedAt;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out waiting for row ${id} to sync to the client`);
}

async function main(): Promise<void> {
  const args = parseArgs();
  const pg = new Client({ connectionString: args.pgConnectionString });
  await pg.connect();

  mkdirSync(dirname(args.outputFile), { recursive: true });
  appendFileSync(args.outputFile, 'iteration,id,inserted_at_ms,received_at_ms,latency_ms\n');

  console.log(`Running ${args.iterations} iterations against engine=${args.engine}`);

  for (let i = 0; i < args.iterations; i++) {
    const id = randomUUID();
    const { rows } = await pg.query<{ inserted_at_ms: string }>(
      "INSERT INTO events (id, payload, inserted_at) VALUES ($1, $2, now()) RETURNING extract(epoch from inserted_at) * 1000 AS inserted_at_ms",
      [id, `test-payload-${i}`]
    );
    const insertedAtMs = Number(rows[0].inserted_at_ms);

    const receivedAtMs = await waitForRow(args.resultsFile, id);
    const latencyMs = receivedAtMs - insertedAtMs;

    appendFileSync(args.outputFile, `${i},${id},${insertedAtMs},${receivedAtMs},${latencyMs}\n`);
    console.log(`[${i + 1}/${args.iterations}] latency=${latencyMs.toFixed(1)}ms`);

    await new Promise((resolve) => setTimeout(resolve, args.delayMs));
  }

  await pg.end();
  console.log(`Done. Results written to ${args.outputFile}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
