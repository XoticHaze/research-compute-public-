import { verifyAuthorityGrant } from './grant.js';
import {
  generateSigningKeypair,
  signReleaseTicket,
  validateClaims,
} from './ticket.js';

const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const EXPECTED_AUDIENCE = 'secure-compute-reference-v1';
const MAX_BODY = 32768;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'content-security-policy': "default-src 'none'",
      'x-content-type-options': 'nosniff',
    },
  });
}

function b64urlToBytes(value) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=');
  const raw = atob(padded);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

function b64ToBytes(value) {
  const raw = atob(value);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function sha256Hex(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return [...digest].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function verifyGithubOidc(jwt) {
  const parts = String(jwt || '').split('.');
  if (parts.length !== 3) throw new Error('oidc_invalid');
  let header;
  let claims;
  try {
    header = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[0])));
    claims = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[1])));
  } catch {
    throw new Error('oidc_invalid');
  }
  if (header.alg !== 'RS256' || typeof header.kid !== 'string' || !header.kid) {
    throw new Error('oidc_header_rejected');
  }

  const jwksResponse = await fetch(GITHUB_JWKS, {
    headers: { accept: 'application/json' },
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!jwksResponse.ok) throw new Error('oidc_jwks_unavailable');
  const jwks = await jwksResponse.json();
  const jwk = Array.isArray(jwks.keys)
    ? jwks.keys.find((k) => k.kid === header.kid && k.kty === 'RSA')
    : null;
  if (!jwk) throw new Error('oidc_key_unknown');

  const key = await crypto.subtle.importKey(
    'jwk',
    { ...jwk },
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  const ok = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    key,
    b64urlToBytes(parts[2]),
    new TextEncoder().encode(parts[0] + '.' + parts[1]),
  );
  if (!ok) throw new Error('oidc_signature_rejected');
  if (claims.iss !== GITHUB_ISSUER) throw new Error('oidc_issuer_rejected');
  return claims;
}

async function importBrokerSigner(privateJwkText) {
  let jwk;
  try { jwk = JSON.parse(privateJwkText); } catch { throw new Error('broker_signer_unconfigured'); }
  if (!jwk || jwk.kty !== 'EC' || jwk.crv !== 'P-256' || !jwk.d) {
    throw new Error('broker_signer_unconfigured');
  }
  const privateKey = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign'],
  );
  const publicJwk = { ...jwk };
  delete publicJwk.d;
  const publicKey = await crypto.subtle.importKey(
    'jwk',
    publicJwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    true,
    ['verify'],
  );
  const raw = new Uint8Array(await crypto.subtle.exportKey('raw', publicKey));
  return {
    privateKey,
    keyId: 'sha256:' + await sha256Hex(raw),
  };
}

function policyFromEnv(env) {
  const policy = {
    audience: EXPECTED_AUDIENCE,
    repository_id: String(env.ALLOWED_REPOSITORY_ID || ''),
    repository_owner_id: String(env.ALLOWED_REPOSITORY_OWNER_ID || ''),
    job_workflow_ref: String(env.ALLOWED_JOB_WORKFLOW_REF || ''),
    job_workflow_sha: String(env.ALLOWED_JOB_WORKFLOW_SHA || ''),
    max_admission_seconds: Number(env.MAX_ADMISSION_SECONDS || 900),
  };
  if (
    !/^\d+$/.test(policy.repository_id)
    || !/^\d+$/.test(policy.repository_owner_id)
    || !policy.job_workflow_ref
    || !/^[0-9a-f]{40}$/.test(policy.job_workflow_sha)
    || !Number.isInteger(policy.max_admission_seconds)
    || policy.max_admission_seconds < 1
    || policy.max_admission_seconds > 900
  ) throw new Error('broker_policy_unconfigured');
  return policy;
}

