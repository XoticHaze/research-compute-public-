const GRANT_SCHEMA = 'reference-release-grant-v1';
const GRANT_ISSUER = 'private-authority-v1';
const GRANT_AUDIENCE = 'independent-release-broker-v1';
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

function validateGrantNode(node, expected, nowSeconds, maxAdmissionSeconds = 900) {
  const required = new Set([
    'schema','issuer','audience','grant_id','run_id','run_attempt',
    'harness_sha','identity_sha256','worker_key_id','broker_key_id','not_before',
    'admission_not_after',
  ]);
  if (!node || Object.keys(node).length !== required.size || Object.keys(node).some((k) => !required.has(k))) {
    throw new Error('grant_fields_rejected');
  }
  if (node.schema !== GRANT_SCHEMA || node.issuer !== GRANT_ISSUER || node.audience !== GRANT_AUDIENCE) {
    throw new Error('grant_schema_rejected');
  }
  if (!/^[0-9a-f]{64}$/.test(String(node.identity_sha256 || ''))) throw new Error('identity_sha256_rejected');
  for (const field of ['grant_id','run_id','run_attempt','harness_sha','identity_sha256','worker_key_id','broker_key_id']) {
    if (String(node[field]) !== String(expected[field])) throw new Error(field + '_mismatch');
  }
  const notBefore = Number(node.not_before);
  const expires = Number(node.admission_not_after);
  if (!Number.isFinite(notBefore) || !Number.isFinite(expires) || expires <= notBefore) {
    throw new Error('grant_time_rejected');
  }
  if (nowSeconds < notBefore) throw new Error('grant_not_yet_valid');
  if (expires <= nowSeconds) throw new Error('grant_expired');
  if (expires - notBefore > maxAdmissionSeconds) throw new Error('grant_ttl_too_long');
}

async function verifyAuthorityGrant(wrapper, authorityPublicB64, expected, nowSeconds, maxAdmissionSeconds = 900) {
  const wrapperFields = new Set(['payload_b64','signature_b64','signer_key_id','signature_format']);
  if (!wrapper || Object.keys(wrapper).length !== wrapperFields.size || Object.keys(wrapper).some((k) => !wrapperFields.has(k))) {
    throw new Error('grant_wrapper_rejected');
  }
  if (wrapper.signature_format !== SIGNATURE_FORMAT) throw new Error('grant_signature_format_rejected');

  const publicRaw = b64ToBytes(authorityPublicB64);
  const keyId = 'sha256:' + await sha256Hex(publicRaw);
  if (wrapper.signer_key_id !== keyId) throw new Error('grant_signer_key_rejected');

  const publicKey = await crypto.subtle.importKey(
    'raw',
    publicRaw,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify'],
  );
  const payload = b64ToBytes(wrapper.payload_b64);
  const signature = b64ToBytes(wrapper.signature_b64);
  if (signature.length !== 64) throw new Error('grant_signature_rejected');

  const ok = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    publicKey,
    signature,
    payload,
  );
  if (!ok) throw new Error('grant_signature_rejected');

  const node = JSON.parse(new TextDecoder().decode(payload));
  if (canonical(node) !== new TextDecoder().decode(payload)) {
    throw new Error('grant_canonicalization_rejected');
  }
  validateGrantNode(node, expected, nowSeconds, maxAdmissionSeconds);
  return node;
}

export { verifyAuthorityGrant, validateGrantNode };
