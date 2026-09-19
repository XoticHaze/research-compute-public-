const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const EXPECTED_AUDIENCE = 'mmibkr-fleet-authority';

const PUBLIC_REPOSITORY = 'XoticHaze/research-compute-public-';
const PUBLIC_REF = 'refs/heads/main';
const PUBLIC_WORKFLOW_REF =
  'XoticHaze/research-compute-public-/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main';

const PRIVATE_REPOSITORY = 'XoticHaze/mm-IBKR';
const PRIVATE_ACCEPTANCE_REF = 'refs/heads/assistant/cloud-signal-history-split-20260918';
const PRIVATE_MAIN_REF = 'refs/heads/main';
const PRIVATE_WORKFLOW_PATH =
  'XoticHaze/mm-IBKR/.github/workflows/mmibkr-cloud-source-producer-r1.yml@';

const REQUEST_SCHEMA = 'mmibkr-cloud-source-request-v1';
const RESPONSE_SCHEMA = 'mmibkr-cloud-source-x25519-v1';
const HARNESS = 'mmibkr_cloud_source_exchange_v1';

const REQUEST_TTL_MS = 12 * 60 * 60 * 1000;
const MAX_CHUNKS = 2048;
const MAX_CHUNK_CHARS = 100000;
const MAX_MANIFEST_BYTES = 65536;
const ALLOWED_PUBLIC_EVENTS = new Set(['push', 'workflow_dispatch']);
const ALLOWED_PRIVATE_EVENTS = new Set(['push', 'workflow_dispatch', 'schedule']);

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

function validRunId(value) {
  const runId = String(value || '');
  if (!/^\d{4,24}$/.test(runId)) throw new Error('run_id_rejected');
  return runId;
}

function validSourceRef(value) {
  const ref = String(value || '').trim();
  if (
    ref === 'main'
    || ref === 'assistant/cloud-signal-history-split-20260918'
    || /^[0-9a-f]{40}$/.test(ref)
  ) return ref;
  throw new Error('source_ref_rejected');
}

async function verifyJwt(jwt, callerRunId) {
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
  const signingInput = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const signature = b64urlToBytes(parts[2]);
  const ok = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    key,
    signature,
    signingInput,
  );
  if (!ok) throw new Error('oidc_signature_rejected');

  const now = Math.floor(Date.now() / 1000);
  const skew = 30;
  const exp = Number(claims.exp);
  const iat = Number(claims.iat);
  const nbf = claims.nbf === undefined ? iat : Number(claims.nbf);
  if (!Number.isFinite(exp) || !Number.isFinite(iat) || !Number.isFinite(nbf)) {
    throw new Error('oidc_time_invalid');
  }
  if (exp < now - skew || nbf > now + skew || iat > now + skew || exp - iat > 600) {
    throw new Error('oidc_time_rejected');
  }
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (claims.iss !== GITHUB_ISSUER || !aud.includes(EXPECTED_AUDIENCE)) {
    throw new Error('oidc_issuer_audience_rejected');
  }
  if (claims.runner_environment !== 'github-hosted') throw new Error('oidc_runner_rejected');
  if (String(claims.run_id || '') !== String(callerRunId)) throw new Error('oidc_run_rejected');
  return claims;
}

export async function verifySourceExchangeOidc(jwt, callerRunId, role) {
  const claims = await verifyJwt(jwt, callerRunId);
  if (role === 'consumer') {
    if (
      claims.repository !== PUBLIC_REPOSITORY
      || claims.repository_visibility !== 'public'
      || claims.ref !== PUBLIC_REF
      || claims.workflow_ref !== PUBLIC_WORKFLOW_REF
      || !ALLOWED_PUBLIC_EVENTS.has(claims.event_name)
    ) throw new Error('oidc_consumer_identity_rejected');
  } else if (role === 'producer') {
    const ref = String(claims.ref || '');
    const workflowRef = String(claims.workflow_ref || '');
    const refAllowed = ref === PRIVATE_ACCEPTANCE_REF || ref === PRIVATE_MAIN_REF;
    const workflowAllowed =
      workflowRef === PRIVATE_WORKFLOW_PATH + PRIVATE_ACCEPTANCE_REF
      || workflowRef === PRIVATE_WORKFLOW_PATH + PRIVATE_MAIN_REF;
    if (
      claims.repository !== PRIVATE_REPOSITORY
      || claims.repository_visibility !== 'private'
      || !refAllowed
      || !workflowAllowed
      || !ALLOWED_PRIVATE_EVENTS.has(claims.event_name)
    ) throw new Error('oidc_producer_identity_rejected');
  } else {
    throw new Error('source_exchange_role_rejected');
  }
  return {
    repository: claims.repository,
    repository_visibility: claims.repository_visibility,
    ref: claims.ref,
    workflow_ref: claims.workflow_ref,
    workflow_sha: claims.workflow_sha,
    event_name: claims.event_name,
    run_id: String(claims.run_id),
    run_attempt: String(claims.run_attempt || ''),
  };
}

