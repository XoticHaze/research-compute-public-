// Bounded OverEmploy owner source -> opaque ciphertext, entirely inside
// the existing authenticated Fleet Authority Worker. Never return raw source.
const RELEASE_REQUEST = 'contracts/private_web_release_request.v1.json';
const PRIVATE_REPO = 'XoticHaze/OverEmploy';
const EXACT_FILES = Object.freeze([
  'candidate_action_board.html',
  'candidate_action_board.js',
  'private_qualification.html',
  'private_qualification.js',
]);
const BASE = '/assets/overemploy/';
const PLAIN_SCHEMA = 'commandcenter.private_web_plain_overlay.v1';
const CAPSULE_SCHEMA = 'commandcenter.private_web_ciphertext_capsule.v1';
const HEX40 = /^[a-f0-9]{40}$/;
const HEX64 = /^[a-f0-9]{64}$/;
const MAX_FILE_BYTES = 512 * 1024;
const MAX_PLAIN_BYTES = 1000000;

const toB64 = (bytes) => {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let raw = '';
  for (let i = 0; i < view.length; i += 0x8000) {
    raw += String.fromCharCode(...view.subarray(i, i + 0x8000));
  }
  return btoa(raw);
};
const fromB64 = (encoded) => Uint8Array.from(
  atob(String(encoded || '').replace(/\s/g, '')), c => c.charCodeAt(0));
const digest = async (bytes) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
  .map(x => x.toString(16).padStart(2, '0')).join('');

async function getPrivateFile(token, ref, path, fetchImpl) {
  if (!token || token.length > 512 || /[\r\n\0]/.test(token)) {
    throw new Error('private_web_owner_source_token_unavailable');
  }
  if (ref !== 'main' && !HEX40.test(ref)) {
    throw new Error('private_web_owner_ref_invalid');
  }
  if (!/^[a-zA-Z0-9_.\/-]{1,160}$/.test(path) || path.includes('..')) {
    throw new Error('private_web_owner_path_rejected');
  }
  const url = 'https://api.github.com/repos/' + PRIVATE_REPO
    + '/contents/' + path + '?ref=' + ref;
  const response = await fetchImpl(url, {
    method: 'GET', redirect: 'manual', headers: {
      Accept: 'application/vnd.github+json',
      Authorization: 'Bearer ' + token,
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'cc-private-web-opaque-owner-seal',
    },
  });
  if (!response.ok) throw new Error('private_web_owner_source_read_denied');
  const node = await response.json();
  if (!node || node.type !== 'file' || node.encoding !== 'base64'
      || typeof node.content !== 'string' || node.content.length > 750000) {
    throw new Error('private_web_owner_source_type_rejected');
  }
  const raw = fromB64(node.content);
  if (raw.length === 0 || raw.length > MAX_FILE_BYTES
      || Number(node.size) !== raw.length) {
    throw new Error('private_web_owner_source_size_rejected');
  }
  return raw;
}

function decodeJSON(bytes) {
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
function exactKeys(value, expected) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === expected.length
    && expected.every(key => Object.hasOwn(value, key));
}
function ownerRelease(request, expectedSha) {
  if (!request || request.schema !== 'commandcenter.private_web_release_request.v1'
      || request.project !== 'overemploy'
      || request.owning_repository !== PRIVATE_REPO
      || !HEX40.test(String(request.source_pin_sha || ''))
      || request.source_pin_sha !== expectedSha
      || request.source_spec !== 'operator/web_surface.v1.json') {
    throw new Error('private_web_owner_release_authority_not_admitted');
  }
  const expectedPaths = [
    ...EXACT_FILES.map(name => BASE + name),
    BASE + 'index.html',
  ];
  const assetHashes = request.expected_asset_sha256;
  if (!exactKeys(assetHashes, expectedPaths)
      || expectedPaths.some(path => !HEX64.test(assetHashes[path]))
      || assetHashes[BASE + 'index.html'] !== assetHashes[BASE + EXACT_FILES[0]]) {
    throw new Error('private_web_owner_release_manifest_rejected');
  }
  return assetHashes;
}

