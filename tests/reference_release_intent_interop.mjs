import fs from 'node:fs';
import { verifyAuthorityIntent } from '../cloudflare/reference-release-broker/src/intent.js';

const wrapper = JSON.parse(fs.readFileSync('reference-authority-intent.json', 'utf8'));
const publicB64 = fs.readFileSync('reference-authority-intent-public.txt', 'utf8').trim();
const expectedAll = JSON.parse(fs.readFileSync('reference-authority-intent-expected.json', 'utf8'));
const now = expectedAll.now;
delete expectedAll.now;

await verifyAuthorityIntent(wrapper, publicB64, expectedAll, now);

const tampered = structuredClone(wrapper);
tampered.signature_b64 = tampered.signature_b64.slice(0, -4) + 'AAAA';
let rejected = false;
try { await verifyAuthorityIntent(tampered, publicB64, expectedAll, now); } catch { rejected = true; }
if (!rejected) throw new Error('tampered_intent_not_rejected');

const wrongPolicy = { ...expectedAll, caller_policy_sha256: '6'.repeat(64) };
rejected = false;
try { await verifyAuthorityIntent(wrapper, publicB64, wrongPolicy, now); } catch { rejected = true; }
if (!rejected) throw new Error('wrong_caller_policy_not_rejected');

console.log('REFERENCE_AUTHORITY_INTENT_INTEROP_PASS=1');
