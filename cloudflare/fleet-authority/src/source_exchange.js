const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const EXPECTED_AUDIENCE = 'mmibkr-fleet-authority';

const TRANSITIONAL_RUNTIME_IDENTITY = {
  repository: 'XoticHaze/research-compute-public-',
  ref: 'refs/heads/main',
  workflow_ref:
    'XoticHaze/research-compute-public-/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main',
};

const CANONICAL_RUNTIME_IDENTITY = {
  repository: 'XoticHaze/mm-ibkr-runtime',
  ref: 'refs/heads/main',
  workflow_ref:
    'XoticHaze/mm-ibkr-runtime/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main',
};

const ALLOWED_RUNTIME_IDENTITIES = [
  TRANSITIONAL_RUNTIME_IDENTITY,
  CANONICAL_RUNTIME_IDENTITY,
];

const PRIVATE_REPOSITORY = 'XoticHaze/mm-IBKR';
const PRIVATE_ACCEPTANCE_REF = 'refs/heads/assistant/cloud-signal-history-split-20260918';
const PRIVATE_MAIN_REF = 'refs/heads/main';
const PRIVATE_WORKFLOW_PATH =
  'XoticHaze/mm-IBKR/.github/workflows/mmibkr-cloud-source-producer-r1.yml@';

const B1_REF = 'refs/heads/ibkr-b1-authority-v1';
const B1_WORKFLOW_REF =
  'XoticHaze/research-compute-public-/.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml@refs/heads/ibkr-b1-authority-v1';

const REQUEST_SCHEMA = 'mmibkr-cloud-source-request-v1';
const RESPONSE_SCHEMA = 'mmibkr-cloud-source-x25519-v1';
const HARNESS = 'mmibkr_cloud_source_exchange_v1';

const REQUEST_TTL_MS = 12 * 60 * 60 * 1000;
const MAX_CHUNKS = 2048;
const MAX_CHUNK_CHARS = 100000;
const MAX_MANIFEST_BYTES = 65536;
const ALLOWED_PUBLIC_EVENTS = new Set(['push', 'workflow_dispatch']);
const ALLOWED_PRIVATE_EVENTS = new Set(['push', 'workflow_dispatch', 'schedule']);

const SOURCE_VAULT_PUBLIC_KEY_SCHEMA = 'mmibkr-source-vault-public-key-v1';
const SOURCE_VAULT_UNWRAP_SCHEMA = 'mmibkr-source-vault-unwrap-v2';
const SOURCE_VAULT_RSA_PRIVATE_KEY = 'vault:rsa-oaep:private-jwk';
const SOURCE_VAULT_RSA_PUBLIC_KEY = 'vault:rsa-oaep:public-jwk';
const SOURCE_VAULT_RSA_KEY_ID = 'vault:rsa-oaep:key-id';
const FLEET_PRIVATE_SOURCE_STREAM_SCHEMA = 'mmibkr-fleet-private-source-stream-v1';
const FLEET_PRIVATE_SOURCE_ATTEST_SCHEMA = 'mmibkr-fleet-private-source-attest-v1';
const SOURCE_VAULT_DYNAMIC_APPROVAL_SCHEMA = 'mmibkr-source-vault-dynamic-approval-v1';
const PRIVATE_SOURCE_STREAM_GRANT_TTL_MS = 60 * 60 * 1000;
const APPROVED_PRIVATE_SOURCE_STREAMS = new Set([
  'ca1d97ebfd95a4e23e7be520a4d8a44d49d44251',
]);

/*
 * Exact source snapshots are approved in code only after their encrypted
 * public snapshot + manifest are created and reviewed. Runtime consumers may
 * unwrap a snapshot master key only when BOTH source SHA and manifest digest
 * match an entry here. No public runtime can add approvals dynamically.
 */
