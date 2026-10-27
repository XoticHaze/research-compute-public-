import {
  machinePromotionProjection,
  readPromotionState,
  recordPromotionDecision,
  storePromotionCandidates,
  validatePromotionCandidateSnapshot,
} from './promotion_review_state.js';

const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const GITHUB_AUDIENCE = 'mmibkr-operator-console';
const SNAPSHOT_SCHEMA = 'mmibkr.cloud_operator_snapshot.v1';
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024;
const MAX_PROMOTION_BYTES = 2 * 1024 * 1024;

const ALLOWED_PUBLISHERS = Object.freeze([
  Object.freeze({
    repository: 'XoticHaze/research-compute-public-',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/research-compute-public-/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main',
  }),
  Object.freeze({
    repository: 'XoticHaze/research-compute-public-',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/research-compute-public-/.github/workflows/mmibkr-paper-account-hygiene-coordinator-r1.yml@refs/heads/main',
  }),
  Object.freeze({
    repository: 'XoticHaze/mm-ibkr-runtime',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/mm-ibkr-runtime/.github/workflows/mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main',
  }),
]);

const ALLOWED_PROMOTION_PUBLISHERS = Object.freeze([
  Object.freeze({
    repository: 'XoticHaze/research-compute-public-',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/research-compute-public-/.github/workflows/mmibkr-promotion-candidate-publisher-r1.yml@refs/heads/main',
  }),
]);

