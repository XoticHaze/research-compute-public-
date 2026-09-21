const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const GITHUB_AUDIENCE = 'mmibkr-operator-console';
const SNAPSHOT_SCHEMA = 'mmibkr.cloud_operator_snapshot.v1';
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024;

const ALLOWED_PUBLISHERS = Object.freeze([
  Object.freeze({
    repository: 'XoticHaze/research-compute-public-',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/research-compute-public-/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main',
  }),
  Object.freeze({
    repository: 'XoticHaze/mm-ibkr-runtime',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/mm-ibkr-runtime/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main',
  }),
]);

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'private, no-store',
      'content-security-policy': "default-src 'none'",
      'referrer-policy': 'no-referrer',
      'x-content-type-options': 'nosniff',
      ...extraHeaders,
    },
  });
}

function b64urlToBytes(value) {
  const padded = String(value || '')
    .replace(/-/g, '+')
    .replace(/_/g, '/')
    .padEnd(Math.ceil(String(value || '').length / 4) * 4, '=');
  const raw = atob(padded);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

function decodeJsonSegment(value) {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(value)));
}

async function fetchJwks(url) {
  const response = await fetch(url, {
    headers: { accept: 'application/json' },
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!response.ok) throw new Error('jwks_unavailable');
  const node = await response.json();
  if (!node || !Array.isArray(node.keys)) throw new Error('jwks_invalid');
  return node.keys;
}

async function verifyRs256Jwt(jwt, jwksUrl) {
  const parts = String(jwt || '').split('.');
  if (parts.length !== 3) throw new Error('jwt_invalid');

  let header;
  let claims;
  try {
    header = decodeJsonSegment(parts[0]);
    claims = decodeJsonSegment(parts[1]);
  } catch {
    throw new Error('jwt_invalid');
  }
  if (header.alg !== 'RS256' || typeof header.kid !== 'string' || !header.kid) {
    throw new Error('jwt_header_rejected');
  }

  const keys = await fetchJwks(jwksUrl);
  const jwk = keys.find((key) => key && key.kid === header.kid && key.kty === 'RSA');
  if (!jwk) throw new Error('jwt_key_unknown');

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
    new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
  );
  if (!ok) throw new Error('jwt_signature_rejected');

  const now = Math.floor(Date.now() / 1000);
  const skew = 30;
  const exp = Number(claims.exp);
  const iat = Number(claims.iat);
  const nbf = claims.nbf === undefined ? iat : Number(claims.nbf);
  if (!Number.isFinite(exp) || !Number.isFinite(iat) || !Number.isFinite(nbf)) {
    throw new Error('jwt_time_invalid');
  }
  if (exp < now - skew || nbf > now + skew || iat > now + skew) {
    throw new Error('jwt_time_rejected');
  }
  return claims;
}

function claimAudience(claims) {
  return Array.isArray(claims.aud) ? claims.aud : [claims.aud];
}

function identityMatches(claims, expected) {
  return Boolean(
    claims.repository === expected.repository
    && claims.ref === expected.ref
    && claims.workflow_ref === expected.workflow_ref
  );
}

async function verifyPublisher(request) {
  const auth = String(request.headers.get('authorization') || '');
  if (!auth.startsWith('Bearer ') || auth.length > 16384) {
    throw new Error('publisher_unauthorized');
  }
  const callerRunId = String(request.headers.get('x-mmibkr-caller-run-id') || '');
  if (!/^\d{4,24}$/.test(callerRunId)) throw new Error('publisher_run_id_rejected');

  const claims = await verifyRs256Jwt(auth.slice(7), GITHUB_JWKS);
  if (
    claims.iss !== GITHUB_ISSUER
    || !claimAudience(claims).includes(GITHUB_AUDIENCE)
    || claims.repository_visibility !== 'public'
    || claims.runner_environment !== 'github-hosted'
    || !['push', 'workflow_dispatch'].includes(String(claims.event_name || ''))
    || String(claims.run_id || '') !== callerRunId
    || !ALLOWED_PUBLISHERS.some((identity) => identityMatches(claims, identity))
  ) {
    throw new Error('publisher_identity_rejected');
  }

  return {
    repository: claims.repository,
    ref: claims.ref,
    workflow_ref: claims.workflow_ref,
    workflow_sha: claims.workflow_sha,
    event_name: claims.event_name,
    run_id: callerRunId,
    run_attempt: String(claims.run_attempt || ''),
  };
}