const APPROVED_SOURCE_SNAPSHOTS = Object.freeze({
  // '<40-hex-private-source-sha>': Object.freeze({
  //   source_ref: '<same exact source sha>',
  //   manifest_sha256: '<64-hex-public-manifest-sha256>',
  //   archive_sha256: '<64-hex-private-archive-sha256>',
  //   archive_bytes: 123,
  // }),
});

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
    const matchedRuntime = ALLOWED_RUNTIME_IDENTITIES.some(
      (identity) => (
        claims.repository === identity.repository
        && claims.ref === identity.ref
        && claims.workflow_ref === identity.workflow_ref
      ),
    );
    if (
      !matchedRuntime
      || claims.repository_visibility !== 'public'
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
  } else if (role === 'b1_consumer') {
    if (
      claims.repository !== 'XoticHaze/research-compute-public-'
      || claims.repository_visibility !== 'public'
      || claims.ref !== B1_REF
      || claims.workflow_ref !== B1_WORKFLOW_REF
      || !ALLOWED_PUBLIC_EVENTS.has(claims.event_name)
    ) throw new Error('oidc_b1_identity_rejected');
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
    (method === 'POST' && pathname === '/v1/source-vault/unwrap')
    || (method === 'GET' && /^\/v1\/source-vault\/private-archive\/[0-9a-f]{40}$/.test(pathname))
    || (method === 'POST' && pathname === '/v1/source-vault/private-archive/attest')
    ||
    (method === 'POST' && pathname === '/v1/source-exchange/request')
    || (method === 'GET' && /^\/v1\/source-exchange\/response\/\d+$/.test(pathname))
    || (method === 'GET' && /^\/v1\/source-exchange\/response\/\d+\/chunk\/\d+$/.test(pathname))
    || (method === 'POST' && /^\/v1\/source-exchange\/cleanup\/\d+$/.test(pathname))
    || (method === 'POST' && pathname === '/v1/source-exchange/relay/request')
    || (method === 'PUT' && /^\/v1\/source-exchange\/relay\/response\/\d+\/chunk\/\d+$/.test(pathname))
    || (method === 'POST' && /^\/v1\/source-exchange\/relay\/response\/\d+\/manifest$/.test(pathname))
  ) return 'consumer';

  if (
    (method === 'GET' && pathname === '/v1/source-exchange/pending')
    || (method === 'GET' && /^\/v1\/source-exchange\/request\/\d+$/.test(pathname))
    || (method === 'PUT' && /^\/v1\/source-exchange\/response\/\d+\/chunk\/\d+$/.test(pathname))
    || (method === 'POST' && /^\/v1\/source-exchange\/response\/\d+\/manifest$/.test(pathname))
  ) return 'producer';

  if (
    (method === 'GET' && /^\/v1\/source-exchange\/b1\/response\/\d+$/.test(pathname))
    || (method === 'GET' && /^\/v1\/source-exchange\/b1\/response\/\d+\/chunk\/\d+$/.test(pathname))
    || (method === 'POST' && /^\/v1\/source-exchange\/b1\/cleanup\/\d+$/.test(pathname))
  ) return 'b1_consumer';
  return null;
}

