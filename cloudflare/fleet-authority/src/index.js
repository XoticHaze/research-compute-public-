const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const EXPECTED_AUDIENCE = 'mmibkr-fleet-authority';
const EXPECTED_REPOSITORY = 'XoticHaze/research-compute-public-';
const EXPECTED_AUTHORITY = 'ibkr-paper-readonly';
const ALLOWED_REF = 'refs/heads/ibkr-b1-authority-v1';
const ALLOWED_EVENT = 'push';
const ALLOWED_WORKFLOW_REF = 'XoticHaze/research-compute-public-/.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml@refs/heads/ibkr-b1-authority-v1';
const ALLOWED_WORKFLOW_SHA = '4c1cd43c0bbb21d9ae2408ba7cfa9f4e6461adba';
const REQUEST_SCHEMA = 'mmibkr-fleet-authority-seal-request-v1';
const ENVELOPE_SCHEMA = 'mmibkr-ibkr-readonly-gateway-env-x25519-hkdf-aesgcm-v1';

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

function bytesToB64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

async function sha256Hex(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return [...digest].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function validateSecretValue(value, name) {
  const text = typeof value === 'string' ? value : '';
  if (!text || text.length > 512 || /[\r\n\0]/.test(text)) throw new Error(`${name}_rejected`);
  return text;
}

async function verifyGithubOidc(jwt, requestedRunId) {
  const parts = jwt.split('.');
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
  const jwk = Array.isArray(jwks.keys) ? jwks.keys.find((k) => k.kid === header.kid && k.kty === 'RSA') : null;
  if (!jwk) throw new Error('oidc_key_unknown');

  const key = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  const signingInput = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const signature = b64urlToBytes(parts[2]);
  const signatureOk = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, signature, signingInput);
  if (!signatureOk) throw new Error('oidc_signature_rejected');

  const now = Math.floor(Date.now() / 1000);
  const skew = 30;
  const exp = Number(claims.exp);
  const iat = Number(claims.iat);
  const nbf = claims.nbf === undefined ? iat : Number(claims.nbf);
  if (!Number.isFinite(exp) || !Number.isFinite(iat) || !Number.isFinite(nbf)) throw new Error('oidc_time_invalid');
  if (exp < now - skew || nbf > now + skew || iat > now + skew || exp - iat > 600) throw new Error('oidc_time_rejected');

  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (claims.iss !== GITHUB_ISSUER || !aud.includes(EXPECTED_AUDIENCE)) throw new Error('oidc_issuer_audience_rejected');
  if (claims.repository !== EXPECTED_REPOSITORY) throw new Error('oidc_repository_rejected');
  if (claims.repository_visibility !== 'public') throw new Error('oidc_visibility_rejected');
  if (claims.runner_environment !== 'github-hosted') throw new Error('oidc_runner_rejected');
  if (claims.ref !== ALLOWED_REF) throw new Error('oidc_ref_rejected');
  if (claims.workflow_ref !== ALLOWED_WORKFLOW_REF) throw new Error('oidc_workflow_ref_rejected');
  if (claims.workflow_sha !== ALLOWED_WORKFLOW_SHA) throw new Error('oidc_workflow_sha_rejected');
  if (claims.event_name !== ALLOWED_EVENT) throw new Error('oidc_event_rejected');
  if (String(claims.run_id) !== requestedRunId) throw new Error('oidc_run_rejected');

  return {
    repository: claims.repository,
    ref: claims.ref,
    workflow_ref: claims.workflow_ref,
    workflow_sha: claims.workflow_sha,
    run_id: String(claims.run_id),
    run_attempt: String(claims.run_attempt ?? ''),
  };
}

