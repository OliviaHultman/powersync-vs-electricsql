import { appendFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

// Records the moment a row became visible in a client's local SQLite database.
export function logReceived(resultsFile: string, id: string, receivedAt: number): void {
  mkdirSync(dirname(resultsFile), { recursive: true });
  appendFileSync(resultsFile, JSON.stringify({ id, receivedAt }) + '\n');
}
