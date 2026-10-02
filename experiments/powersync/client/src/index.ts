import { PowerSyncDatabase } from '@powersync/node';
import { AppSchema } from './schema.js';
import { logReceived } from '../../../../shared/client/resultLogger.js';

const POWERSYNC_URL = process.env.POWERSYNC_URL ?? 'http://localhost:8080';
const POWERSYNC_TOKEN = process.env.POWERSYNC_TOKEN;
const RESULTS_FILE = process.env.RESULTS_FILE ?? '../../../results/powersync-received.ndjson';

if (!POWERSYNC_TOKEN) {
  throw new Error(
    'Set POWERSYNC_TOKEN (generate one with: node ../generate-dev-token.mjs, using the same POWERSYNC_JWT_SECRET as the service)'
  );
}

const db = new PowerSyncDatabase({
  schema: AppSchema,
  database: { dbFilename: 'powersync-client.db' },
});

class Connector {
  async fetchCredentials() {
    return { endpoint: POWERSYNC_URL, token: POWERSYNC_TOKEN! };
  }

  async uploadData() {
    // No local writes in this experiment - the orchestrator writes directly to Postgres.
  }
}

await db.connect(new Connector());
await db.waitForFirstSync();

// Track ids already accounted for so re-running the client doesn't re-log old rows.
const seen = new Set<string>();
for (const row of await db.getAll<{ id: string }>('SELECT id FROM events')) {
  seen.add(row.id);
}

console.log('PowerSync client ready, watching for new events...');

for await (const result of db.watch('SELECT id FROM events', [], { throttleMs: 0 })) {
  const rows = (result.rows?._array ?? []) as { id: string }[];
  for (const row of rows) {
    if (!seen.has(row.id)) {
      seen.add(row.id);
      logReceived(RESULTS_FILE, row.id, Date.now());
    }
  }
}