function verifySpec(node) {
  if (!exactKeys(node, ['schema', 'slug', 'entrypoint', 'files'])
      || node.schema !== 'commandcenter.private_web_app_source.v1'
      || node.slug !== 'overemploy'
      || node.entrypoint !== EXACT_FILES[0]
      || !Array.isArray(node.files) || node.files.length !== EXACT_FILES.length
      || new Set(node.files).size !== EXACT_FILES.length
      || node.files.some(name => !EXACT_FILES.includes(name))) {
    throw new Error('private_web_owner_asset_spec_mismatch');
  }
}
function verifyHTML(body) {
  const html = new TextDecoder('utf-8', { fatal: true }).decode(body);
  if (/\bon[a-z]+\s*=|javascript\s*:/i.test(html)) {
    throw new Error('private_web_inline_event_handler_rejected');
  }
  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)];
  for (const script of scripts) {
    const src = script[1].match(/\bsrc\s*=\s*["']\.\/([a-zA-Z0-9_.-]+)["']/i);
    if (!src || script[2].trim() || !EXACT_FILES.includes(src[1])) {
      throw new Error('private_web_inline_script_rejected');
    }
  }
}

export async function sealPrivateOverEmploy(env, sourceKey, {
  fetchImpl = fetch,
} = {}) {
  // Owner approval lives only in the Cloudflare Worker environment.
  const approvedSha = String(env.CC_PRIVATE_WEB_APPROVED_OWNER_SOURCE_SHA || '');
  if (env.CC_PRIVATE_WEB_SOURCE_STAGE_ENABLED !== '1' || !HEX40.test(approvedSha)) {
    throw new Error('private_web_source_stage_owner_approval_missing');
  }
  const token = String(env.MMIBKR_PRIVATE_SOURCE_TOKEN || '');
  const request = decodeJSON(await getPrivateFile(token, 'main', RELEASE_REQUEST, fetchImpl));
  const expected = ownerRelease(request, approvedSha);
  const sourceSpec = decodeJSON(await getPrivateFile(
    token, approvedSha, 'operator/web_surface.v1.json', fetchImpl));
  verifySpec(sourceSpec);
  const files = {};
  for (const name of EXACT_FILES) {
    const raw = await getPrivateFile(token, approvedSha, 'operator/' + name, fetchImpl);
    const sha = await digest(raw);
    if (sha !== expected[BASE + name]) {
      throw new Error('private_web_owner_source_digest_mismatch');
    }
    if (name.endsWith('.html')) verifyHTML(raw);
    files['assets/overemploy/' + name] = { sha256: sha, data_b64: toB64(raw) };
  }
  files['assets/overemploy/index.html'] = files['assets/overemploy/' + EXACT_FILES[0]];
  const plaintext = new TextEncoder().encode(JSON.stringify({
    schema: PLAIN_SCHEMA, app_slug: 'overemploy',
    source_sha: approvedSha, source_pin_verified: true, files,
  }));
  if (plaintext.length > MAX_PLAIN_BYTES) {
    throw new Error('private_web_owner_plaintext_size_rejected');
  }
  if (!sourceKey || sourceKey.schema !== 'mmibkr-source-vault-public-key-v1'
      || sourceKey.ok !== true || sourceKey.algorithm !== 'RSA-OAEP-256'
      || sourceKey.private_key_exported !== false
      || !/^sha256:[a-f0-9]{64}$/.test(String(sourceKey.key_id || ''))
      || !sourceKey.public_jwk || sourceKey.public_jwk.kty !== 'RSA') {
    throw new Error('private_web_source_key_not_verified');
  }
  const rsa = await crypto.subtle.importKey('jwk', sourceKey.public_jwk,
    { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt']);
  const key = crypto.getRandomValues(new Uint8Array(32));
  const sealed = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, rsa, key);
  const aes = await crypto.subtle.importKey('raw', key,
    { name: 'AES-GCM' }, false, ['encrypt']);
  const capsuleId = 'private-web-' + crypto.randomUUID();
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aad = new TextEncoder().encode(CAPSULE_SCHEMA + '|' + capsuleId);
  const ciphertext = new Uint8Array(await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce, additionalData: aad }, aes, plaintext));
  return {
    schema: CAPSULE_SCHEMA,
    capsule_id: capsuleId,
    cipher: 'AES-256-GCM+RSA-OAEP-256',
    key_id: sourceKey.key_id,
    nonce_b64: toB64(nonce), aad_b64: toB64(aad),
    sealed_key_b64: toB64(new Uint8Array(sealed)),
    ciphertext_b64: toB64(ciphertext),
    ciphertext_sha256: await digest(ciphertext),
  };
}

const HELD_REASONS = new Set([
  'private_web_source_stage_owner_approval_missing',
  'private_web_owner_source_token_unavailable',
  'private_web_owner_source_read_denied',
  'private_web_owner_release_authority_not_admitted',
  'private_web_owner_release_manifest_rejected',
  'private_web_owner_asset_spec_mismatch',
  'private_web_owner_source_digest_mismatch',
  'private_web_inline_script_rejected',
  'private_web_inline_event_handler_rejected',
  'private_web_source_key_not_verified',
]);

// Never return arbitrary provider exception text, private URLs, source SHA or token.
export function privateWebHeldReason(error) {
  const code = String(error?.message || '');
  return HELD_REASONS.has(code) ? code : 'private_web_source_unclassified_denial';
}
