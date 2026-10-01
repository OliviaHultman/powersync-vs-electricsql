// Generates a short-lived HS256 development token for the PowerSync client,
// signed with the same shared secret configured in service.yaml (POWERSYNC_JWT_SECRET).
// Usage: POWERSYNC_JWT_SECRET=... node generate-dev-token.mjs
import { createHmac } from 'node:crypto';

const secret = process.env.POWERSYNC_JWT_SECRET;
if (!secret) {
  throw new Error('Set POWERSYNC_JWT_SECRET in the environment (see .env)');
}

function base64url(input) {
  return Buffer.from(input).toString('base64url');
}

const header = { alg: 'HS256', typ: 'JWT', kid: 'dev-key-1' };
const now = Math.floor(Date.now() / 1000);
const payload = {
  sub: 'test-user',
  aud: 'http://localhost:8080',
  iat: now,
  exp: now + 12 * 60 * 60,
};

const headerB64 = base64url(JSON.stringify(header));
const payloadB64 = base64url(JSON.stringify(payload));
const signature = createHmac('sha256', Buffer.from(secret, 'base64url'))
  .update(`${headerB64}.${payloadB64}`)
  .digest('base64url');

console.log(`${headerB64}.${payloadB64}.${signature}`);
