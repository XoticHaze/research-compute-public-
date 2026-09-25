const SCHEMA = 'reference-release-ticket-v1';
const ISSUER = 'independent-release-broker-v1';
const SIGNATURE_FORMAT = 'ecdsa-p256-sha256-p1363';

function bytesToB64(bytes) {
  let out = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    out += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(out);
}

function utf8(text) {
  return new TextEncoder().encode(text);
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

function callerIdentity(claims) {
  return {
    repository_id: String(claims.repository_id || ''),
    repository_owner_id: String(claims.repository_owner_id || ''),
    repository_visibility: String(claims.repository_visibility || ''),
    ref: String(claims.ref || ''),
    event_name: String(claims.event_name || ''),
    run_id: String(claims.run_id || ''),
    run_attempt: String(claims.run_attempt || ''),
  };
}

async function callerIdentitySha256(claims) {
  return sha256Hex(utf8(canonical(callerIdentity(claims))));
}

async function validateClaims(claims, policy, grant, nowSeconds) {
  const required = [
    'iss','aud','repository_id','repository_owner_id','repository_visibility',
    'ref','event_name','job_workflow_ref','job_workflow_sha','run_id','run_attempt',
    'runner_environment','iat','nbf','exp',
  ];
  for (const key of required) {
    if (claims[key] === undefined || claims[key] === null || claims[key] === '') {
      throw new Error('oidc_claim_missing');
    }
  }
  if (claims.iss !== 'https://token.actions.githubusercontent.com') throw new Error('oidc_issuer_rejected');
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud.includes(policy.audience)) throw new Error('oidc_audience_rejected');
  if (claims.job_workflow_ref !== policy.job_workflow_ref) throw new Error('oidc_harness_ref_rejected');
  if (claims.job_workflow_sha !== policy.job_workflow_sha) throw new Error('oidc_harness_sha_rejected');
  if (claims.runner_environment !== 'github-hosted') throw new Error('oidc_runner_rejected');
  if (String(claims.run_id) !== String(grant.run_id)) throw new Error('oidc_run_rejected');
  if (String(claims.run_attempt) !== String(grant.run_attempt)) throw new Error('oidc_attempt_rejected');

  const iat = Number(claims.iat);
  const nbf = Number(claims.nbf);
  const exp = Number(claims.exp);
  const skew = 30;
  if (![iat, nbf, exp].every(Number.isFinite)) throw new Error('oidc_time_invalid');
  if (iat > nowSeconds + skew || nbf > nowSeconds + skew || exp < nowSeconds - skew) {
    throw new Error('oidc_time_rejected');
  }
  if (exp - iat > 600) throw new Error('oidc_lifetime_rejected');

  if (String(grant.harness_sha) !== String(policy.job_workflow_sha)) throw new Error('grant_harness_rejected');
  const identityDigest = await callerIdentitySha256(claims);
  if (String(grant.identity_sha256) !== identityDigest) throw new Error('grant_identity_rejected');
  if (!String(grant.worker_key_id).match(/^sha256:[0-9a-f]{64}$/)) throw new Error('grant_worker_key_rejected');
  if (!String(grant.grant_id || '').match(/^[A-Za-z0-9_-]{16,128}$/)) throw new Error('grant_id_rejected');
  const admission = Number(grant.admission_not_after);
  if (!Number.isFinite(admission) || admission <= nowSeconds) throw new Error('grant_expired');
  if (admission - nowSeconds > Number(policy.max_admission_seconds || 900)) throw new Error('grant_ttl_too_long');
}

async function generateSigningKeypair() {
  const pair = await crypto.subtle.generateKey(
    { name: 'ECDSA', namedCurve: 'P-256' },
    true,
    ['sign', 'verify'],
  );
  const publicRaw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return {
    privateKey: pair.privateKey,
    publicKey: pair.publicKey,
    publicRaw,
    publicB64: bytesToB64(publicRaw),
    keyId: 'sha256:' + await sha256Hex(publicRaw),
  };
}

async function signReleaseTicket(privateKey, signerKeyId, grant, nowSeconds) {
  const payload = {
    schema: SCHEMA,
    issuer: ISSUER,
    grant_id: String(grant.grant_id),
    run_id: String(grant.run_id),
    run_attempt: String(grant.run_attempt),
    harness_sha: String(grant.harness_sha),
    worker_key_id: String(grant.worker_key_id),
    issued_at: Number(nowSeconds),
    admission_not_after: Number(grant.admission_not_after),
  };
  const payloadBytes = utf8(canonical(payload));
  const signature = new Uint8Array(await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    privateKey,
    payloadBytes,
  ));
  if (signature.length !== 64) throw new Error('signature_format_unexpected');
  return {
    payload_b64: bytesToB64(payloadBytes),
    signature_b64: bytesToB64(signature),
    signer_key_id: signerKeyId,
    signature_format: SIGNATURE_FORMAT,
  };
}

export {
  callerIdentity,
  callerIdentitySha256,
  validateClaims,
  generateSigningKeypair,
  signReleaseTicket,
};
