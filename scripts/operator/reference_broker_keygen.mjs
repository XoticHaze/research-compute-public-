import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const outDir = process.argv[2];
if (!outDir) throw new Error('output directory required');
fs.mkdirSync(outDir, { recursive: true });

const HARNESS_SHA = '3bd5b90c445c6331a8e9c8a99487977b453df443';
const callerPolicy = {
  event_name: 'push',
  ref: 'refs/heads/main',
  repository_id: '1358005162',
  repository_owner_id: '152584286',
  repository_visibility: 'public',
};

function canonical(node) {
  const ordered = {};
  for (const key of Object.keys(node).sort()) ordered[key] = node[key];
  return JSON.stringify(ordered);
}
function b64(bytes) { return Buffer.from(bytes).toString('base64'); }
function sha256Hex(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }

const callerPolicySha256 = sha256Hex(Buffer.from(canonical(callerPolicy), 'utf8'));
const authority = await crypto.webcrypto.subtle.generateKey(
  { name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']
);
const broker = await crypto.webcrypto.subtle.generateKey(
  { name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']
);

const authorityPrivateJwk = await crypto.webcrypto.subtle.exportKey('jwk', authority.privateKey);
const authorityPublicRaw = new Uint8Array(await crypto.webcrypto.subtle.exportKey('raw', authority.publicKey));
const brokerPrivateJwk = await crypto.webcrypto.subtle.exportKey('jwk', broker.privateKey);
const brokerPublicRaw = new Uint8Array(await crypto.webcrypto.subtle.exportKey('raw', broker.publicKey));
const brokerKeyId = 'sha256:' + sha256Hex(brokerPublicRaw);
const authorityKeyId = 'sha256:' + sha256Hex(authorityPublicRaw);

const now = Math.floor(Date.now() / 1000);
const grantId = 'grant_' + crypto.randomBytes(18).toString('base64url');
const intent = {
  schema: 'reference-release-intent-v1',
  issuer: 'private-authority-v1',
  audience: 'independent-release-broker-v1',
  grant_id: grantId,
  caller_policy_sha256: callerPolicySha256,
  harness_sha: HARNESS_SHA,
  broker_key_id: brokerKeyId,
  not_before: now - 30,
  intent_not_after: now + 24 * 60 * 60,
};
const payload = Buffer.from(canonical(intent), 'utf8');
const signature = new Uint8Array(await crypto.webcrypto.subtle.sign(
  { name: 'ECDSA', hash: 'SHA-256' }, authority.privateKey, payload
));
if (signature.length !== 64) throw new Error('unexpected ECDSA signature format');

const signedIntent = {
  payload_b64: payload.toString('base64'),
  signature_b64: b64(signature),
  signer_key_id: authorityKeyId,
  signature_format: 'ecdsa-p256-sha256-p1363',
};

fs.writeFileSync(path.join(outDir, 'authority-private.jwk.json'), JSON.stringify(authorityPrivateJwk) + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'authority-public.b64'), b64(authorityPublicRaw) + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'broker-private.jwk.json'), JSON.stringify(brokerPrivateJwk) + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'broker-public.b64'), b64(brokerPublicRaw) + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'signed-intent.json'), JSON.stringify(signedIntent) + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'bootstrap-public.txt'), [
  'GRANT_ID=' + grantId,
  'BROKER_KEY_ID=' + brokerKeyId,
  'AUTHORITY_KEY_ID=' + authorityKeyId,
  'CALLER_POLICY_SHA256=' + callerPolicySha256,
  'HARNESS_SHA=' + HARNESS_SHA,
  'INTENT_NOT_AFTER_UNIX=' + intent.intent_not_after,
].join('\n') + '\n', { mode: 0o600 });

console.log('REFERENCE_BROKER_KEYGEN_PASS=1');
console.log('GRANT_ID=' + grantId);
console.log('BROKER_KEY_ID=' + brokerKeyId);
console.log('AUTHORITY_KEY_ID=' + authorityKeyId);
console.log('HARNESS_SHA=' + HARNESS_SHA);