function roleForRequest(method, pathname) {
  if (
    (method === 'POST' && pathname === '/v1/source-exchange/request')
    || (method === 'GET' && /^\/v1\/source-exchange\/response\/\d+$/.test(pathname))
    || (method === 'GET' && /^\/v1\/source-exchange\/response\/\d+\/chunk\/\d+$/.test(pathname))
    || (method === 'POST' && /^\/v1\/source-exchange\/cleanup\/\d+$/.test(pathname))
  ) return 'consumer';

  if (
    (method === 'GET' && pathname === '/v1/source-exchange/pending')
    || (method === 'GET' && /^\/v1\/source-exchange\/request\/\d+$/.test(pathname))
    || (method === 'PUT' && /^\/v1\/source-exchange\/response\/\d+\/chunk\/\d+$/.test(pathname))
    || (method === 'POST' && /^\/v1\/source-exchange\/response\/\d+\/manifest$/.test(pathname))
  ) return 'producer';
  return null;
}

export async function handleSourceExchange(request, env) {
  if (!env.SOURCE_EXCHANGE) return json({ error: 'source_exchange_not_configured' }, 503);
  const url = new URL(request.url);
  const role = roleForRequest(request.method, url.pathname);
  if (!role) return json({ error: 'not_found' }, 404);

  const auth = request.headers.get('authorization') || '';
  const callerRunId = request.headers.get('x-mmibkr-caller-run-id') || '';
  if (!auth.startsWith('Bearer ') || auth.length > 16384) {
    return json({ error: 'unauthorized' }, 401);
  }
  let identity;
  try {
    identity = await verifySourceExchangeOidc(auth.slice(7), callerRunId, role);
  } catch {
    return json({ error: 'unauthorized' }, 401);
  }

  const headers = new Headers(request.headers);
  headers.delete('authorization');
  headers.set('x-mmibkr-source-role', role);
  headers.set('x-mmibkr-oidc-repository', identity.repository);
  headers.set('x-mmibkr-oidc-ref', identity.ref);
  headers.set('x-mmibkr-oidc-workflow-ref', identity.workflow_ref);
  headers.set('x-mmibkr-oidc-event', identity.event_name);
  headers.set('x-mmibkr-oidc-run-id', identity.run_id);
  headers.set('x-mmibkr-oidc-run-attempt', identity.run_attempt);

  const id = env.SOURCE_EXCHANGE.idFromName('global');
  const stub = env.SOURCE_EXCHANGE.get(id);
  const internalUrl = 'https://source-exchange.internal' + url.pathname + url.search;
  const init = { method: request.method, headers };
  if (!['GET', 'HEAD'].includes(request.method)) init.body = request.body;
  return stub.fetch(new Request(internalUrl, init));
}

export class SourceExchange {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  async _deleteRun(runId) {
    const manifest = await this.ctx.storage.get(`resp:${runId}`);
    const chunkCount = Number(manifest?.chunk_count || 0);
    const keys = [`req:${runId}`, `resp:${runId}`];
    for (let i = 0; i < chunkCount; i += 1) keys.push(`chunk:${runId}:${i}`);
    await this.ctx.storage.delete(keys);
  }

  async _cleanupExpired() {
    const requests = await this.ctx.storage.list({ prefix: 'req:', limit: 100 });
    const now = Date.now();
    for (const [key, value] of requests) {
      if (!value || now - Number(value.created_at_ms || 0) <= REQUEST_TTL_MS) continue;
      const runId = key.slice(4);
      await this._deleteRun(runId);
    }
  }

  _internalRole(request) {
    const role = request.headers.get('x-mmibkr-source-role') || '';
    if (!['consumer', 'producer'].includes(role)) throw new Error('internal_role_rejected');
    return role;
  }

  _producerIdentity(request) {
    return {
      repository: request.headers.get('x-mmibkr-oidc-repository') || '',
      ref: request.headers.get('x-mmibkr-oidc-ref') || '',
      workflow_ref: request.headers.get('x-mmibkr-oidc-workflow-ref') || '',
      event_name: request.headers.get('x-mmibkr-oidc-event') || '',
      run_id: request.headers.get('x-mmibkr-oidc-run-id') || '',
      run_attempt: request.headers.get('x-mmibkr-oidc-run-attempt') || '',
    };
  }

