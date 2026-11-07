// Pi owner grants use the installed cc-pi4 root verifier byte contract.
// Source implementation only: no signing identity, root key or queue authority is installed by this file.
const KEY_ID = 'ccpi-owner-bootstrap-ed25519-v1';
const DOMAINS = Object.freeze({
  bootstrap: 'commandcenter.pi.bot_owner_bootstrap_approval.v1\u0000',
  replace: 'commandcenter.pi.bot_replace_approval.v1\u0000',
});
const B_FIELDS = [
  'schema', 'node_id', 'request_id', 'request_sha256', 'source_sha', 'image_ref',
  'expires_at', 'snapshot_sha256', 'expected_account_sha256',
  'canonical_start_receipt_sha256', 'writer_lease_receipt_sha256',
  'review_epoch_utc', 'no_pi_live_orders_before_epoch_verified',
  'exclusive_writer_lease_reviewed', 'selected_strategy_pins_sha256',
  'approve_new_pi_owned_zero_only',
];
const R_FIELDS = [
  'schema', 'request_id', 'source_sha', 'image_ref',
  'expected_active_source_sha', 'expected_active_image_ref',
  'artifact_manifest_blob_sha', 'client_id', 'inspect_client_id',
  'expected_release', 'runtime_mode', 'acknowledge_existing_live_mode_preserved',
  'expires_at',
];
const BASE_REQUEST = [
  'schema', 'node_id', 'request_id', 'action', 'source_repo', 'source_sha',
  'image_ref', 'client_id', 'inspect_client_id', 'artifact_manifest_blob_sha',
  'expected_release', 'created_at', 'expires_at',
];
const B_REQUEST = [
  'schema', 'node_id', 'request_id', 'action', 'source_sha', 'image_ref',
  'expected_release', 'created_at', 'expires_at',
];
const QUEUE_REPO = 'XoticHaze/CommandCenter-gate-control';
const QUEUE_REF = 'pi-node-inbox';
const APPROVAL_PATHS = Object.freeze({
  bootstrap: 'pi-node/bot-owner-signed-approval.json',
  replace: 'pi-node/bot-replace-signed-approval.json',
});
const REQUEST_PATH = 'pi-node/bot-release-request.json';
const te = new TextEncoder();

