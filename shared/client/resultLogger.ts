import { appendFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

// Records the moment a row was read from a client's local SQLite database.
// notifiedAt is when the client was told about the change, before the local read.
export function logReceived(
  resultsFile: string,
  id: string,
  receivedAt: number,
  notifiedAt?: number
): void {
  mkdirSync(dirname(resultsFile), { recursive: true });
  appendFileSync(resultsFile, JSON.stringify({ id, receivedAt, notifiedAt }) + '\n');
}
