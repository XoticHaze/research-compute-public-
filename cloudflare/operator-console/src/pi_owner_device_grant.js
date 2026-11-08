// Owner-device detached grant verification.  No private signing key, crypto
// seed, or owner passphrase is ever accepted or persisted by this Worker.
// GitHub remains a transport writer; cc-pi4 root verifies signatures again.
import { canonicalPiJson, validatePiOwnerApproval } from './pi_owner_approval.js';

const KEY_ID = 'ccpi-owner-bootstrap-ed25519-v1';
const DOMAINS = {
  bootstrap: 'commandcenter.pi.bot_owner_bootstrap_approval.v1\0',
  replace: 'commandcenter.pi.bot_replace_approval.v1\0',
};
const encoder = new TextEncoder();
const SHA64 = /^[0-9a-f]{64}$/;
const B64SIG = /^(?:[A-Za-z0-9+/]{4}){21}==$/; // 64 Ed25519 bytes => 88 chars

function eq(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let out = 0;
  for (let i=0;i<a.length;i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}
function hex(arr) {
  return [...new Uint8Array(arr)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
function decodeSpki(pem) {
  if (typeof pem !== 'string' || pem.length > 1024
      || !/^-----BEGIN PUBLIC KEY-----\s+[A-Za-z0-9+\/\s=]+-----END PUBLIC KEY-----\s*$/.test(pem)) {
    throw new Error('pi_owner_root_public_pem_not_admitted');
  }
  const data = pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g,'');
  let binary;
  try {binary=atob(data);} catch {throw new Error('pi_owner_root_public_pem_invalid');}
  const result=Uint8Array.from(binary, x=>x.charCodeAt(0));
  if (result.length < 40 || result.length > 120) throw new Error('pi_owner_root_public_pem_invalid');
  return result;
}

export async function verifyPiOwnerDeviceGrant(env, operator, kind, request, approval, signed) {
  const owner = String(operator?.email || '').trim().toLowerCase();
  const allowed = String(env.PI_OWNER_SIGNER_ALLOWED_EMAILS || '').split(',')
    .map(s=>s.trim().toLowerCase()).filter(Boolean);
  if (!owner || !operator?.sub || !allowed.includes(owner)) {
    throw new Error('pi_owner_operator_not_admitted');
  }
  if (!Object.hasOwn(DOMAINS,kind)) throw new Error('pi_owner_kind_invalid');
  if (env.PI_OWNER_SIGNER_ENABLED === '1') {
    // The legacy in-Worker signer must never run alongside the independent
    // device-key path, or GitHub source authority would become a second issuer.
    throw new Error('pi_owner_legacy_signer_must_remain_disabled');
  }
  const pin = String(env.PI_OWNER_ENROLLED_PUB_SHA256 || '').toLowerCase();
  if (!SHA64.test(pin)) throw new Error('pi_owner_root_key_enrollment_missing');
  const spki = decodeSpki(env.PI_OWNER_ROOT_PUBLIC_KEY_PEM);
  if (!eq(hex(await crypto.subtle.digest('SHA-256', spki)),pin)) {
    throw new Error('pi_owner_root_public_key_fingerprint_mismatch');
  }

  await validatePiOwnerApproval(kind, approval, request);
  if (signed === null || typeof signed !== 'object' || Array.isArray(signed)
      || signed.key_id !== KEY_ID || typeof signed.signature_b64 !== 'string'
      || !B64SIG.test(signed.signature_b64)
      || Object.keys(signed).length !== Object.keys(approval).length+2) {
    throw new Error('pi_owner_signed_grant_shape_invalid');
  }
  for (const key of Object.keys(approval)) {
    if (!Object.hasOwn(signed,key) || signed[key] !== approval[key]) {
      throw new Error('pi_owner_signed_grant_unsigned_payload_drift');
    }
  }
  const sig = Uint8Array.from(atob(signed.signature_b64),x=>x.charCodeAt(0));
  if (sig.length !== 64) throw new Error('pi_owner_signature_length_invalid');
  const key = await crypto.subtle.importKey('spki',spki,'Ed25519',false,['verify']);
  const message = encoder.encode(DOMAINS[kind] + canonicalPiJson(approval));
  if (!await crypto.subtle.verify('Ed25519', key, sig, message)) {
    throw new Error('pi_owner_device_signature_rejected');
  }
  return {key_sha256:pin,request_id:request.request_id,independent_device_signature_verified:true};
}