const ALLOWED_MACHINE_READERS = Object.freeze([
  Object.freeze({
    repository: 'XoticHaze/research-compute-public-',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/research-compute-public-/.github/workflows/mmibkr-operator-snapshot-read-bridge-r1.yml@refs/heads/main',
    repository_visibility: 'public',
  }),
  Object.freeze({
    repository: 'XoticHaze/research-compute-public-',
    ref: 'refs/heads/main',
    workflow_ref:
      'XoticHaze/research-compute-public-/.github/workflows/mmibkr-paper-account-hygiene-coordinator-r1.yml@refs/heads/main',
    repository_visibility: 'public',
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

async function verifyPromotionPublisher(request) {
  const auth = String(request.headers.get('authorization') || '');
  if (!auth.startsWith('Bearer ') || auth.length > 16384) {
    throw new Error('promotion_publisher_unauthorized');
  }
  const callerRunId = String(request.headers.get('x-mmibkr-caller-run-id') || '');
  if (!/^\d{4,24}$/.test(callerRunId)) throw new Error('promotion_publisher_run_id_rejected');

  const claims = await verifyRs256Jwt(auth.slice(7), GITHUB_JWKS);
  if (
    claims.iss !== GITHUB_ISSUER
    || !claimAudience(claims).includes(GITHUB_AUDIENCE)
    || claims.repository_visibility !== 'public'
    || claims.runner_environment !== 'github-hosted'
    || !['push', 'workflow_dispatch'].includes(String(claims.event_name || ''))
    || String(claims.run_id || '') !== callerRunId
    || !ALLOWED_PROMOTION_PUBLISHERS.some((identity) => identityMatches(claims, identity))
  ) {
    throw new Error('promotion_publisher_identity_rejected');
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

async function verifySnapshotReader(request) {
  const auth = String(request.headers.get('authorization') || '');
  if (!auth.startsWith('Bearer ') || auth.length > 16384) {
    throw new Error('reader_unauthorized');
  }
  const callerRunId = String(request.headers.get('x-mmibkr-caller-run-id') || '');
  if (!/^\d{4,24}$/.test(callerRunId)) throw new Error('reader_run_id_rejected');

  const claims = await verifyRs256Jwt(auth.slice(7), GITHUB_JWKS);
  const trustedPublisherReader = Boolean(
    claims.repository_visibility === 'public'
    && ALLOWED_PUBLISHERS.some((identity) => identityMatches(claims, identity))
  );
  const trustedMachineReader = Boolean(
    ALLOWED_MACHINE_READERS.some((identity) => (
      identityMatches(claims, identity)
      && claims.repository_visibility === identity.repository_visibility
    ))
  );
  if (
    claims.iss !== GITHUB_ISSUER
    || !claimAudience(claims).includes(GITHUB_AUDIENCE)
    || claims.runner_environment !== 'github-hosted'
    || !['push', 'workflow_dispatch'].includes(String(claims.event_name || ''))
    || String(claims.run_id || '') !== callerRunId
    || (!trustedPublisherReader && !trustedMachineReader)
  ) {
    throw new Error('reader_identity_rejected');
  }

  return {
    repository: claims.repository,
    repository_visibility: claims.repository_visibility,
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
  if (!allowedEmails.length || !email || !allowedEmails.includes(email)) {
    throw new Error('access_email_rejected');
  }

  return {
    email,
    sub: String(claims.sub || ''),
  };
}

// Browser promotion decisions mutate durable review state. Cloudflare Access
// authenticates the operator but is not, by itself, a cross-site request
// forgery boundary. Only same-origin JSON requests may reach the decision
// writer. Machine OIDC publisher/reader routes remain separate.
export function operatorDecisionRequestIsSameOrigin(request) {
  const url = new URL(request.url);
  const origin = request.headers.get('origin');
  const fetchSite = request.headers.get('sec-fetch-site');
  const contentType = String(request.headers.get('content-type') || '').trim();
  return origin === url.origin
    && (!fetchSite || fetchSite === 'same-origin')
    && /^application\/json(?:\s*;\s*charset\s*=\s*utf-8)?$/i.test(contentType);
}

function snapshotSourceSha(node) {
  return String(node?.runtime?.source_sha || '').trim().toLowerCase();
}

// GitHub publisher jobs can finish out of order. A later HTTP receipt is
// not proof that its underlying boundary snapshot is the latest observation.
function snapshotGeneratedAtMs(node) {
  const value = node?.generated_at_utc;
  if (typeof value !== 'string'
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(value)) {
    return null;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return null;
  // Date.parse normalizes impossible Gregorian dates and 24:00 into a
  // different instant. An invalid producer clock must not advance or roll
  // back the durable operator snapshot ordering authority.
  return new Date(parsed).toISOString().slice(0, 19) === value.slice(0, 19)
    ? parsed : null;
}

// Compare full signed UTC observation precision, not Date.parse's
// millisecond-truncated value. Python producers can emit microseconds;
// lexical UTC seconds + zero-padded nanoseconds preserves exact ordering.
function snapshotGeneratedAtOrderKey(node) {
  if (snapshotGeneratedAtMs(node) === null) return null;
  const value = node?.generated_at_utc;
  const match = typeof value === 'string'
    ? /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$/.exec(value)
    : null;
  if (!match) return null;
  return `${match[1]}.${(match[2] || '').padEnd(9, '0')}`;
}

export function mergeRuntimeProjection(previousRecord, incomingSnapshot) {
  // A duplicate or malformed incoming runtime ID must never be silently
  // collapsed by Map last-wins semantics before the UI sees the snapshot.
  validateSnapshot(incomingSnapshot);
  const previous = previousRecord?.snapshot;
  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) {
    return {
      snapshot: incomingSnapshot,
      runtimeMergeApplied: false,
      previousRuntimeCount: 0,
    };
  }

  // Persisted state may predate the current runtime-ID/privacy validator.
  // Never carry legacy malformed rows through Map last-wins deduplication;
  // keep the independently validated incoming boundary without inheritance.
  try {
    validateSnapshot(previous);
  } catch {
    return {
      snapshot: incomingSnapshot,
      runtimeMergeApplied: false,
      previousRuntimeCount: Array.isArray(previous.runtimes)
        ? previous.runtimes.length : 0,
    };
  }

  const previousSource = snapshotSourceSha(previous);
  const incomingSource = snapshotSourceSha(incomingSnapshot);
  if (!previousSource || !incomingSource || previousSource !== incomingSource) {
    return {
      snapshot: incomingSnapshot,
      runtimeMergeApplied: false,
      previousRuntimeCount: Array.isArray(previous.runtimes)
        ? previous.runtimes.length
        : 0,
    };
  }

  const previousRuntimes = Array.isArray(previous.runtimes) ? previous.runtimes : [];
  const incomingRuntimes = Array.isArray(incomingSnapshot.runtimes)
    ? incomingSnapshot.runtimes
    : [];
  const merged = new Map();
  const incomingIds = new Set(incomingRuntimes.map((row) => String(row?.runtime_id || '').trim()));
  for (const row of previousRuntimes) {
    const runtimeId = String(row?.runtime_id || '').trim();
    if (!runtimeId || incomingIds.has(runtimeId)) continue;
    // A prior source-matched runtime is retained for navigation only. It is
    // NOT a new bar, position, quote, actionable signal or live owner proof.
    // The top-level generated_at_utc belongs to the incoming snapshot.
    merged.set(runtimeId, {
      ...row,
      state: 'unobserved',
      position: null,
      broker_symbol_position: null,
      broker_symbol_position_observed: false,
      position_ownership: {
        // Explicit allowlist: no unknown historical ownership/ledger field may
        // leak into a new boundary's navigation-only projection.
        attributed: false,
        account_wide_position_is_not_strategy_ownership: true,
        // Prior ledger provenance belongs to the earlier observation, not
        // this unobserved boundary. The UI renders provenance_kind even when
        // attributed=false, so leaving it here falsely reports current
        // execution-backed inventory on a navigation-only carried card.
        source: null,
        provenance_kind: null,
        processed_execution_count: null,
        execution_history_present: null,
        reviewed_migration_seed_present: null,
        pre_seed_transition_continuity_proven: null,
        ledger_updated_at_utc: null,
        runtime_updated_at_utc: null,
        attribution_unverified_this_boundary: true,
        carried_from_previous_snapshot: true,
      },
      last_action: 'NOT_OBSERVED',
      // A carried runtime is navigation-only. Never inherit an earlier
      // eligible/execute disposition as if this boundary evaluated it.
      disposition: 'not_due_this_boundary',
      candidate_ready: false,
      broker_action: false,
      // Policy flags and limits can change between boundaries. The prior
      // paper/DCA settings are not a current authority observation either.
      execution_policy: {
        paper_submit_enabled: null,
        live_submit_enabled: null,
        dca_enabled: null,
        max_dca_adds: null,
        max_contracts: null,
        max_shares: null,
        carried_from_previous_snapshot: true,
        policy_unverified_this_boundary: true,
      },
      primary_metric: null,
      conditions: [],
      position_context: null,
      market_context: { features: [], quote: null },
      data_health: {
        // Explicit carry schema: only timestamps remain historical context.
        // Unknown previous health keys must not become fresh eligibility.
        target_bar_close_utc: row?.data_health?.target_bar_close_utc ?? null,
        latest_timestamp: row?.data_health?.latest_timestamp ?? null,
        current: false,
        observed_this_boundary: false,
        not_due_this_boundary: true,
        // Prior positive bar/refresh evidence is historical only. A carried
        // card cannot claim this boundary had a completed/no-new bar.
        bar_close_identity_ok: false,
        no_new_completed_target_bar: false,
        bar_close_gap_sec: null,
        warmup: {},
        freshness: {},
        carried_from_previous_snapshot: true,
      },
    });
  }
  for (const row of incomingRuntimes) {
    const runtimeId = String(row?.runtime_id || '').trim();
    if (runtimeId) merged.set(runtimeId, row);
  }

  const runtimes = Array.from(merged.values());
  const snapshot = validateSnapshot({
    ...incomingSnapshot,
    runtimes,
  });
  return {
    snapshot,
    runtimeMergeApplied: runtimes.length > incomingRuntimes.length,
    previousRuntimeCount: previousRuntimes.length,
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
  const seenRuntimeIds = new Set();
  for (const row of runtimes) {
    const id = row?.runtime_id;
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || typeof id !== 'string' || !id || id !== id.trim()
        || seenRuntimeIds.has(id)) {
      throw new Error('snapshot_runtime_identity_invalid_or_duplicate');
    }
    seenRuntimeIds.add(id);
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
      const incomingSnapshot = validateSnapshot(body.snapshot);
      const incomingGeneratedAt = snapshotGeneratedAtMs(incomingSnapshot);
      const incomingOrderKey = snapshotGeneratedAtOrderKey(incomingSnapshot);
      if (incomingGeneratedAt === null || incomingOrderKey === null || incomingGeneratedAt > Date.now() + 60_000) {
        return json({ error: 'snapshot_generated_at_invalid' }, 400);
      }
      // Compare-and-store must share a Durable Object storage transaction.
      // Independent read/put awaits can otherwise interleave concurrent
      // publishers and allow an older completion to overwrite a newer bar.
      const accepted = await this.ctx.storage.transaction(async (txn) => {
        const previousRecord = await txn.get('latest');
        const previousOrderKey = snapshotGeneratedAtOrderKey(previousRecord?.snapshot);
        if (previousOrderKey !== null && incomingOrderKey < previousOrderKey) {
          return { outOfOrder: true };
        }
        const merged = mergeRuntimeProjection(previousRecord, incomingSnapshot);
        const snapshot = merged.snapshot;
        const transport = body.transport && typeof body.transport === 'object'
          ? body.transport
          : {};
        const record = {
          schema: 'mmibkr.operator_console_state.v1',
          // A timestamp plus collection counts is not a durable record
          // identity: another publisher can replace the value before the
          // independent readback. Generate a unique private write identity.
          write_id: crypto.randomUUID(),
          stored_at_utc: new Date().toISOString(),
          snapshot,
          transport: {
            publisher: transport.publisher || {},
            published_at_utc: transport.published_at_utc || null,
            received_runtime_count: incomingSnapshot.runtimes.length,
            stored_runtime_count: snapshot.runtimes.length,
            runtime_merge_applied: merged.runtimeMergeApplied,
          },
        };
        await txn.put('latest', record);
        return { record, merged, snapshot };
      });
      if (accepted.outOfOrder) return json({ error: 'snapshot_out_of_order' }, 409);
      const { record, merged, snapshot } = accepted;
      const readback = await this.ctx.storage.get('latest');
      const readbackVerified = Boolean(
        readback
        && readback.schema === record.schema
        && readback.stored_at_utc === record.stored_at_utc
        && typeof record.write_id === 'string'
        && readback.write_id === record.write_id
        && readback.snapshot?.schema === snapshot.schema
        && Array.isArray(readback.snapshot?.runtimes)
        && readback.snapshot.runtimes.length === snapshot.runtimes.length
        && Array.isArray(readback.snapshot?.positions)
        && readback.snapshot.positions.length === snapshot.positions.length
      );
      if (!readbackVerified) {
        return json({ error: 'operator_snapshot_readback_failed' }, 502);
      }
      return json({
        ok: true,
        stored_at_utc: record.stored_at_utc,
        durable_readback_verified: true,
        received_runtime_count: incomingSnapshot.runtimes.length,
        runtime_count: snapshot.runtimes.length,
        previous_runtime_count: merged.previousRuntimeCount,
        runtime_merge_applied: merged.runtimeMergeApplied,
      }, 201);
    }

    if (request.method === 'GET' && url.pathname === '/latest') {
      const record = await this.ctx.storage.get('latest');
      if (!record) return json({ error: 'operator_snapshot_not_available' }, 404);
      return json(record, 200);
    }

    if (request.method === 'POST' && url.pathname === '/promotion/candidates') {
      const body = await request.json();
      try {
        const receipt = await storePromotionCandidates(
          this.ctx.storage,
          body.snapshot,
          body.publisher || {},
        );
        return json(receipt, 201);
      } catch (error) {
        return json({
          error: 'promotion_candidates_rejected',
          reason: String(error?.message || 'invalid'),
        }, 400);
      }
    }

    if (request.method === 'GET' && url.pathname === '/promotion/latest') {
      return json(await readPromotionState(this.ctx.storage), 200);
    }

    if (request.method === 'POST' && url.pathname === '/promotion/decision') {
      const body = await request.json();
      try {
        const receipt = await recordPromotionDecision(
          this.ctx.storage,
          body.decision,
          body.operator || {},
        );
        return json(receipt, 201);
      } catch (error) {
        return json({
          error: 'promotion_decision_rejected',
          reason: String(error?.message || 'invalid'),
        }, 409);
      }
    }

    return json({ error: 'not_found' }, 404);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

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
      if (stored.status === 409) return json({ error: 'snapshot_out_of_order' }, 409);
      if (!stored.ok) return json({ error: 'snapshot_store_failed' }, 502);
      const receipt = await stored.json();
      if (receipt.durable_readback_verified !== true) {
        return json({ error: 'snapshot_readback_unverified' }, 502);
      }
      return json({
        ok: true,
        schema: 'mmibkr.operator_console_publish_receipt.v1',
        stored_at_utc: receipt.stored_at_utc,
        source_sha: snapshot?.runtime?.source_sha || null,
        received_runtime_count: receipt.received_runtime_count,
        runtime_count: receipt.received_runtime_count,
        stored_runtime_count: receipt.runtime_count,
        previous_runtime_count: receipt.previous_runtime_count,
        runtime_merge_applied: receipt.runtime_merge_applied === true,
        positions_count: snapshot.positions.length,
        durable_readback_verified: true,
        credentials_included: false,
        tokens_included: false,
        broker_mutation_authority: false,
        live_execution_allowed: false,
      }, 201);
    }

    if (request.method === 'POST' && url.pathname === '/v1/promotion-candidates') {
      const length = Number(request.headers.get('content-length') || 0);
      if (Number.isFinite(length) && length > MAX_PROMOTION_BYTES) {
        return json({ error: 'promotion_payload_too_large' }, 413);
      }

      let publisher;
      try {
        publisher = await verifyPromotionPublisher(request);
      } catch {
        return json({ error: 'unauthorized' }, 401);
      }

      let snapshot;
      try {
        const raw = await request.text();
        if (new TextEncoder().encode(raw).length > MAX_PROMOTION_BYTES) {
          return json({ error: 'promotion_payload_too_large' }, 413);
        }
        snapshot = validatePromotionCandidateSnapshot(JSON.parse(raw));
      } catch (error) {
        return json({
          error: 'promotion_candidates_rejected',
          reason: String(error?.message || 'invalid'),
        }, 400);
      }

      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/promotion/candidates', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ snapshot, publisher }),
        }),
      );
      if (!stored.ok) return stored;
      const receipt = await stored.json();
      return json({
        ...receipt,
        private_source_included: false,
        broker_mutation_authority: false,
        live_execution_allowed: false,
      }, 201);
    }

    if (request.method === 'GET' && url.pathname === '/v1/promotion-review-read') {
      try {
        await verifySnapshotReader(request);
      } catch {
        return json({ error: 'unauthorized' }, 401);
      }
      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/promotion/latest'),
      );
      if (!stored.ok) return stored;
      return json(machinePromotionProjection(await stored.json()), 200);
    }

    if (request.method === 'GET' && url.pathname === '/v1/operator-snapshot-read') {
      let reader;
      try {
        reader = await verifySnapshotReader(request);
      } catch {
        return json({ error: 'unauthorized' }, 401);
      }

      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/latest'),
      );
      if (!stored.ok) return stored;

      const record = await stored.json();
      let snapshot;
      try {
        snapshot = validateSnapshot(record.snapshot);
      } catch {
        return json({ error: 'operator_snapshot_state_invalid' }, 502);
      }

      return json({
        ok: true,
        schema: 'mmibkr.operator_console_machine_read.v1',
        stored_at_utc: record.stored_at_utc || null,
        snapshot,
        reader: {
          repository: reader.repository,
          repository_visibility: reader.repository_visibility,
          workflow_ref: reader.workflow_ref,
          run_id: reader.run_id,
        },
        broker_mutation_authority: false,
        live_execution_allowed: false,
      }, 200);
    }

    let accessIdentity;
    try {
      accessIdentity = await verifyAccess(request, env);
    } catch {
      return json({ error: 'access_denied' }, 403);
    }

    // This dedicated Access-locked host is the operator console, not the
    // full MM backend. React's generic '/' route targets unsupported Markets.
    if (request.method === 'GET' && url.pathname === '/') {
      return new Response(null, {
        status: 302,
        headers: { location: '/bot-console', 'cache-control': 'private, no-store' },
      });
    }

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

    if (request.method === 'GET' && url.pathname === '/api/promotion-review') {
      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/promotion/latest'),
      );
      return stored;
    }

    if (request.method === 'POST' && url.pathname === '/api/promotion-review/decision') {
      if (!operatorDecisionRequestIsSameOrigin(request)) {
        return json({ error: 'operator_mutation_origin_rejected' }, 403);
      }
      let decision;
      try {
        const raw = await request.text();
        if (new TextEncoder().encode(raw).length > 64 * 1024) {
          return json({ error: 'promotion_decision_too_large' }, 413);
        }
        decision = JSON.parse(raw);
      } catch {
        return json({ error: 'invalid_json' }, 400);
      }
      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/promotion/decision', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ decision, operator: accessIdentity }),
        }),
      );
      return stored;
    }

    if (request.method === 'GET' && url.pathname === '/api/operator-snapshot') {
      const stored = await stateStub(env).fetch(
        new Request('https://operator-state.internal/latest'),
      );
      if (!stored.ok) return stored;
      const record = await stored.json();
      let snapshot;
      try {
        snapshot = validateSnapshot(record.snapshot);
      } catch {
        return json({ error: 'operator_snapshot_state_invalid' }, 502);
      }
      return json(snapshot, 200);
    }

    // This Worker only exposes the explicitly admitted read-only/operator APIs.
    // Never return SPA HTML with HTTP 200 for an unsupported MM backend API.
    if (url.pathname === '/api' || url.pathname.startsWith('/api/')
        || url.pathname === '/v1' || url.pathname.startsWith('/v1/')) {
      return json({ error: 'operator_api_not_supported' }, 404);
    }

    if (!env.ASSETS) return json({ error: 'static_assets_not_deployed' }, 503);
    return secureAssetResponse(await env.ASSETS.fetch(request));
  },
};