async function sealIbkrGatewayEnv(body, env, oidc) {
  if (body.schema !== REQUEST_SCHEMA || body.authority !== EXPECTED_AUTHORITY) throw new Error('request_rejected');
  const runId = String(body.run_id ?? '');
  if (!/^\d{4,24}$/.test(runId)) throw new Error('run_id_rejected');

  const recipientB64 = String(body.recipient_b64 ?? '');
  const recipientKeyId = String(body.recipient_key_id ?? '');
  let recipientRaw;
  try {
    recipientRaw = b64ToBytes(recipientB64);
  } catch {
    throw new Error('recipient_rejected');
  }
  if (recipientRaw.length !== 32) throw new Error('recipient_rejected');
  const calculatedKeyId = `sha256:${await sha256Hex(recipientRaw)}`;
  if (recipientKeyId !== calculatedKeyId) throw new Error('recipient_key_id_rejected');

  if (!env.IBKR_PAPER_USERNAME || !env.IBKR_PAPER_PASSWORD) throw new Error('authority_not_configured');
  const userid = validateSecretValue(env.IBKR_PAPER_USERNAME, 'authority_userid');
  const secret = validateSecretValue(env.IBKR_PAPER_PASSWORD, 'authority_secret');

  const recipientKey = await crypto.subtle.importKey('raw', recipientRaw, { name: 'X25519' }, false, []);
  const ephemeral = await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits']);
  const shared = await crypto.subtle.deriveBits(
    { name: 'X25519', public: recipientKey },
    ephemeral.privateKey,
    256,
  );

  const salt = crypto.getRandomValues(new Uint8Array(32));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const aadText = `mmibkr-fleet-authority|${EXPECTED_AUTHORITY}|${runId}|${recipientKeyId}`;
  const aad = new TextEncoder().encode(aadText);

  const hkdfBase = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  const aesKey = await crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt, info: aad },
    hkdfBase,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt'],
  );

  const plaintext = new TextEncoder().encode([
    `TWS_USERID=${userid}`,
    `TWS_PASSWORD=${secret}`,
    'TRADING_MODE=paper',
    'READ_ONLY_API=yes',
    'TWS_ACCEPT_INCOMING=accept',
    'TWOFA_TIMEOUT_ACTION=exit',
    'RELOGIN_AFTER_TWOFA_TIMEOUT=no',
    'SAVE_TWS_SETTINGS=no',
    'ENABLE_VNC=false',
    '',
  ].join('\n'));

  const ciphertext = new Uint8Array(await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: aad, tagLength: 128 },
    aesKey,
    plaintext,
  ));
  const ephemeralPublic = new Uint8Array(await crypto.subtle.exportKey('raw', ephemeral.publicKey));

  return {
    schema: ENVELOPE_SCHEMA,
    authority: EXPECTED_AUTHORITY,
    run_id: runId,
    recipient_key_id: recipientKeyId,
    ephemeral_public_b64: bytesToB64(ephemeralPublic),
    salt_b64: bytesToB64(salt),
    iv_b64: bytesToB64(iv),
    aad_b64: bytesToB64(aad),
    ciphertext_b64: bytesToB64(ciphertext),
    created_at: new Date().toISOString(),
    oidc: {
      repository: oidc.repository,
      ref: oidc.ref,
      workflow_ref: oidc.workflow_ref,
      workflow_sha: oidc.workflow_sha,
      run_id: oidc.run_id,
      run_attempt: oidc.run_attempt,
    },
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'GET' && url.pathname === '/healthz') {
      return json({
        ok: true,
        service: 'mmibkr-fleet-authority',
        authority_configured: Boolean(env.IBKR_PAPER_USERNAME && env.IBKR_PAPER_PASSWORD),
      });
    }

    if (request.method !== 'POST' || url.pathname !== '/v1/authorities/ibkr-paper/seal') {
      return json({ error: 'not_found' }, 404);
    }

    if (!String(request.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) {
      return json({ error: 'unsupported_media_type' }, 415);
    }

    const length = Number(request.headers.get('content-length') || 0);
    if (Number.isFinite(length) && length > 8192) return json({ error: 'request_too_large' }, 413);

    const auth = request.headers.get('authorization') || '';
    if (!auth.startsWith('Bearer ') || auth.length > 16384) return json({ error: 'unauthorized' }, 401);

    let body;
    try {
      const text = await request.text();
      if (text.length > 8192) return json({ error: 'request_too_large' }, 413);
      body = JSON.parse(text);
    } catch {
      return json({ error: 'invalid_json' }, 400);
    }

    try {
      const runId = String(body?.run_id ?? '');
      const oidc = await verifyGithubOidc(auth.slice(7), runId);
      const envelope = await sealIbkrGatewayEnv(body, env, oidc);
      return json(envelope, 200);
    } catch (error) {
      const message = String(error?.message || 'rejected');
      if (message === 'authority_not_configured') return json({ error: message }, 503);
      if (message.startsWith('oidc_')) return json({ error: 'unauthorized' }, 401);
      return json({ error: 'request_rejected' }, 400);
    }
  },
};