export async function handleSourceExchange(request, env) {
  if (!env.SOURCE_EXCHANGE) return json({ error: 'source_exchange_not_configured' }, 503);
  const url = new URL(request.url);

  const id = env.SOURCE_EXCHANGE.idFromName('global');
  const stub = env.SOURCE_EXCHANGE.get(id);

  // The vault public key contains no secret and is intentionally readable
  // without GitHub OIDC. The private key never leaves the Durable Object.
  if (request.method === 'GET' && url.pathname === '/v1/source-vault/public-key') {
    const headers = new Headers();
    headers.set('x-mmibkr-source-role', 'vault_public');
    return stub.fetch(new Request(
      'https://source-exchange.internal/v1/source-vault/public-key',
      { method: 'GET', headers },
    ));
  }

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

  const privateArchiveMatch = url.pathname.match(/^\/v1\/source-vault\/private-archive\/([0-9a-f]{40})$/);
  if (request.method === 'GET' && privateArchiveMatch) {
    const sourceSha = privateArchiveMatch[1];
    if (!APPROVED_PRIVATE_SOURCE_STREAMS.has(sourceSha)) {
      return json({ error: 'private_source_sha_not_approved' }, 403);
    }
    const sourceToken = String(env.MMIBKR_PRIVATE_SOURCE_TOKEN || '');
    if (!sourceToken || sourceToken.length > 512 || /[\r\n\0]/.test(sourceToken)) {
      return json({ error: 'private_source_authority_not_configured' }, 503);
    }

    let upstream;
    try {
      upstream = await fetch(
        `https://api.github.com/repos/${PRIVATE_REPOSITORY}/tarball/${sourceSha}`,
        {
          method: 'GET',
          redirect: 'follow',
          headers: {
            Accept: 'application/vnd.github+json',
            Authorization: `Bearer ${sourceToken}`,
            'X-GitHub-Api-Version': '2026-03-10',
            'User-Agent': 'mmibkr-fleet-private-source-stream-v1',
          },
        },
      );
    } catch {
      return json({ error: 'private_source_fetch_unavailable' }, 502);
    }
    if (!upstream.ok || !upstream.body) {
      return json({ error: 'private_source_fetch_failed', status: upstream.status }, 502);
    }

    const expectedArchiveBytes = Number(upstream.headers.get('content-length') || 0);
    if (
      Number.isFinite(expectedArchiveBytes)
      && (expectedArchiveBytes < 0 || expectedArchiveBytes > 150 * 1024 * 1024)
    ) {
      return json({ error: 'private_source_archive_size_rejected' }, 413);
    }
    const streamId = crypto.randomUUID();
    const grant = await stub.fetch(new Request(
      'https://source-exchange.internal/v1/source-vault/private-archive/grant',
      {
        method: 'POST',
        headers: {
          ...Object.fromEntries(headers.entries()),
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          schema: FLEET_PRIVATE_SOURCE_STREAM_SCHEMA,
          source_sha: sourceSha,
          stream_id: streamId,
          expected_archive_bytes: Number.isFinite(expectedArchiveBytes) ? expectedArchiveBytes : 0,
        }),
      },
    ));
    if (!grant.ok) {
      return json({ error: 'private_source_stream_grant_failed' }, 502);
    }

    const responseHeaders = new Headers();
    responseHeaders.set('content-type', 'application/gzip');
    responseHeaders.set('cache-control', 'no-store');
    responseHeaders.set('content-security-policy', "default-src 'none'");
    responseHeaders.set('x-content-type-options', 'nosniff');
    responseHeaders.set('x-mmibkr-source-sha', sourceSha);
    responseHeaders.set('x-mmibkr-source-stream-id', streamId);
    responseHeaders.set('x-mmibkr-source-transport', 'fleet_authority_oidc_private_archive_stream');
    responseHeaders.set('x-mmibkr-private-source-token-exposed', 'false');
    if (Number.isFinite(expectedArchiveBytes) && expectedArchiveBytes > 0) {
      responseHeaders.set('x-mmibkr-source-archive-bytes', String(expectedArchiveBytes));
    }
    return new Response(upstream.body, { status: 200, headers: responseHeaders });
  }

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
    const grants = await this.ctx.storage.list({ prefix: 'streamgrant:', limit: 100 });
    for (const [key, value] of grants) {
      if (!value || now - Number(value.created_at_ms || 0) <= PRIVATE_SOURCE_STREAM_GRANT_TTL_MS) continue;
      await this.ctx.storage.delete(key);
    }
  }

  _internalRole(request) {
    const role = request.headers.get('x-mmibkr-source-role') || '';
    if (!['consumer', 'producer', 'b1_consumer', 'vault_public'].includes(role)) throw new Error('internal_role_rejected');
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

  async _vaultKeypair() {
    let privateJwk = await this.ctx.storage.get(SOURCE_VAULT_RSA_PRIVATE_KEY);
    let publicJwk = await this.ctx.storage.get(SOURCE_VAULT_RSA_PUBLIC_KEY);
    let keyId = await this.ctx.storage.get(SOURCE_VAULT_RSA_KEY_ID);
    if (privateJwk && publicJwk && keyId) {
      return { privateJwk, publicJwk, keyId };
    }

    const pair = await crypto.subtle.generateKey(
      {
        name: 'RSA-OAEP',
        modulusLength: 3072,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: 'SHA-256',
      },
      true,
      ['encrypt', 'decrypt'],
    );
    privateJwk = await crypto.subtle.exportKey('jwk', pair.privateKey);
    publicJwk = await crypto.subtle.exportKey('jwk', pair.publicKey);
    const publicIdentity = new TextEncoder().encode(
      JSON.stringify({
        kty: publicJwk.kty,
        n: publicJwk.n,
        e: publicJwk.e,
        alg: 'RSA-OAEP-256',
      }),
    );
    keyId = 'sha256:' + await sha256Hex(publicIdentity);
    await this.ctx.storage.put({
      [SOURCE_VAULT_RSA_PRIVATE_KEY]: privateJwk,
      [SOURCE_VAULT_RSA_PUBLIC_KEY]: publicJwk,
      [SOURCE_VAULT_RSA_KEY_ID]: keyId,
    });
    return { privateJwk, publicJwk, keyId };
  }

  async _vaultKeypairSelfTest(privateJwk, publicJwk) {
    const publicKey = await crypto.subtle.importKey(
      'jwk',
      publicJwk,
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      false,
      ['encrypt'],
    );
    const privateKey = await crypto.subtle.importKey(
      'jwk',
      privateJwk,
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      false,
      ['decrypt'],
    );
    const probe = crypto.getRandomValues(new Uint8Array(32));
    const wrapped = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, probe);
    const unwrapped = new Uint8Array(
      await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, privateKey, wrapped),
    );
    if (
      unwrapped.length !== probe.length
      || unwrapped.some((value, index) => value !== probe[index])
    ) {
      throw new Error('vault_keypair_self_test_failed');
    }
    return true;
  }

  async _vaultPublicKeyResponse() {
    const { privateJwk, publicJwk, keyId } = await this._vaultKeypair();
    await this._vaultKeypairSelfTest(privateJwk, publicJwk);
    return {
      schema: SOURCE_VAULT_PUBLIC_KEY_SCHEMA,
      ok: true,
      algorithm: 'RSA-OAEP-256',
      key_id: keyId,
      public_jwk: {
        kty: publicJwk.kty,
        n: publicJwk.n,
        e: publicJwk.e,
        alg: 'RSA-OAEP-256',
        use: 'enc',
        key_ops: ['encrypt'],
        ext: true,
      },
      private_key_exported: false,
      keypair_self_test: true,
      source_approval_is_code_pinned: true,
      snapshot_manifest_approval: 'static_code_pin_or_fleet_attested_first_use_pin',
    };
  }

  async _resolveVaultSnapshotApproval({
    sourceSha,
    manifestSha,
    archiveSha,
    archiveBytes,
  }) {
    const staticApproval = APPROVED_SOURCE_SNAPSHOTS[sourceSha];
    if (staticApproval) {
      if (
        staticApproval.source_ref !== sourceSha
        || staticApproval.manifest_sha256 !== manifestSha
        || staticApproval.archive_sha256 !== archiveSha
        || Number(staticApproval.archive_bytes) !== archiveBytes
      ) {
        throw new Error('vault_source_snapshot_not_approved');
      }
      return {
        ...staticApproval,
        source_sha: sourceSha,
        approval_mode: 'static_code_pin',
      };
    }

    if (!APPROVED_PRIVATE_SOURCE_STREAMS.has(sourceSha)) {
      throw new Error('vault_source_snapshot_not_approved');
    }

    const approvalKey = `vaultapproval:${sourceSha}`;
    const existing = await this.ctx.storage.get(approvalKey);
    if (existing) {
      if (
        existing.source_ref !== sourceSha
        || existing.source_sha !== sourceSha
        || existing.manifest_sha256 !== manifestSha
        || existing.archive_sha256 !== archiveSha
        || Number(existing.archive_bytes) !== archiveBytes
      ) {
        throw new Error('vault_source_snapshot_not_approved');
      }
      return existing;
    }

    const streamAttestation = await this.ctx.storage.get(
      `attest:${sourceSha}:${archiveSha}`,
    );
    if (
      !streamAttestation
      || streamAttestation.schema !== 'mmibkr-cloud-source-fleet-stream-attestation-v1'
      || streamAttestation.source_ref !== sourceSha
      || streamAttestation.source_sha !== sourceSha
      || streamAttestation.plaintext_sha256 !== archiveSha
      || Number(streamAttestation.archive_bytes) !== archiveBytes
      || streamAttestation.source_transport
        !== 'fleet_authority_oidc_private_archive_stream'
    ) {
      throw new Error('vault_source_snapshot_not_approved');
    }

    const approval = {
      schema: SOURCE_VAULT_DYNAMIC_APPROVAL_SCHEMA,
      source_ref: sourceSha,
      source_sha: sourceSha,
      manifest_sha256: manifestSha,
      archive_sha256: archiveSha,
      archive_bytes: archiveBytes,
      approval_mode: 'fleet_attested_first_use_pin',
      private_source_attestation_schema: streamAttestation.schema,
      approved_at: new Date().toISOString(),
    };
    await this.ctx.storage.put(approvalKey, approval);
    return approval;
  }

  async _vaultUnwrap(body, request) {
    const fields = new Set([
      'schema',
      'source_sha',
      'manifest_sha256',
      'archive_sha256',
      'archive_bytes',
      'key_id',
      'sealed_key_b64',
    ]);
    if (
      !body
      || Object.keys(body).length !== fields.size
      || Object.keys(body).some((key) => !fields.has(key))
      || body.schema !== SOURCE_VAULT_UNWRAP_SCHEMA
    ) throw new Error('vault_unwrap_field_set_rejected');

    const sourceSha = String(body.source_sha || '').toLowerCase();
    const manifestSha = String(body.manifest_sha256 || '').toLowerCase();
    const archiveSha = String(body.archive_sha256 || '').toLowerCase();
    const archiveBytes = Number(body.archive_bytes || 0);
    if (!/^[0-9a-f]{40}$/.test(sourceSha)) throw new Error('vault_source_sha_rejected');
    if (!/^[0-9a-f]{64}$/.test(manifestSha)) throw new Error('vault_manifest_sha_rejected');
    if (!/^[0-9a-f]{64}$/.test(archiveSha)) throw new Error('vault_archive_sha_rejected');
    if (!Number.isInteger(archiveBytes) || archiveBytes <= 0 || archiveBytes > 150 * 1024 * 1024) {
      throw new Error('vault_archive_bytes_rejected');
    }
    const approval = await this._resolveVaultSnapshotApproval({
      sourceSha,
      manifestSha,
      archiveSha,
      archiveBytes,
    });

    const { privateJwk, keyId } = await this._vaultKeypair();
    if (String(body.key_id || '') !== keyId) throw new Error('vault_key_id_rejected');

    let sealedKey;
    try {
      sealedKey = b64ToBytes(String(body.sealed_key_b64 || ''));
    } catch {
      throw new Error('vault_sealed_key_rejected');
    }
    if (sealedKey.length < 128 || sealedKey.length > 1024) {
      throw new Error('vault_sealed_key_rejected');
    }

    const privateKey = await crypto.subtle.importKey(
      'jwk',
      privateJwk,
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      false,
      ['decrypt'],
    );
    let masterKey;
    try {
      masterKey = new Uint8Array(await crypto.subtle.decrypt(
        { name: 'RSA-OAEP' },
        privateKey,
        sealedKey,
      ));
    } catch {
      throw new Error('vault_sealed_key_decrypt_rejected');
    }
    if (masterKey.length !== 32) throw new Error('vault_master_key_size_rejected');

    const runtimeIdentity = this._producerIdentity(request);
    const attestation = {
      schema: 'mmibkr-cloud-source-vault-attestation-v1',
      source_ref: approval.source_ref,
      source_sha: sourceSha,
      plaintext_sha256: archiveSha,
      archive_bytes: archiveBytes,
      manifest_sha256: manifestSha,
      producer_identity: runtimeIdentity,
      attested_at: new Date().toISOString(),
      source_transport: 'fleet_authority_exact_sha_encrypted_snapshot_vault',
      snapshot_approval_mode: approval.approval_mode,
    };
    await this.ctx.storage.put(`attest:${sourceSha}:${archiveSha}`, attestation);

    return {
      schema: 'mmibkr-source-vault-unwrapped-key-v2',
      ok: true,
      source_sha: sourceSha,
      manifest_sha256: manifestSha,
      archive_sha256: archiveSha,
      archive_bytes: archiveBytes,
      key_id: keyId,
      master_key_b64: bytesToB64(masterKey),
      approved: true,
      reusable_attestation_stored: true,
      private_source_included: false,
      live_execution_authority: false,
    };
  }

  async fetch(request) {
    await this._cleanupExpired();
    const url = new URL(request.url);
    const role = this._internalRole(request);

    if (request.method === 'GET' && url.pathname === '/v1/source-vault/public-key') {
      if (role !== 'vault_public') return json({ error: 'forbidden' }, 403);
      try {
        return json(await this._vaultPublicKeyResponse(), 200);
      } catch {
        return json({ error: 'source_vault_key_unavailable' }, 503);
      }
    }

    if (request.method === 'POST' && url.pathname === '/v1/source-vault/private-archive/grant') {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      let body;
      try {
        const text = await request.text();
        if (text.length > 4096) return json({ error: 'request_too_large' }, 413);
        body = JSON.parse(text);
      } catch {
        return json({ error: 'invalid_json' }, 400);
      }
      const runId = String(request.headers.get('x-mmibkr-oidc-run-id') || '');
      const sourceSha = String(body?.source_sha || '').toLowerCase();
      const streamId = String(body?.stream_id || '');
      const expectedArchiveBytes = Number(body?.expected_archive_bytes || 0);
      if (
        body?.schema !== FLEET_PRIVATE_SOURCE_STREAM_SCHEMA
        || !/^\d{4,24}$/.test(runId)
        || !APPROVED_PRIVATE_SOURCE_STREAMS.has(sourceSha)
        || !/^[0-9a-f-]{36}$/.test(streamId)
        || !Number.isInteger(expectedArchiveBytes)
        || expectedArchiveBytes < 0
        || expectedArchiveBytes > 150 * 1024 * 1024
      ) {
        return json({ error: 'private_source_stream_grant_rejected' }, 400);
      }
      await this.ctx.storage.put(`streamgrant:${runId}`, {
        schema: FLEET_PRIVATE_SOURCE_STREAM_SCHEMA,
        source_sha: sourceSha,
        stream_id: streamId,
        expected_archive_bytes: expectedArchiveBytes,
        runtime_identity: this._producerIdentity(request),
        created_at_ms: Date.now(),
      });
      return json({
        ok: true,
        source_sha: sourceSha,
        stream_id: streamId,
        expected_archive_bytes: expectedArchiveBytes,
        private_source_token_exposed: false,
      }, 201);
    }

    if (request.method === 'POST' && url.pathname === '/v1/source-vault/private-archive/attest') {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      let body;
      try {
        const text = await request.text();
        if (text.length > 4096) return json({ error: 'request_too_large' }, 413);
        body = JSON.parse(text);
      } catch {
        return json({ error: 'invalid_json' }, 400);
      }
      const runId = String(request.headers.get('x-mmibkr-oidc-run-id') || '');
      const sourceSha = String(body?.source_sha || '').toLowerCase();
      const streamId = String(body?.stream_id || '');
      const archiveSha = String(body?.archive_sha256 || '').toLowerCase();
      const archiveBytes = Number(body?.archive_bytes || 0);
      const grant = await this.ctx.storage.get(`streamgrant:${runId}`);
      if (
        body?.schema !== FLEET_PRIVATE_SOURCE_ATTEST_SCHEMA
        || !grant
        || Date.now() - Number(grant.created_at_ms || 0) > PRIVATE_SOURCE_STREAM_GRANT_TTL_MS
        || grant.source_sha !== sourceSha
        || grant.stream_id !== streamId
        || !APPROVED_PRIVATE_SOURCE_STREAMS.has(sourceSha)
        || !/^[0-9a-f]{64}$/.test(archiveSha)
        || !Number.isInteger(archiveBytes)
        || archiveBytes <= 0
        || archiveBytes > 150 * 1024 * 1024
        || (Number(grant.expected_archive_bytes || 0) > 0
          && Number(grant.expected_archive_bytes) !== archiveBytes)
      ) {
        return json({ error: 'private_source_stream_attestation_rejected' }, 409);
      }
      const attestation = {
        schema: 'mmibkr-cloud-source-fleet-stream-attestation-v1',
        source_ref: sourceSha,
        source_sha: sourceSha,
        plaintext_sha256: archiveSha,
        archive_bytes: archiveBytes,
        producer_identity: grant.runtime_identity,
        stream_id: streamId,
        attested_at: new Date().toISOString(),
        source_transport: 'fleet_authority_oidc_private_archive_stream',
      };
      await this.ctx.storage.put(`attest:${sourceSha}:${archiveSha}`, attestation);
      await this.ctx.storage.delete(`streamgrant:${runId}`);
      return json({
        ok: true,
        source_sha: sourceSha,
        archive_sha256: archiveSha,
        archive_bytes: archiveBytes,
        private_attestation_stored: true,
        source_transport: 'fleet_authority_oidc_private_archive_stream',
        private_source_token_exposed: false,
      }, 200);
    }

    if (request.method === 'POST' && url.pathname === '/v1/source-vault/unwrap') {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const length = Number(request.headers.get('content-length') || 0);
      if (Number.isFinite(length) && length > 16384) return json({ error: 'request_too_large' }, 413);
      let body;
      try {
        const text = await request.text();
        if (text.length > 16384) return json({ error: 'request_too_large' }, 413);
        body = JSON.parse(text);
      } catch {
        return json({ error: 'invalid_json' }, 400);
      }
      try {
        return json(await this._vaultUnwrap(body, request), 200);
      } catch (error) {
        const message = String(error?.message || '');
        if (message === 'vault_source_snapshot_not_approved') {
          return json({ error: 'source_snapshot_not_approved' }, 403);
        }
        const reasonCode = message
          ? (await sha256Hex(new TextEncoder().encode(message))).slice(0, 16)
          : 'none';
        return json({ error: 'source_vault_unwrap_rejected', reason_code: reasonCode }, 400);
      }
    }

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
        const producerIdentity = this._producerIdentity(request);
        const manifest = {
          ...body,
          producer_identity: producerIdentity,
          finalized_at: new Date().toISOString(),
        };
        const attestationKey = `attest:${body.source_sha}:${body.plaintext_sha256}`;
        const attestation = {
          schema: 'mmibkr-cloud-source-private-attestation-v1',
          source_ref: body.source_ref,
          source_sha: body.source_sha,
          plaintext_sha256: body.plaintext_sha256,
          archive_bytes: Number(body.archive_bytes),
          producer_identity: producerIdentity,
          attested_at: new Date().toISOString(),
        };
        await this.ctx.storage.put(attestationKey, attestation);
        await this.ctx.storage.put(`resp:${runId}`, manifest);
        return json({
          ok: true,
          status: 'finalized',
          run_id: runId,
          source_sha: body.source_sha,
          private_attestation_stored: true,
        });
      } catch {
        return json({ error: 'manifest_rejected' }, 400);
      }
    }

    if (request.method === 'POST' && url.pathname === '/v1/source-exchange/relay/request') {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      let body;
      try {
        const text = await request.text();
        if (text.length > 16384) return json({ error: 'request_too_large' }, 413);
        body = JSON.parse(text);
      } catch {
        return json({ error: 'invalid_json' }, 400);
      }
      try {
        const targetRunId = validRunId(body?.target_run_id);
        const sourceRef = validSourceRef(body?.source_ref);
        const sourceSha = String(body?.source_sha || '').toLowerCase();
        const plaintextSha = String(body?.plaintext_sha256 || '').toLowerCase();
        const archiveBytes = Number(body?.archive_bytes || 0);
        const recipientB64 = String(body?.recipient_b64 || '');
        const recipientKeyId = String(body?.recipient_key_id || '');
        if (!/^[0-9a-f]{40}$/.test(sourceSha) || !/^[0-9a-f]{64}$/.test(plaintextSha)) {
          throw new Error('source_identity');
        }
        if (!Number.isInteger(archiveBytes) || archiveBytes <= 0 || archiveBytes > 150 * 1024 * 1024) {
          throw new Error('archive_bytes');
        }
        const recipientRaw = b64ToBytes(recipientB64);
        if (recipientRaw.length !== 32) throw new Error('recipient');
        const calculated = `sha256:${await sha256Hex(recipientRaw)}`;
        if (calculated !== recipientKeyId) throw new Error('recipient_key_id');
        const attestation = await this.ctx.storage.get(`attest:${sourceSha}:${plaintextSha}`);
        if (
          !attestation
          || attestation.source_ref !== sourceRef
          || Number(attestation.archive_bytes) !== archiveBytes
        ) {
          return json({ error: 'private_source_attestation_required' }, 409);
        }
        const relayRequest = {
          schema: 'mmibkr-cloud-source-relay-request-v1',
          target_run_id: targetRunId,
          source_ref: sourceRef,
          source_sha: sourceSha,
          plaintext_sha256: plaintextSha,
          archive_bytes: archiveBytes,
          recipient_b64: recipientB64,
          recipient_key_id: recipientKeyId,
          private_attestation: attestation,
          requested_at: new Date().toISOString(),
        };
        const existing = await this.ctx.storage.get(`relayreq:${targetRunId}`);
        if (existing) {
          const same =
            existing.source_ref === relayRequest.source_ref
            && existing.source_sha === relayRequest.source_sha
            && existing.plaintext_sha256 === relayRequest.plaintext_sha256
            && existing.recipient_key_id === relayRequest.recipient_key_id;
          if (!same) return json({ error: 'relay_request_conflict' }, 409);
        } else {
          await this.ctx.storage.put(`relayreq:${targetRunId}`, relayRequest);
        }
        return json({
          ok: true,
          status: existing ? 'already_requested' : 'requested',
          target_run_id: targetRunId,
          private_attestation_verified: true,
        }, existing ? 200 : 201);
      } catch {
        return json({ error: 'relay_request_rejected' }, 400);
      }
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/relay\/response\/(\d+)\/chunk\/(\d+)$/);
    if (request.method === 'PUT' && match) {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const targetRunId = validRunId(match[1]);
      const index = Number(match[2]);
      if (!Number.isInteger(index) || index < 0 || index >= MAX_CHUNKS) {
        return json({ error: 'chunk_index_rejected' }, 400);
      }
      const relayRequest = await this.ctx.storage.get(`relayreq:${targetRunId}`);
      if (!relayRequest) return json({ error: 'relay_request_not_found' }, 404);
      if (await this.ctx.storage.get(`relayresp:${targetRunId}`)) {
        return json({ error: 'relay_response_already_finalized' }, 409);
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
      await this.ctx.storage.put(`relaychunk:${targetRunId}:${index}`, {
        chars: text.length,
        sha256: digest,
        text,
      });
      return json({ ok: true, target_run_id: targetRunId, index, chars: text.length, sha256: digest });
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/relay\/response\/(\d+)\/manifest$/);
    if (request.method === 'POST' && match) {
      if (role !== 'consumer') return json({ error: 'forbidden' }, 403);
      const targetRunId = validRunId(match[1]);
      const relayRequest = await this.ctx.storage.get(`relayreq:${targetRunId}`);
      if (!relayRequest) return json({ error: 'relay_request_not_found' }, 404);
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
        if (
          String(body.run_id) !== targetRunId
          || body.source_ref !== relayRequest.source_ref
          || body.source_sha !== relayRequest.source_sha
          || body.plaintext_sha256 !== relayRequest.plaintext_sha256
          || Number(body.archive_bytes) !== Number(relayRequest.archive_bytes)
          || body.recipient_key_id !== relayRequest.recipient_key_id
        ) throw new Error('identity');
        const count = Number(body.chunk_count);
        if (!Number.isInteger(count) || count <= 0 || count > MAX_CHUNKS) throw new Error('chunk_count');
        if (!Array.isArray(body.chunks) || body.chunks.length !== count) throw new Error('chunks');
        for (let i = 0; i < count; i += 1) {
          const desc = body.chunks[i];
          const stored = await this.ctx.storage.get(`relaychunk:${targetRunId}:${i}`);
          if (
            !desc
            || Number(desc.index) !== i
            || !stored
            || stored.sha256 !== desc.sha256
            || Number(stored.chars) !== Number(desc.chars)
          ) throw new Error('chunk_missing_or_mismatch');
        }
        const relayManifest = {
          ...body,
          private_attestation: relayRequest.private_attestation,
          relay_identity: this._producerIdentity(request),
          finalized_at: new Date().toISOString(),
        };
        await this.ctx.storage.put(`relayresp:${targetRunId}`, relayManifest);
        return json({
          ok: true,
          status: 'finalized',
          target_run_id: targetRunId,
          private_attestation_verified: true,
        });
      } catch {
        return json({ error: 'relay_manifest_rejected' }, 400);
      }
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/b1\/response\/(\d+)$/);
    if (request.method === 'GET' && match) {
      if (role !== 'b1_consumer') return json({ error: 'forbidden' }, 403);
      const targetRunId = validRunId(match[1]);
      if (String(request.headers.get('x-mmibkr-oidc-run-id') || '') !== targetRunId) {
        return json({ error: 'b1_run_identity_mismatch' }, 403);
      }
      const manifest = await this.ctx.storage.get(`relayresp:${targetRunId}`);
      if (!manifest) return json({ error: 'response_not_ready' }, 404);
      return json({ ok: true, response: manifest });
    }

    match = url.pathname.match(/^\/v1\/source-exchange\/b1\/response\/(\d+)\/chunk\/(\d+)$/);
    if (request.method === 'GET' && match) {
      if (role !== 'b1_consumer') return json({ error: 'forbidden' }, 403);
      const targetRunId = validRunId(match[1]);
      if (String(request.headers.get('x-mmibkr-oidc-run-id') || '') !== targetRunId) {
        return json({ error: 'b1_run_identity_mismatch' }, 403);
      }
      const index = Number(match[2]);
      const chunk = await this.ctx.storage.get(`relaychunk:${targetRunId}:${index}`);
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

    match = url.pathname.match(/^\/v1\/source-exchange\/b1\/cleanup\/(\d+)$/);
    if (request.method === 'POST' && match) {
      if (role !== 'b1_consumer') return json({ error: 'forbidden' }, 403);
      const targetRunId = validRunId(match[1]);
      if (String(request.headers.get('x-mmibkr-oidc-run-id') || '') !== targetRunId) {
        return json({ error: 'b1_run_identity_mismatch' }, 403);
      }
      const manifest = await this.ctx.storage.get(`relayresp:${targetRunId}`);
      const chunkCount = Number(manifest?.chunk_count || 0);
      const keys = [`relayreq:${targetRunId}`, `relayresp:${targetRunId}`];
      for (let i = 0; i < chunkCount; i += 1) keys.push(`relaychunk:${targetRunId}:${i}`);
      await this.ctx.storage.delete(keys);
      return json({ ok: true, status: 'deleted', target_run_id: targetRunId });
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
