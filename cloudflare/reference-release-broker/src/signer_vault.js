// Cloudflare-native, non-exporting release-ticket signer for #809.
// Private key never appears in a public response, GitHub source, or an admin
// receipt. Initial issuance is an independently approved *scheduled* action
// in the containing Worker. This DO has no public routing.
import { signReleaseTicket } from './ticket.js';

const KEY = 'reference_broker_p256_ticket_signer_v1';
const APPROVAL = /^cc809-[0-9a-f]{32}$/;
const KEY_ID = /^sha256:[0-9a-f]{64}$/;
const HEX40 = /^[0-9a-f]{40}$/;
const GRANT = /^[A-Za-z0-9_-]{16,128}$/;
const RUN = /^[1-9][0-9]{0,19}$/;
const FIELDS = new Set([
  'grant_id', 'run_id', 'run_attempt', 'harness_sha',
  'worker_key_id', 'admission_not_after',
]);

function response(node, status = 200) {
  return new Response(JSON.stringify(node), {
    status,
    headers: { 'content-type':'application/json', 'cache-control':'no-store' },
  });
}
function safeB64(bytes) {
  let text = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(text);
}
async function sha256(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return [...digest].map(x => x.toString(16).padStart(2,'0')).join('');
}
function validClaims(c, now) {
  if (!c || typeof c !== 'object' || Array.isArray(c) ||
      Object.keys(c).length !== FIELDS.size ||
      Object.keys(c).some(k => !FIELDS.has(k))) return false;
  return GRANT.test(c.grant_id) && RUN.test(String(c.run_id)) &&
    RUN.test(String(c.run_attempt)) && HEX40.test(c.harness_sha) &&
    KEY_ID.test(c.worker_key_id) && Number.isInteger(c.admission_not_after) &&
    c.admission_not_after > now && c.admission_not_after <= now + 900;
}
async function readBody(request, limit = 3072) {
  const raw = await request.text();
  if (!raw || raw.length > limit) throw new Error('size');
  const node = JSON.parse(raw);
  if (!node || typeof node !== 'object' || Array.isArray(node)) throw new Error('shape');
  return node;
}

export class BrokerSignerVault {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const existing = await this.state.storage.get(KEY);
    if (request.method === 'GET' && url.pathname === '/public-key') {
      if (!existing) return response({error:'unavailable'}, 503);
      return response({public_b64:existing.public_b64, key_id:existing.key_id});
    }
    if (request.method === 'POST' && url.pathname === '/initial-seal') {
      let node;
      try { node = await readBody(request, 512); }
      catch { return response({error:'approval_rejected'}, 400); }
      if (Object.keys(node).sort().join(',') !== 'approval_id,not_after' ||
          !APPROVAL.test(node.approval_id) ||
          !Number.isInteger(node.not_after) ||
          node.not_after <= Math.floor(Date.now()/1000) ||
          node.not_after > Math.floor(Date.now()/1000) + 172800) {
        return response({error:'approval_rejected'}, 400);
      }
      if (existing) {
        return existing.approval_id === node.approval_id
          ? response({ok:true, created:false, key_id:existing.key_id})
          : response({error:'already_sealed'}, 409);
      }
      // Transactional first write. Even concurrent initiators cannot replace
      // a preexisting signer. Do not rotate when an approval is replayed.
      const result = await this.state.storage.transaction(async txn => {
        const prior = await txn.get(KEY);
        if (prior) return {record:prior, created:false};
        const pair = await crypto.subtle.generateKey(
          {name:'ECDSA', namedCurve:'P-256'}, true, ['sign','verify']
        );
        const jwk = await crypto.subtle.exportKey('jwk', pair.privateKey);
        const raw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
        const record = {
          private_jwk:jwk, public_b64:safeB64(raw),
          key_id:'sha256:' + await sha256(raw),
          approval_id:node.approval_id, created_at:Math.floor(Date.now()/1000),
        };
        await txn.put(KEY, record);
        return {record, created:true};
      });
      if (result.record.approval_id !== node.approval_id) {
        return response({error:'already_sealed'}, 409);
      }
      return response({ok:true, created:result.created, key_id:result.record.key_id});
    }
    if (request.method === 'POST' && url.pathname === '/sign-ticket') {
      if (!existing) return response({error:'unavailable'}, 503);
      let node;
      try { node = await readBody(request); }
      catch { return response({error:'ticket_rejected'}, 400); }
      if (Object.keys(node).sort().join(',') !== 'claims,expected_key_id' ||
          node.expected_key_id !== existing.key_id ||
          !validClaims(node.claims, Math.floor(Date.now()/1000))) {
        return response({error:'ticket_rejected'}, 400);
      }
      const key = await crypto.subtle.importKey(
        'jwk', existing.private_jwk,
        {name:'ECDSA',namedCurve:'P-256'}, false, ['sign'],
      );
      const ticket = await signReleaseTicket(
        key, existing.key_id, node.claims, Math.floor(Date.now()/1000)
      );
      return response({ok:true, ticket});
    }
    return response({error:'not_found'}, 404);
  }
}
