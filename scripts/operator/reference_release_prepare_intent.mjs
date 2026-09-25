import fs from 'node:fs';
import { webcrypto, randomBytes } from 'node:crypto';

const crypto = webcrypto;

function b64ToBytes(text) {
  return Uint8Array.from(Buffer.from(text.trim(), 'base64'));
}

function bytesToB64(bytes) {
  return Buffer.from(bytes).toString('base64');
}

function canonical(node) {
  const ordered = {};
  for (const key of Object.keys(node).sort()) ordered[key] = node[key];
  return JSON.stringify(ordered);
}

async function sha256Hex(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return Buffer.from(digest).toString('hex');
}

const [privatePath, brokerKeyId, outputPath, intentSecondsArg] = process.argv.slice(2);
if (!privatePath || !brokerKeyId || !outputPath) throw new Error('arguments_required');
if (!/^sha256:[0-9a-f]{64}$/.test(brokerKeyId)) throw new Error('broker_key_id_rejected');

const intentSeconds = Number(intentSecondsArg || 28800);
if (!Number.isInteger(intentSeconds) || intentSeconds < 300 || intentSeconds > 259200) {
  throw new Error('intent_window_rejected');
}

const callerPolicy = {
  repository_id: '1358005162',
  repository_owner_id: '152584286',
  repository_visibility: 'public',
  ref: 'refs/heads/main',
  event_name: 'push',
};
const callerPolicySha256 = await sha256Hex(
  new TextEncoder().encode(canonical(callerPolicy))
);

const now = Math.floor(Date.now() / 1000);
const node = {
  schema: 'reference-release-intent-v1',
  issuer: 'private-authority-v1',
  audience: 'independent-release-broker-v1',
  grant_id: 'g_' + randomBytes(24).toString('hex'),
  caller_policy_sha256: callerPolicySha256,
  harness_sha: '477b76085c06f77fee72b57771225a66545aa43f',
  broker_key_id: brokerKeyId,
  not_before: now - 30,
  intent_not_after: now + intentSeconds,
};

const pkcs8 = b64ToBytes(fs.readFileSync(privatePath, 'utf8'));
const privateKey = await crypto.subtle.importKey(
  'pkcs8',
  pkcs8,
  { name: 'ECDSA', namedCurve: 'P-256' },
  false,
  ['sign'],
);
const payload = new TextEncoder().encode(canonical(node));
const signature = new Uint8Array(await crypto.subtle.sign(
  { name: 'ECDSA', hash: 'SHA-256' },
  privateKey,
  payload,
));
if (signature.length !== 64) throw new Error('signature_format_unexpected');

const publicDerivePair = await crypto.subtle.importKey(
  'pkcs8',
  pkcs8,
  { name: 'ECDSA', namedCurve: 'P-256' },
  true,
  ['sign'],
);
// WebCrypto cannot derive public from an imported private key. The caller only
// needs the signer key id already persisted by keygen; inject it separately.
const signerKeyIdPath = privatePath.replace('authority-private.pkcs8.b64', 'authority-key-id.txt');
const signerKeyId = fs.readFileSync(signerKeyIdPath, 'utf8').trim();

const wrapper = {
  payload_b64: bytesToB64(payload),
  signature_b64: bytesToB64(signature),
  signer_key_id: signerKeyId,
  signature_format: 'ecdsa-p256-sha256-p1363',
};
const bootstrap = {
  schema: 'reference-live-intent-v1',
  intent: wrapper,
};
fs.writeFileSync(outputPath, JSON.stringify(bootstrap, null, 2) + '\n', { mode: 0o600 });
console.log('REFERENCE_INTENT_PREPARE_PASS=1');
console.log('GRANT_ID=' + node.grant_id);
console.log('INTENT_NOT_AFTER=' + node.intent_not_after);