async function handleRelease(request, env) {
  if (!env.GRANT_LEDGER) throw new Error('grant_ledger_unconfigured');
  if (typeof env.AUTHORITY_PUBLIC_B64 !== 'string' || !env.AUTHORITY_PUBLIC_B64) {
    throw new Error('authority_key_unconfigured');
  }
  if (typeof env.BROKER_SIGNING_PRIVATE_JWK !== 'string' || !env.BROKER_SIGNING_PRIVATE_JWK) {
    throw new Error('broker_signer_unconfigured');
  }

  const auth = String(request.headers.get('authorization') || '');
  if (!auth.startsWith('Bearer ') || auth.length > 16384) throw new Error('oidc_missing');

  const raw = await request.text();
  if (!raw || raw.length > MAX_BODY) throw new Error('request_size_rejected');
  let body;
  try { body = JSON.parse(raw); } catch { throw new Error('request_json_rejected'); }

  const fields = new Set(['worker_key_id','grant']);
  if (!body || Object.keys(body).length !== fields.size || Object.keys(body).some((k) => !fields.has(k))) {
    throw new Error('request_fields_rejected');
  }
  const workerKeyId = String(body.worker_key_id || '');
  if (!/^sha256:[0-9a-f]{64}$/.test(workerKeyId)) throw new Error('worker_key_rejected');

  const policy = policyFromEnv(env);
  const claims = await verifyGithubOidc(auth.slice(7));
  const signer = await importBrokerSigner(env.BROKER_SIGNING_PRIVATE_JWK);

  const grantPayloadBytes = b64ToBytes(String(body.grant?.payload_b64 || ''));
  let grantPayload;
  try { grantPayload = JSON.parse(new TextDecoder().decode(grantPayloadBytes)); }
  catch { throw new Error('grant_payload_rejected'); }

  const expected = {
    grant_id: String(grantPayload.grant_id || ''),
    run_id: String(claims.run_id || ''),
    run_attempt: String(claims.run_attempt || ''),
    harness_sha: String(policy.job_workflow_sha),
    worker_key_id: workerKeyId,
    broker_key_id: signer.keyId,
  };
  const now = Math.floor(Date.now() / 1000);
  const grant = await verifyAuthorityGrant(
    body.grant,
    env.AUTHORITY_PUBLIC_B64,
    expected,
    now,
    policy.max_admission_seconds,
  );

  validateClaims(claims, policy, grant, now);

  const id = env.GRANT_LEDGER.idFromName(String(grant.grant_id));
  const stub = env.GRANT_LEDGER.get(id);
  const consumeResponse = await stub.fetch('https://grant-ledger/consume', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      grant_id: grant.grant_id,
      run_id: grant.run_id,
      run_attempt: grant.run_attempt,
      harness_sha: grant.harness_sha,
      worker_key_id: grant.worker_key_id,
      broker_key_id: grant.broker_key_id,
      admission_not_after: grant.admission_not_after,
    }),
  });
  if (!consumeResponse.ok) throw new Error('grant_consume_rejected');

  const ticket = await signReleaseTicket(
    signer.privateKey,
    signer.keyId,
    grant,
    now,
  );
  return json({ ok: true, ticket }, 200);
}

export class GrantLedger {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/consume') {
      return json({ error: 'not_found' }, 404);
    }
    let body;
    try { body = await request.json(); } catch { return json({ error: 'invalid_json' }, 400); }
    const grantId = String(body?.grant_id || '');
    if (!/^[A-Za-z0-9_-]{16,128}$/.test(grantId)) {
      return json({ error: 'grant_rejected' }, 400);
    }

    const existing = await this.state.storage.get('consumed');
    if (existing) return json({ error: 'grant_already_consumed' }, 409);

    const now = Math.floor(Date.now() / 1000);
    if (Number(body.admission_not_after) <= now) {
      return json({ error: 'grant_expired' }, 410);
    }

    await this.state.storage.put('consumed', {
      grant_id: grantId,
      run_id: String(body.run_id || ''),
      run_attempt: String(body.run_attempt || ''),
      harness_sha: String(body.harness_sha || ''),
      worker_key_id: String(body.worker_key_id || ''),
      broker_key_id: String(body.broker_key_id || ''),
      consumed_at: now,
    });
    return json({ ok: true }, 200);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/healthz') {
      return json({ ok: true, service: 'reference-release-broker-v1' }, 200);
    }
    if (request.method !== 'POST' || url.pathname !== '/v1/release') {
      return json({ error: 'not_found' }, 404);
    }
    try {
      return await handleRelease(request, env);
    } catch (error) {
      const code = String(error?.message || 'rejected');
      if (
        code.includes('unconfigured')
        || code === 'oidc_jwks_unavailable'
      ) return json({ error: 'unavailable' }, 503);
      if (code.startsWith('oidc_')) return json({ error: 'unauthorized' }, 401);
      if (code === 'grant_consume_rejected') return json({ error: 'conflict' }, 409);
      return json({ error: 'rejected' }, 400);
    }
  },
};
