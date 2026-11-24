// Independent, fail-closed Ed25519 PLACED attestation verifier for the existing
// neutral Cloudflare broker. Pure source helper: it grants NO release, claim,
// dispatch, receipt ACK, or public endpoint. A reviewed owner must bind policy
// outside the request and explicitly wire an authenticated caller to GRANT_LEDGER.
const DOMAIN = 'COMMANDCENTER-PLACEMENT-ISSUANCE-V1\n';
const RECEIPT_KEYS = [
  'schema', 'job_id', 'job_sha256', 'lane', 'workload', 'compute_id',
  'executor', 'trust_mode', 'state', 'load_ratio', 'issuer_proof',
];
const PROOF_KEYS = [
  'issuer_id', 'issued_at_utc', 'expires_at_utc', 'nonce',
  'registry_sha256', 'route_sha256',
];
const POLICY_KEYS = [
  'issuer_id', 'issuer_public_b64', 'registry_sha256', 'route_sha256', 'compute_id',
];
const HEX32 = /^[0-9a-f]{32}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const ISSUER_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

function rejected() { throw new Error('PLACEMENT_ISSUER_ATTESTATION_REJECTED'); }
function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function exactKeys(value, keys) {
  return record(value) && Object.keys(value).length === keys.length
    && Object.keys(value).every(k => keys.includes(k));
}
function asciiId(value, max=128) {
  return typeof value === 'string' && value.length >= 1 && value.length <= max
    && /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value) && !value.includes('..');
}
function strictB64(value, maxChars) {
  if (typeof value !== 'string' || value.length < 4 || value.length > maxChars
      || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) rejected();
  try {
    const raw = atob(value);
    if (btoa(raw) !== value) rejected();
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  } catch { rejected(); }
}
function utcSeconds(value) {
  if (typeof value !== 'string' || !ISO_UTC.test(value)) rejected();
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)
      || new Date(milliseconds).toISOString().slice(0,19) + 'Z' !== value) rejected();
  return milliseconds / 1000;
}
function validatePolicy(policy) {
  if (!exactKeys(policy, POLICY_KEYS)
      || !ISSUER_ID.test(policy.issuer_id)
      || !asciiId(policy.compute_id)
      || !HEX64.test(policy.registry_sha256)
      || !HEX64.test(policy.route_sha256)) rejected();
  const publicKey = strictB64(policy.issuer_public_b64, 48);
  if (publicKey.length !== 32) rejected();
  return publicKey;
}

/**
 * Verify exact original CommandCenter DOMAIN + signing_payload() bytes.
 * Policy MUST be supplied from independently approved neutral configuration,
 * never from the request, GitHub mutable fields, or a caller-selected key.
 * Does not consume nonce or authorize dispatch; the owner must separately
 * invoke existing GRANT_LEDGER idFromName('placement:' + nonce) ONCE.
 */
export async function verifySignedPlacementClaim(claim, policy, nowSeconds = Date.now()/1000) {
  const publicKey = validatePolicy(policy);
  if (!exactKeys(claim, ['payload_b64', 'signature_b64'])) rejected();
  const payload = strictB64(claim.payload_b64, 12288);
  const signature = strictB64(claim.signature_b64, 88);
  if (signature.length !== 64 || payload.length > 8192 || payload.length < DOMAIN.length + 50
      || !Number.isFinite(nowSeconds)) rejected();
  let message;
  try { message = new TextDecoder('utf-8', {fatal:true}).decode(payload); }
  catch { rejected(); }
  if (!message.startsWith(DOMAIN)) rejected();
  let receipt;
  try { receipt = JSON.parse(message.slice(DOMAIN.length)); }
  catch { rejected(); }
  if (!exactKeys(receipt, RECEIPT_KEYS)
      || receipt.schema !== 'commandcenter.job_submission_receipt.v1'
      || receipt.state !== 'PLACED'
      || receipt.trust_mode !== 'public_encrypted'
      || !asciiId(receipt.job_id)
      || !asciiId(receipt.lane)
      || !asciiId(receipt.workload)
      || receipt.compute_id !== policy.compute_id
      || !HEX64.test(receipt.job_sha256)
      || !record(receipt.executor)
      || Object.keys(receipt.executor).length === 0
      || typeof receipt.executor.kind !== 'string'
      || receipt.executor.kind !== 'github_actions_generic'
      || typeof receipt.load_ratio !== 'number'
      || !Number.isFinite(receipt.load_ratio)
      || receipt.load_ratio < 0 || receipt.load_ratio > 1) rejected();
  const proof = receipt.issuer_proof;
  if (!exactKeys(proof, PROOF_KEYS)
      || proof.issuer_id !== policy.issuer_id
      || !ISSUER_ID.test(proof.issuer_id)
      || !HEX32.test(proof.nonce)
      || proof.registry_sha256 !== policy.registry_sha256
      || proof.route_sha256 !== policy.route_sha256) rejected();
  const issued = utcSeconds(proof.issued_at_utc);
  const expires = utcSeconds(proof.expires_at_utc);
  if (!(nowSeconds >= issued - 30 && nowSeconds <= issued + 300
      && expires > issued && expires <= issued + 300 && nowSeconds < expires)) rejected();
  try {
    const key = await crypto.subtle.importKey('raw', publicKey, {name:'Ed25519'}, false, ['verify']);
    if (!await crypto.subtle.verify({name:'Ed25519'}, key, signature, payload)) rejected();
  } catch { rejected(); }
  return Object.freeze({
    schema:'commandcenter.placement_issuer_verified.v1',
    issuer_id:proof.issuer_id, nonce:proof.nonce,
    job_sha256:receipt.job_sha256, compute_id:receipt.compute_id,
    trust_mode:'public_encrypted',
    registry_sha256:proof.registry_sha256, route_sha256:proof.route_sha256,
    signature_verified:true, nonce_consumed:false,
    broker_mutation_authorized:false, external_launch_authorized:false,
  });
}

/**
 * Bounded internal composition; no HTTP endpoint is exposed by importing it.
 * Requires independently trusted policy and the existing broker Durable Object
 * binding. Any ambiguous DO result fails closed and is NEVER retried here.
 */
export async function consumeSignedPlacementOnce(claim, policy, grantLedger, nowSeconds = Date.now()/1000) {
  const verified = await verifySignedPlacementClaim(claim, policy, nowSeconds);
  if (!grantLedger || typeof grantLedger.idFromName !== 'function'
      || typeof grantLedger.get !== 'function') rejected();
  let response;
  try {
    const id = grantLedger.idFromName('placement:' + verified.nonce);
    const stub = grantLedger.get(id);
    if (!stub || typeof stub.fetch !== 'function') rejected();
    response = await stub.fetch('https://grant-ledger/consume-placement', {
      method:'POST', headers:{'content-type':'application/json'},
      body:JSON.stringify({nonce:verified.nonce,issuer_id:verified.issuer_id}),
    });
    if (response.status !== 200 || !(await response.json())?.ok) rejected();
  } catch { rejected(); }
  return Object.freeze({...verified, nonce_consumed:true});
}
