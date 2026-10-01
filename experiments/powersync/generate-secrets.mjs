// Generates a random base64url HS256 secret for local dev use.
// Usage: node generate-secrets.mjs   (then paste the output into .env)
import { randomBytes } from 'node:crypto';

const secret = randomBytes(32).toString('base64url');
console.log(`POWERSYNC_JWT_SECRET=${secret}`);