function normalizeTeamDomain(value) {
  let domain = String(value || '').trim().replace(/\/$/, '');
  if (!domain) throw new Error('access_team_domain_missing');
  if (!/^https:\/\//i.test(domain)) domain = 'https://' + domain;
  const parsed = new URL(domain);
  if (parsed.protocol !== 'https:' || parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error('access_team_domain_invalid');
  }
  return parsed.origin;
}

async function verifyAccess(request, env) {
  const teamDomain = normalizeTeamDomain(env.ACCESS_TEAM_DOMAIN);
  const audience = String(env.ACCESS_AUD || '').trim();
  if (!audience || audience.length > 512) throw new Error('access_audience_missing');

  const token = String(request.headers.get('cf-access-jwt-assertion') || '');
  if (!token || token.length > 16384) throw new Error('access_token_missing');

  const claims = await verifyRs256Jwt(
    token,
    teamDomain + '/cdn-cgi/access/certs',
  );
  if (
    claims.iss !== teamDomain
    || !claimAudience(claims).includes(audience)
  ) {
    throw new Error('access_identity_rejected');
  }

  const email = String(claims.email || '').trim().toLowerCase();
  const allowedEmails = String(env.ACCESS_ALLOWED_EMAILS || '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  if (allowedEmails.length && !allowedEmails.includes(email)) {
    throw new Error('access_email_rejected');
  }

  return {
    email,
    sub: String(claims.sub || ''),
  };
}

function validateSnapshot(node) {
  if (!node || typeof node !== 'object' || Array.isArray(node)) {
    throw new Error('snapshot_object_required');
  }
  if (node.schema !== SNAPSHOT_SCHEMA) throw new Error('snapshot_schema_rejected');
  if (node.mode !== 'paper' || node.live_enabled !== false) {
    throw new Error('snapshot_paper_only_required');
  }

  const privacy = node.privacy && typeof node.privacy === 'object' ? node.privacy : {};
  const authority = node.authority && typeof node.authority === 'object' ? node.authority : {};
  if (
    privacy.private_operator_state !== true
    || privacy.account_identifiers_included !== false
    || privacy.credentials_included !== false
    || privacy.tokens_included !== false
    || privacy.private_source_included !== false
    || privacy.execution_authority_included !== false
  ) {
    throw new Error('snapshot_privacy_contract_rejected');
  }
  if (
    authority.presentation_projection_only !== true
    || authority.strategy_authority !== false
    || authority.execution_policy_authority !== false
    || authority.sizing_authority !== false
    || authority.broker_mutation_authority !== false
    || authority.live_execution_allowed !== false
  ) {
    throw new Error('snapshot_authority_contract_rejected');
  }

  const runtimes = Array.isArray(node.runtimes) ? node.runtimes : null;
  const positions = Array.isArray(node.positions) ? node.positions : null;
  if (!runtimes || !positions) throw new Error('snapshot_collection_contract_rejected');
  if (runtimes.length > 100 || positions.length > 500) {
    throw new Error('snapshot_collection_size_rejected');
  }
  return node;
}

function stateStub(env) {
  if (!env.OPERATOR_STATE) throw new Error('operator_state_binding_missing');
  const id = env.OPERATOR_STATE.idFromName('global');
  return env.OPERATOR_STATE.get(id);
}

function secureAssetResponse(response) {
  const headers = new Headers(response.headers);
  headers.set('cache-control', 'private, no-store');
  headers.set('referrer-policy', 'no-referrer');
  headers.set('x-content-type-options', 'nosniff');
  headers.set('x-frame-options', 'DENY');
  headers.set(
    'content-security-policy',
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  );
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export class OperatorState {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/store') {
      const body = await request.json();
      const snapshot = validateSnapshot(body.snapshot);
      const transport = body.transport && typeof body.transport === 'object'
        ? body.transport
        : {};
      const record = {
        schema: 'mmibkr.operator_console_state.v1',
        stored_at_utc: new Date().toISOString(),
        snapshot,
        transport: {
          publisher: transport.publisher || {},
          published_at_utc: transport.published_at_utc || null,
        },
      };
      await this.ctx.storage.put('latest', record);
      return json({ ok: true, stored_at_utc: record.stored_at_utc }, 201);
    }

    if (request.method === 'GET' && url.pathname === '/latest') {
      const record = await this.ctx.storage.get('latest');
      if (!record) return json({ error: 'operator_snapshot_not_available' }, 404);
      return json(record, 200);
    }

    return json({ error: 'not_found' }, 404);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'GET' && url.pathname === '/healthz') {
      return json({
        ok: true,
        service: 'mmibkr-operator-console',
        access_configured: Boolean(env.ACCESS_TEAM_DOMAIN && env.ACCESS_AUD),
        operator_state_configured: Boolean(env.OPERATOR_STATE),
        static_assets_configured: Boolean(env.ASSETS),
        live_execution_allowed: false,
      });
    }

    if (request.method === 'POST' && url.pathname === '/v1/operator-snapshot') {
      const length = Number(request.headers.get('content-length') || 0);
      if (Number.isFinite(length) && length > MAX_SNAPSHOT_BYTES) {
        return json({ error: 'snapshot_too_large' }, 413);
      }

      let publisher;
      try {
        publisher = await verifyPublisher(request);
      } catch {
        return json({ error: 'unauthorized' }, 401);
      }

      let text;
      let snapshot;
      try {
        text = await request.text();
        if (new TextEncoder().encode(text).length > MAX_SNAPSHOT_BYTES) {
          return json({ error: 'snapshot_too_large' }, 413);
        }
        snapshot = validateSnapshot(JSON.parse(text));
      } catch (error) {
        return json({
          error: 'snapshot_rejected',
          reason: String(error?.message || 'invalid'),
        }, 400);
      }

      const stub = stateStub(env);
      const stored = await stub.fetch(new Request('https://operator-state.internal/store', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          snapshot,
          transport: {
            publisher,
            published_at_utc: new Date().toISOString(),
          },
        }),
      }));
      if (!stored.ok) return json({ error: 'snapshot_store_failed' }, 502);
      const receipt = await stored.json();
      return json({
        ok: true,
        schema: 'mmibkr.operator_console_publish_receipt.v1',
        stored_at_utc: receipt.stored_at_utc,
        source_sha: snapshot?.runtime?.source_sha || null,
        runtime_count: snapshot.runtimes.length,
        positions_count: snapshot.positions.length,
        credentials_included: false,
        tokens_included: false,
        broker_mutation_authority: false,
        live_execution_allowed: false,
      }, 201);
    }

    try {
      await verifyAccess(request, env);
    } catch {
      return json({ error: 'access_denied' }, 403);
    }

    if (request.method === 'GET' && url.pathname === '/api/operator-snapshot') {
      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/latest'),
      );
      if (!stored.ok) return stored;
      const record = await stored.json();
      return json(record.snapshot, 200);
    }

    if (!env.ASSETS) return json({ error: 'static_assets_not_deployed' }, 503);
    return secureAssetResponse(await env.ASSETS.fetch(request));
  },
};
