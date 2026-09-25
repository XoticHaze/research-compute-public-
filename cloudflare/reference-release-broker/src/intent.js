const INTENT_SCHEMA = 'reference-release-intent-v1';
const INTENT_ISSUER = 'private-authority-v1';
const INTENT_AUDIENCE = 'independent-release-broker-v1';
const SIGNATURE_FORMAT = 'ecdsa-p256-sha256-p1363';

function b64ToBytes(value) {
  const raw = atob(value);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

function canonical(node) {
  const ordered = {};
  for (const key of Object.keys(node).sort()) ordered[key] = node[key];
  return JSON.stringify(ordered);
}

async function sha256Hex(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return [...digest].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function validateIntentNode(node, expected, nowSeconds, maxIntentSeconds = 86400) {
  const required = new Set([
    'schema','issuer','audience','grant_id','caller_policy_sha256',
    'harness_sha','broker_key_id','not_before','intent_not_after',
  ]);
  if (!node || Object.keys(node).length !== required.size || Object.keys(node).some((k) => !required.has(k))) {
    throw new Error('intent_fields_rejected');
  }
  if (node.schema !== INTENT_SCHEMA || node.issuer !== INTENT_ISSUER || node.audience !== INTENT_AUDIENCE) {
    throw new Error('intent_schema_rejected');
  }
  for (const field of ['grant_id','caller_policy_sha256','harness_sha','broker_key_id']) {
    if (String(node[field]) !== String(expected[field])) throw new Error(field + '_mismatch');
  }
  const notBefore = Number(node.not_before);
  const expires = Number(node.intent_not_after);
  if (!Number.isFinite(notBefore) || !Number.isFinite(expires) || expires <= notBefore) {
    throw new Error('intent_time_rejected');
  }
  if (nowSeconds < notBefore) throw new Error('intent_not_yet_valid');
  if (expires <= nowSeconds) throw new Error('intent_expired');
  if (expires - notBefore > maxIntentSeconds) throw new Error('intent_window_too_long');
}

async function verifyAuthorityIntent(wrapper, authorityPublicB64, expected, nowSeconds, maxIntentSeconds = 86400) {
  const wrapperFields = new Set(['payload_b64','signature_b64','signer_key_id','signature_format']);
  if (!wrapper || Object.keys(wrapper).length !== wrapperFields.size || Object.keys(wrapper).some((k) => !wrapperFields.has(k))) {
    throw new Error('intent_wrapper_rejected');
  }
  if (wrapper.signature_format !== SIGNATURE_FORMAT) throw new Error('intent_signature_format_rejected');
  const publicRaw = b64ToBytes(authorityPublicB64);
  const keyId = 'sha256:' + await sha256Hex(publicRaw);
  if (wrapper.signer_key_id !== keyId) throw new Error('intent_signer_rejected');
  const publicKey = await crypto.subtle.importKey(
    'raw', publicRaw, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']
  );
  const payload = b64ToBytes(wrapper.payload_b64);
  const signature = b64ToBytes(wrapper.signature_b64);
  if (signature.length !== 64) throw new Error('intent_signature_rejected');
  const ok = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' }, publicKey, signature, payload
  );
  if (!ok) throw new Error('intent_signature_rejected');
  const text = new TextDecoder().decode(payload);
  const node = JSON.parse(text);
  if (canonical(node) !== text) throw new Error('intent_canonicalization_rejected');
  validateIntentNode(node, expected, nowSeconds, maxIntentSeconds);
  return node;
}

export { verifyAuthorityIntent, validateIntentNode };
