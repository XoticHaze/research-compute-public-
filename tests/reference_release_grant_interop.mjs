import fs from 'node:fs';
import { verifyAuthorityGrant } from '../cloudflare/reference-release-broker/src/grant.js';

const wrapper = JSON.parse(fs.readFileSync('reference-authority-grant.json', 'utf8'));
const publicB64 = fs.readFileSync('reference-authority-public.txt', 'utf8').trim();
const expectedAll = JSON.parse(fs.readFileSync('reference-authority-grant-expected.json', 'utf8'));
const now = expectedAll.now;
delete expectedAll.now;

await verifyAuthorityGrant(wrapper, publicB64, expectedAll, now);

const tampered = structuredClone(wrapper);
tampered.signature_b64 = tampered.signature_b64.slice(0, -4) + 'AAAA';
let rejected = false;
try { await verifyAuthorityGrant(tampered, publicB64, expectedAll, now); } catch { rejected = true; }
if (!rejected) throw new Error('tampered_grant_not_rejected');

const wrongBroker = { ...expectedAll, broker_key_id: 'sha256:' + '4'.repeat(64) };
rejected = false;
try { await verifyAuthorityGrant(wrapper, publicB64, wrongBroker, now); } catch { rejected = true; }
if (!rejected) throw new Error('wrong_broker_binding_not_rejected');

console.log('REFERENCE_AUTHORITY_GRANT_INTEROP_PASS=1');
