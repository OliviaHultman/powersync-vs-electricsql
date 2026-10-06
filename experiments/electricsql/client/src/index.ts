import Database from 'better-sqlite3';
import { ShapeStream } from '@electric-sql/client';
import type { ChangeMessage, Message } from '@electric-sql/client';
import { logReceived } from '../../../../shared/client/resultLogger.js';

const ELECTRIC_URL = process.env.ELECTRIC_URL ?? 'http://localhost:3001/v1/shape';
const RESULTS_FILE = process.env.RESULTS_FILE ?? '../../../results/electricsql-received.ndjson';

type EventRow = { id: string; payload: string; inserted_at: string };

const db = new Database('electric-client.db');
db.exec(`
  CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    payload TEXT,
    inserted_at TEXT
  )
`);

const upsert = db.prepare(
  'INSERT INTO events (id, payload, inserted_at) VALUES (@id, @payload, @inserted_at) ' +
    'ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, inserted_at = excluded.inserted_at'
);
const remove = db.prepare('DELETE FROM events WHERE id = ?');

const stream = new ShapeStream<EventRow>({
  url: ELECTRIC_URL,
  params: { table: 'events' },
});

console.log('ElectricSQL client ready, watching for new events...');

function isChangeMessage(message: Message<EventRow>): message is ChangeMessage<EventRow> {
  return 'key' in message;
}

stream.subscribe((messages) => {
  for (const message of messages) {
    if (!isChangeMessage(message)) continue; // control message (e.g. up-to-date)

    const { value, headers } = message;
    if (headers.operation === 'insert') {
      upsert.run(value);
      logReceived(RESULTS_FILE, value.id, Date.now());
    } else if (headers.operation === 'update') {
      upsert.run(value);
    } else if (headers.operation === 'delete') {
      remove.run(value.id);
    }
  }
});
