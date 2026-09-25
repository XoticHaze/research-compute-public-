import fs from 'node:fs';
import path from 'node:path';
import { webcrypto } from 'node:crypto';

const crypto = webcrypto;

function bytesToB64(bytes) {
  return Buffer.from(bytes).toString('base64');
}

async function sha256Hex(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return Buffer.from(digest).toString('hex');
}

async function makePair() {
  const pair = await crypto.subtle.generateKey(
    { name: 'ECDSA', namedCurve: 'P-256' },
    true,
    ['sign', 'verify'],
  );
  const privateJwk = await crypto.subtle.exportKey('jwk', pair.privateKey);
  const privatePkcs8 = new Uint8Array(await crypto.subtle.exportKey('pkcs8', pair.privateKey));
  const publicRaw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return {
    privateJwk,
    privatePkcs8B64: bytesToB64(privatePkcs8),
    publicB64: bytesToB64(publicRaw),
    keyId: 'sha256:' + await sha256Hex(publicRaw),
  };
}

const outDir = process.argv[2];
if (!outDir) throw new Error('output_directory_required');
fs.mkdirSync(outDir, { recursive: true });

const broker = await makePair();
const authority = await makePair();

fs.writeFileSync(path.join(outDir, 'broker-private.jwk'), JSON.stringify(broker.privateJwk) + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'broker-public.b64'), broker.publicB64 + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'broker-key-id.txt'), broker.keyId + '\n', { mode: 0o600 });

fs.writeFileSync(path.join(outDir, 'authority-private.pkcs8.b64'), authority.privatePkcs8B64 + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'authority-public.b64'), authority.publicB64 + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'authority-key-id.txt'), authority.keyId + '\n', { mode: 0o600 });

console.log('REFERENCE_KEYGEN_PASS=1');
console.log('BROKER_KEY_ID=' + broker.keyId);
console.log('AUTHORITY_KEY_ID=' + authority.keyId);