  async fetch(request) {
    await this._cleanupExpired();
    const url = new URL(request.url);
    const role = this._internalRole(request);

    if (request.method === 'POST' && url.pathname === '/v1/source-exchange/request') {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const length = Number(request.headers.get('content-length') || 0);
      if (Number.isFinite(length) && length > 8192) return json({ error: 'request_too_large' }, 413);
      let body;
      try {
        const text = await request.text();
        if (text.length > 8192) return json({ error: 'request_too_large' }, 413);
        body = JSON.parse(text);
      } catch {
        return json({ error: 'invalid_json' }, 400);
      }
      try {
        if (body?.schema !== REQUEST_SCHEMA) throw new Error('schema');
        const runId = validRunId(body.run_id);
        const sourceRef = validSourceRef(body.source_ref);
        const recipientB64 = String(body.recipient_b64 || '');
        const recipientKeyId = String(body.recipient_key_id || '');
        const recipientRaw = b64ToBytes(recipientB64);
        if (recipientRaw.length !== 32) throw new Error('recipient');
        const calculated = `sha256:${await sha256Hex(recipientRaw)}`;
        if (calculated !== recipientKeyId) throw new Error('recipient_key_id');

        const incoming = {
          schema: REQUEST_SCHEMA,
          run_id: runId,
          source_ref: sourceRef,
          recipient_b64: recipientB64,
          recipient_key_id: recipientKeyId,
          created_at_ms: Date.now(),
          created_at: new Date().toISOString(),
        };
        const key = `req:${runId}`;
        const existing = await this.ctx.storage.get(key);
        if (existing) {
          const same =
            existing.source_ref === incoming.source_ref
            && existing.recipient_b64 === incoming.recipient_b64
            && existing.recipient_key_id === incoming.recipient_key_id;
          if (!same) return json({ error: 'run_request_conflict' }, 409);
          return json({ ok: true, status: 'already_requested', request: existing });
        }
        await this.ctx.storage.put(key, incoming);
        return json({ ok: true, status: 'requested', request: incoming }, 201);
      } catch {
        return json({ error: 'request_rejected' }, 400);
      }
    }

    if (request.method === 'GET' && url.pathname === '/v1/source-exchange/pending') {
      if (role !== 'producer') return json({ error: 'forbidden' }, 403);
      const rows = await this.ctx.storage.list({ prefix: 'req:', limit: 20 });
      const pending = [];
      for (const [, value] of rows) {
        if (!value) continue;
        const response = await this.ctx.storage.get(`resp:${value.run_id}`);
        if (response) continue;
        pending.push({
          run_id: value.run_id,
          source_ref: value.source_ref,
          created_at: value.created_at,
        });
      }
      pending.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
      return json({ ok: true, pending });
    }

    let match = url.pathname.match(/^\/v1\/source-exchange\/request\/(\d+)$/);
    if (request.method === 'GET' && match) {
      if (role !== 'producer') return json({ error: 'forbidden' }, 403);
      const runId = validRunId(match[1]);
      const node = await this.ctx.storage.get(`req:${runId}`);
      if (!node) return json({ error: 'request_not_found' }, 404);
      return json({ ok: true, request: node });
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/response\/(\d+)\/chunk\/(\d+)$/);
    if (request.method === 'PUT' && match) {
      if (role !== 'producer') return json({ error: 'forbidden' }, 403);
      const runId = validRunId(match[1]);
      const index = Number(match[2]);
      if (!Number.isInteger(index) || index < 0 || index >= MAX_CHUNKS) {
        return json({ error: 'chunk_index_rejected' }, 400);
      }
      const req = await this.ctx.storage.get(`req:${runId}`);
      if (!req) return json({ error: 'request_not_found' }, 404);
      if (await this.ctx.storage.get(`resp:${runId}`)) {
        return json({ error: 'response_already_finalized' }, 409);
      }
      const text = await request.text();
      if (!text || text.length > MAX_CHUNK_CHARS || !/^[A-Za-z0-9+/=]+$/.test(text)) {
        return json({ error: 'chunk_rejected' }, 400);
      }
      const digest = await sha256Hex(new TextEncoder().encode(text));
      const expected = String(request.headers.get('x-mmibkr-chunk-sha256') || '');
      if (!/^[0-9a-f]{64}$/.test(expected) || digest !== expected) {
        return json({ error: 'chunk_digest_rejected' }, 400);
      }
      await this.ctx.storage.put(`chunk:${runId}:${index}`, {
        chars: text.length,
        sha256: digest,
        text,
      });
      return json({ ok: true, run_id: runId, index, chars: text.length, sha256: digest });
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/response\/(\d+)\/manifest$/);
    if (request.method === 'POST' && match) {
      if (role !== 'producer') return json({ error: 'forbidden' }, 403);
      const runId = validRunId(match[1]);
      const req = await this.ctx.storage.get(`req:${runId}`);
      if (!req) return json({ error: 'request_not_found' }, 404);
      const raw = await request.text();
      if (raw.length > MAX_MANIFEST_BYTES) return json({ error: 'manifest_too_large' }, 413);
      let body;
      try { body = JSON.parse(raw); } catch { return json({ error: 'invalid_json' }, 400); }
      try {
        const required = new Set([
          'schema', 'run_id', 'harness', 'source_ref', 'source_sha',
          'recipient_key_id', 'sender_public_b64', 'salt_b64', 'nonce_b64',
          'ciphertext_sha256', 'plaintext_sha256', 'archive_bytes',
          'ciphertext_bytes', 'chunk_count', 'chunks',
        ]);
        if (!body || Object.keys(body).length !== required.size || Object.keys(body).some((k) => !required.has(k))) {
          throw new Error('field_set');
        }
        if (body.schema !== RESPONSE_SCHEMA || body.harness !== HARNESS) throw new Error('schema');
        if (String(body.run_id) !== runId || body.source_ref !== req.source_ref) throw new Error('identity');
        if (!/^[0-9a-f]{40}$/.test(String(body.source_sha || ''))) throw new Error('source_sha');
        if (body.recipient_key_id !== req.recipient_key_id) throw new Error('recipient');
        for (const field of ['ciphertext_sha256', 'plaintext_sha256']) {
          if (!/^[0-9a-f]{64}$/.test(String(body[field] || ''))) throw new Error(field);
        }
        const count = Number(body.chunk_count);
        if (!Number.isInteger(count) || count <= 0 || count > MAX_CHUNKS) throw new Error('chunk_count');
        if (!Array.isArray(body.chunks) || body.chunks.length !== count) throw new Error('chunks');
        for (let i = 0; i < count; i += 1) {
          const desc = body.chunks[i];
          if (!desc || Number(desc.index) !== i || !/^[0-9a-f]{64}$/.test(String(desc.sha256 || ''))) {
            throw new Error('chunk_descriptor');
          }
          const stored = await this.ctx.storage.get(`chunk:${runId}:${i}`);
          if (!stored || stored.sha256 !== desc.sha256 || Number(stored.chars) !== Number(desc.chars)) {
            throw new Error('chunk_missing_or_mismatch');
          }
        }
        const manifest = {
          ...body,
          producer_identity: this._producerIdentity(request),
          finalized_at: new Date().toISOString(),
        };
        await this.ctx.storage.put(`resp:${runId}`, manifest);
        return json({ ok: true, status: 'finalized', run_id: runId, source_sha: body.source_sha });
      } catch {
        return json({ error: 'manifest_rejected' }, 400);
      }
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/response\/(\d+)$/);
    if (request.method === 'GET' && match) {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const runId = validRunId(match[1]);
      const manifest = await this.ctx.storage.get(`resp:${runId}`);
      if (!manifest) return json({ error: 'response_not_ready' }, 404);
      return json({ ok: true, response: manifest });
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/response\/(\d+)\/chunk\/(\d+)$/);
    if (request.method === 'GET' && match) {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const runId = validRunId(match[1]);
      const index = Number(match[2]);
      const chunk = await this.ctx.storage.get(`chunk:${runId}:${index}`);
      if (!chunk) return json({ error: 'chunk_not_found' }, 404);
      return new Response(chunk.text, {
        status: 200,
        headers: {
          'content-type': 'text/plain; charset=us-ascii',
          'cache-control': 'no-store',
          'x-content-type-options': 'nosniff',
          'x-mmibkr-chunk-sha256': chunk.sha256,
        },
      });
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/cleanup\/(\d+)$/);
    if (request.method === 'POST' && match) {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const runId = validRunId(match[1]);
      await this._deleteRun(runId);
      return json({ ok: true, status: 'deleted', run_id: runId });
    }

    return json({ error: 'not_found' }, 404);
  }
}