function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function strictFields(value, fields) {
  if (!object(value) || Object.keys(value).length !== fields.length
      || !fields.every((key) => Object.hasOwn(value, key))) {
    throw new Error('pi_owner_exact_fields_required');
  }
}
function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (object(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  if (typeof value === 'string') {
    // All supported Pi approval fields are ASCII. Avoid Python ensure_ascii
    // versus JavaScript UTF-16 escape differences and reject hidden controls.
    if (!/^[\x20-\x7e]*$/.test(value)) throw new Error('pi_owner_non_ascii_or_control');
    return value;
  }
  if (typeof value === 'boolean' || value === null || Number.isSafeInteger(value)) return value;
  throw new Error('pi_owner_json_value_invalid');
}
export function canonicalPiJson(value) {
  return JSON.stringify(stable(value)) + '\n';
}
function shaHex(bytes) {
  return crypto.subtle.digest('SHA-256', bytes).then((digest) =>
    [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, '0')).join(''));
}
const SHA40 = /^[0-9a-f]{40}$/;
const SHA64 = /^[0-9a-f]{64}$/;
const REQ = /^[A-Za-z0-9._:-]{6,100}$/;
const IMAGE = /^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$/;
function time(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)$/.test(value)) {
    throw new Error('pi_owner_utc_time_required');
  }
  const result = Date.parse(value);
  if (!Number.isFinite(result)) throw new Error('pi_owner_time_invalid');
  return result;
}
export async function validatePiOwnerApproval(kind, approval, request, now = Date.now()) {
  if (!Object.hasOwn(DOMAINS, kind)) throw new Error('pi_owner_operation_unknown');
  strictFields(approval, kind === 'bootstrap' ? B_FIELDS : R_FIELDS);
  strictFields(request, kind === 'bootstrap' ? B_REQUEST : [...BASE_REQUEST, 'expected_active_source_sha', 'expected_active_image_ref', 'runtime_mode']);
  if (approval.schema !== 'commandcenter.pi.bot_' + (kind === 'bootstrap' ? 'owner_bootstrap' : 'replace') + '_approval.v1'
      || request.schema !== 'commandcenter.pi.bot_' + (kind === 'bootstrap' ? 'owner_bootstrap' : 'release') + '_request.v1'
      || request.node_id !== 'cc-pi4' || !REQ.test(request.request_id)
      || request.action !== (kind === 'bootstrap' ? 'pi.bot.owner_bootstrap' : 'pi.bot.replace_existing')
      || !SHA40.test(request.source_sha) || !IMAGE.test(request.image_ref)
      || !/^r[0-9a-f]{12}$/.test(request.expected_release)
      || request.request_id !== approval.request_id
      || request.source_sha !== approval.source_sha
      || request.image_ref !== approval.image_ref
      || request.expires_at !== approval.expires_at) {
    throw new Error('pi_owner_request_identity_mismatch');
  }
  const created = time(request.created_at);
  const expires = time(request.expires_at);
  if (created > now + 120000 || expires <= now || created >= expires
      || expires - created > 3600000 || expires > now + (kind === 'bootstrap' ? 180000 : 600000)) {
    throw new Error('pi_owner_request_not_fresh');
  }
  if (kind === 'bootstrap') {
    if (approval.node_id !== 'cc-pi4'
        || approval.request_sha256 !== await shaHex(te.encode(canonicalPiJson(request)))
        || ![approval.snapshot_sha256, approval.expected_account_sha256,
          approval.canonical_start_receipt_sha256, approval.writer_lease_receipt_sha256,
          approval.selected_strategy_pins_sha256].every((v) => typeof v === 'string' && SHA64.test(v))
        || approval.no_pi_live_orders_before_epoch_verified !== true
        || approval.exclusive_writer_lease_reviewed !== true
        || approval.approve_new_pi_owned_zero_only !== true
        || now - time(approval.review_epoch_utc) < 0
        || now - time(approval.review_epoch_utc) > 180000) {
      throw new Error('pi_owner_independent_bootstrap_proof_required');
    }
  } else {
    if (request.source_repo !== 'XoticHaze/mm-IBKR'
        || request.runtime_mode !== 'PRESERVE_EXISTING_LIVE'
        || request.expected_active_source_sha !== approval.expected_active_source_sha
        || request.expected_active_image_ref !== approval.expected_active_image_ref
        || request.artifact_manifest_blob_sha !== approval.artifact_manifest_blob_sha
        || request.client_id !== approval.client_id
        || request.inspect_client_id !== approval.inspect_client_id
        || request.expected_release !== approval.expected_release
        || approval.runtime_mode !== 'PRESERVE_EXISTING_LIVE'
        || approval.acknowledge_existing_live_mode_preserved !== true
        || !SHA40.test(approval.expected_active_source_sha)
        || !IMAGE.test(approval.expected_active_image_ref)
        || !SHA40.test(approval.artifact_manifest_blob_sha)
        || !Number.isInteger(approval.client_id) || !Number.isInteger(approval.inspect_client_id)
        || approval.client_id < 1 || approval.client_id > 65535 || approval.client_id === 79
        || approval.inspect_client_id < 1 || approval.inspect_client_id > 65535
        || [79, approval.client_id].includes(approval.inspect_client_id)
        || approval.expected_active_source_sha === approval.source_sha
        || approval.expected_active_image_ref === approval.image_ref) {
      throw new Error('pi_owner_exact_live_preservation_required');
    }
  }
  const raw = te.encode(canonicalPiJson(approval));
  if (raw.length > 3500 || /\b(?:broker_net_qty|password|account_number|private_key)\b/i.test(canonicalPiJson(approval))) {
    throw new Error('pi_owner_grant_private_data_rejected');
  }
  return { request_id: request.request_id, approval_hash: await shaHex(raw) };
}
function b64(bytes) {
  let s = '';
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s);
}
function unb64(value) {
  const s = atob(value);
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}
function pem(spki) {
  const s = b64(spki);
  return '-----BEGIN PUBLIC KEY-----\n' + (s.match(/.{1,64}/g) || []).join('\n')
    + '\n-----END PUBLIC KEY-----\n';
}
function safeEq(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}
function requireOwner(env, operator) {
  const email = String(operator?.email || '').trim().toLowerCase();
  const emails = String(env.PI_OWNER_SIGNER_ALLOWED_EMAILS || '').split(',')
    .map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (!email || !emails.length || !emails.includes(email) || !operator?.sub) {
    throw new Error('pi_owner_distinct_operator_allowlist_required');
  }
}
async function requireActivation(env, code) {
  const expected = String(env.PI_OWNER_INIT_CODE_SHA256 || '').trim().toLowerCase();
  if (!SHA64.test(expected) || typeof code !== 'string' || code.length < 24 || code.length > 256
      || !safeEq(await shaHex(te.encode(code)), expected)) {
    throw new Error('pi_owner_independent_activation_required');
  }
}
export class PiOwnerApprovalState {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }
  async fetch(request) {
    const url = new URL(request.url);
    try {
      if (request.method === 'GET' && url.pathname === '/status') {
        const key = await this.ctx.storage.get('pi_owner_key_v1');
        const enrollment = await this.ctx.storage.get('pi_owner_enrollment_v1');
        return json({ schema: 'commandcenter.pi.owner_signer_status.v1',
          initialized: Boolean(key), enrolled: Boolean(enrollment),
          public_key_pem: key?.public_key_pem || null,
          public_key_sha256: key?.public_key_sha256 || null,
          signing_enabled: this.env.PI_OWNER_SIGNER_ENABLED === '1',
          github_transport_configured: Boolean(this.env.PI_OWNER_QUEUE_GITHUB_TOKEN),
        });
      }
      if (request.method !== 'POST') return json({error:'pi_owner_route_unsupported'},404);
      const raw = await request.text();
      if (te.encode(raw).length > 8192) return json({error:'pi_owner_payload_oversize'},413);
      const body = JSON.parse(raw);
      requireOwner(this.env, body.operator);
      if (url.pathname === '/initialize') {
        await requireActivation(this.env, body.activation_code);
        let entry = await this.ctx.storage.get('pi_owner_key_v1');
        if (entry) return json({error:'pi_owner_key_already_initialized'},409);
        const kp = await crypto.subtle.generateKey('Ed25519', true, ['sign', 'verify']);
        const spki = new Uint8Array(await crypto.subtle.exportKey('spki', kp.publicKey));
        const pkcs8 = new Uint8Array(await crypto.subtle.exportKey('pkcs8', kp.privateKey));
        const candidate = {
          private_pkcs8_b64: b64(pkcs8), public_key_pem: pem(spki),
          public_key_sha256: await shaHex(spki),
        };
        const result = await this.ctx.storage.transaction(async (txn) => {
          if (await txn.get('pi_owner_key_v1')) return false;
          await txn.put('pi_owner_key_v1', candidate);
          return true;
        });
        if (!result) return json({error:'pi_owner_key_already_initialized'},409);
        entry = await this.ctx.storage.get('pi_owner_key_v1');
        if (entry?.public_key_sha256 !== candidate.public_key_sha256) throw new Error('pi_owner_key_readback_failed');
        return json({schema:'commandcenter.pi.owner_key_issue.v1',
          public_key_pem: entry.public_key_pem,
          public_key_sha256: entry.public_key_sha256,
          one_time_created: true, pi_root_enrolled: false},201);
      }
      if (url.pathname === '/enroll') {
        await requireActivation(this.env, body.activation_code);
        const entry = await this.ctx.storage.get('pi_owner_key_v1');
        if (!entry || !safeEq(body.pi_enrolled_public_key_sha256, entry.public_key_sha256)
            || body.confirm_independently_enrolled_on_pi !== true) {
          throw new Error('pi_owner_root_enrollment_confirmation_required');
        }
        const current = await this.ctx.storage.get('pi_owner_enrollment_v1');
        if (current) return json({error:'pi_owner_enrollment_already_recorded'},409);
        const enrollment = {key_sha256: entry.public_key_sha256,
          confirmed_by_operator: body.operator.email, confirmed_at_utc: new Date().toISOString(),
          evidence_kind: 'operator-attested-not-pi-attested'};
        await this.ctx.storage.put('pi_owner_enrollment_v1', enrollment);
        return json({recorded: true, pi_root_independent_readback: false},201);
      }
      if (url.pathname === '/sign') {
        if (this.env.PI_OWNER_SIGNER_ENABLED !== '1'
            || !this.env.PI_OWNER_QUEUE_GITHUB_TOKEN) throw new Error('pi_owner_protected_activation_incomplete');
        const entry = await this.ctx.storage.get('pi_owner_key_v1');
        const enrolled = await this.ctx.storage.get('pi_owner_enrollment_v1');
        if (!entry || !enrolled || enrolled.key_sha256 !== entry.public_key_sha256
            || body.approve_exact_release !== true
            || !safeEq(String(this.env.PI_OWNER_ENROLLED_PUB_SHA256 || ''), entry.public_key_sha256)) {
          throw new Error('pi_owner_trust_anchor_not_activated');
        }
        const accepted = await validatePiOwnerApproval(body.kind, body.approval, body.request);
        const storageKey = 'pi_owner_issued_v1/' + accepted.request_id;
        const previous = await this.ctx.storage.get(storageKey);
        if (previous) {
          if (previous.approval_hash !== accepted.approval_hash) {
            return json({error:'pi_owner_request_id_replay_conflict'},409);
          }
          return json({schema:'commandcenter.pi.owner_grant_issued.v1',
            signed_grant:previous.signed_grant, recovered:true,
            key_sha256:entry.public_key_sha256, request_id:accepted.request_id});
        }
        const key = await crypto.subtle.importKey('pkcs8',
          unb64(entry.private_pkcs8_b64), 'Ed25519', false, ['sign']);
        const signature = await crypto.subtle.sign('Ed25519', key,
          te.encode(DOMAINS[body.kind] + canonicalPiJson(body.approval)));
        const signedGrant = {...body.approval, key_id: KEY_ID, signature_b64: b64(signature)};
        const result = await this.ctx.storage.transaction(async (txn) => {
          if (await txn.get(storageKey)) return false;
          await txn.put(storageKey, {approval_hash:accepted.approval_hash,
            signed_grant:signedGrant, issued_at_utc:new Date().toISOString(),
            operator_email:body.operator.email, kind:body.kind});
          return true;
        });
        if (!result) return json({error:'pi_owner_concurrent_issue_retry'},409);
        return json({schema:'commandcenter.pi.owner_grant_issued.v1',
          signed_grant:signedGrant, recovered:false,
          key_sha256:entry.public_key_sha256, request_id:accepted.request_id},201);
      }
      return json({error:'pi_owner_route_unsupported'},404);
    } catch (error) {
      return json({error:String(error?.message || 'pi_owner_rejected')},403);
    }
  }
}
async function githubFile(token, path) {
  const url = 'https://api.github.com/repos/' + QUEUE_REPO + '/contents/' + path
    + '?ref=' + encodeURIComponent(QUEUE_REF);
  const response = await fetch(url, {
    headers: {'authorization':'Bearer ' + token, 'accept':'application/vnd.github+json',
      'x-github-api-version':'2022-11-28'}, redirect:'manual',
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('pi_owner_private_queue_read_unavailable');
  const doc = await response.json();
  if (!SHA40.test(doc.sha) || typeof doc.content !== 'string' || doc.encoding !== 'base64') {
    throw new Error('pi_owner_private_queue_snapshot_invalid');
  }
  return {sha:doc.sha, text:new TextDecoder().decode(unb64(doc.content.replace(/\s/g,'')))};
}
function queueSlotFree(old, newRequestId, now) {
  if (!old) return true;
  let previous;
  try { previous = JSON.parse(old.text); }
  catch { return false; }
  if (!REQ.test(previous?.request_id || '')) return false;
  if (previous.request_id === newRequestId) return false;
  const expiry = Date.parse(previous.expires_at || '');
  return Number.isFinite(expiry) && expiry <= now - 120000;
}
async function githubPut(token, path, doc, old) {
  const body = {message:'ccpi owner-signed exact approval: protected phone action',
    content:b64(te.encode(canonicalPiJson(doc))), branch:QUEUE_REF};
  if (old) body.sha = old.sha;
  const url = 'https://api.github.com/repos/' + QUEUE_REPO + '/contents/' + path;
  const response = await fetch(url, {
    method:'PUT', redirect:'manual',
    headers:{'authorization':'Bearer ' + token, 'accept':'application/vnd.github+json',
      'content-type':'application/json', 'x-github-api-version':'2022-11-28'},
    body:JSON.stringify(body),
  });
  if (!response.ok) throw new Error('pi_owner_private_queue_write_failed');
  const result = await response.json();
  if (!SHA40.test(result?.content?.sha || '')) throw new Error('pi_owner_private_queue_write_unverified');
  const observed = await githubFile(token, path);
  if (observed?.sha !== result.content.sha || observed.text !== canonicalPiJson(doc)) {
    throw new Error('pi_owner_private_queue_readback_mismatch');
  }
  return observed.sha;
}
export async function publishPiOwnerGrant(env, kind, approval, request, signedGrant) {
  const token = String(env.PI_OWNER_QUEUE_GITHUB_TOKEN || '');
  if (token.length < 20) throw new Error('pi_owner_queue_credential_missing');
  await validatePiOwnerApproval(kind, approval, request);
  if (signedGrant?.key_id !== KEY_ID || signedGrant?.signature_b64?.length < 80) {
    throw new Error('pi_owner_signed_grant_missing');
  }
  for (const key of [...(kind === 'bootstrap' ? B_FIELDS : R_FIELDS), 'key_id', 'signature_b64']) {
    if (!Object.hasOwn(signedGrant, key)) throw new Error('pi_owner_signed_grant_incomplete');
  }
  const requestOld = await githubFile(token, REQUEST_PATH);
  const grantPath = APPROVAL_PATHS[kind];
  const grantOld = await githubFile(token, grantPath);
  if (!queueSlotFree(requestOld, request.request_id, Date.now())
      || !queueSlotFree(grantOld, request.request_id, Date.now())) {
    throw new Error('pi_owner_private_queue_occupied');
  }
  const grantBlob = await githubPut(token, grantPath, signedGrant, grantOld);
  // Approval first; the Pi never sees a mutating request without its exact grant.
  const requestBlob = await githubPut(token, REQUEST_PATH, request, requestOld);
  return {schema:'commandcenter.pi.owner_grant_dispatched.v1',
    request_id:request.request_id, kind, branch:QUEUE_REF,
    signed_grant_blob_sha:grantBlob, request_blob_sha:requestBlob,
    root_receipt_verified:false, protected_mutation_claimed:false};
}
