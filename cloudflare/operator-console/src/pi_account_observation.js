// Strict public-side projection of the existing root-owned cc-pi4 account reader.
// This is operator observability, never a broker, strategy, or submit authority.
export const PI_ACCOUNT_SCHEMA = 'commandcenter.pi.ibkr_account_readonly_snapshot.v1';
export const PI_ENVELOPE_SCHEMA = 'mmibkr.pi_account_observation_envelope.v1';
// A root-approved periodic outbox snapshot is NOT a typed-command ACK.
export const PI_OUTBOX_ENVELOPE_SCHEMA = 'mmibkr.pi_account_observation_envelope.v2';
export const PI_OUTBOX_RECORD_SCHEMA = 'commandcenter.pi.account_observation_outbox.v1';
export const MAX_PI_OBSERVATION_AGE_MS = 420000;
const KEYS = ['schema','node_id','observed_at','read_only','broker_mutation_attempted',
  'historical_fills_complete','canonical_execution_writer_verified','account_numbers_emitted',
  'status','reason','expected_account_matched','managed_account_count',
  'position_count_all_managed','open_order_count_all_managed','recent_execution_count_all_managed',
  'expected_account_position_count','expected_account_open_order_count',
  'expected_account_recent_execution_count','unattributed_record_count',
  'foreign_account_record_count','expected_account_symbol_position_counts',
  'expected_account_symbol_open_order_counts','selected_scope_authority'];
const TOTALS = ['managed_account_count','position_count_all_managed',
  'open_order_count_all_managed','recent_execution_count_all_managed'];
const SCOPED = ['expected_account_position_count','expected_account_open_order_count',
  'expected_account_recent_execution_count','foreign_account_record_count'];
const GROUPS = ['expected_account_symbol_position_counts','expected_account_symbol_open_order_counts'];
const SYMBOLS = ['AMAT','APH','MNQ','OTHER'];
const isObject = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
function reject(code) { throw new Error(code); }
function exactKeys(x, keys) {
  return isObject(x) && Object.keys(x).length === keys.length
    && keys.every((key) => Object.hasOwn(x, key));
}
function boundedCount(x) { return Number.isSafeInteger(x) && x >= 0 && x <= 1000000; }
function groupsValid(x, total) {
  return exactKeys(x, SYMBOLS) && SYMBOLS.every((s) => boundedCount(x[s]))
    && SYMBOLS.reduce((n, s) => n + x[s], 0) === total;
}
function observedMs(raw, now) {
  if (typeof raw !== 'string' || raw.length > 48
      || !/(Z|[+-]\d\d:\d\d)$/.test(raw)) reject('pi_timestamp_unqualified');
  const time = Date.parse(raw);
  if (!Number.isFinite(time) || time > now + 60000
      || time < now - MAX_PI_OBSERVATION_AGE_MS) reject('pi_observation_stale_or_future');
  return time;
}
export function validatePiAccountObservation(raw, now = Date.now()) {
  if (!exactKeys(raw, KEYS)) reject('pi_account_fields_rejected');
  if (raw.schema !== PI_ACCOUNT_SCHEMA || raw.node_id !== 'cc-pi4'
      || raw.read_only !== true || raw.broker_mutation_attempted !== false
      || raw.historical_fills_complete !== false
      || raw.canonical_execution_writer_verified !== false
      || raw.account_numbers_emitted !== false
      || raw.selected_scope_authority !== 'symbol_only_diagnostic_not_strategy_ownership') {
    reject('pi_account_authority_rejected');
  }
  observedMs(raw.observed_at, now);
  if (raw.status === 'readback_complete') {
    if (raw.reason !== null || raw.expected_account_matched !== true
        || ![...TOTALS, ...SCOPED, 'unattributed_record_count'].every((k) => boundedCount(raw[k]))
        || !groupsValid(raw.expected_account_symbol_position_counts, raw.expected_account_position_count)
        || !groupsValid(raw.expected_account_symbol_open_order_counts, raw.expected_account_open_order_count)
        || raw.managed_account_count !== 1
        || raw.unattributed_record_count !== 0
        || raw.foreign_account_record_count !== 0
        || raw.expected_account_position_count !== raw.position_count_all_managed
        || raw.expected_account_open_order_count !== raw.open_order_count_all_managed
        || raw.expected_account_recent_execution_count !== raw.recent_execution_count_all_managed) {
      reject('pi_account_scope_rejected');
    }
  } else if (raw.status === 'readback_complete_unbound') {
    if (raw.reason !== 'EXPECTED_ACCOUNT_NOT_CONFIGURED'
        || raw.expected_account_matched !== null
        || ![...TOTALS, 'unattributed_record_count'].every((k) => boundedCount(raw[k]))
        || [...SCOPED, ...GROUPS].some((k) => raw[k] !== null)) {
      reject('pi_account_unbound_rejected');
    }
  } else if (raw.status === 'blocked') {
    if (raw.expected_account_matched !== null
        || typeof raw.reason !== 'string' || !/^[A-Z][A-Z0-9_]{2,79}$/.test(raw.reason)
        || [...TOTALS, ...SCOPED, ...GROUPS, 'unattributed_record_count'].some((k) => raw[k] !== null)) {
      reject('pi_account_blocked_rejected');
    }
  } else {
    reject('pi_account_status_rejected');
  }
  // Return only fields from the fixed Pi reader, never a caller-supplied extension.
  return Object.fromEntries(KEYS.map((k) => [k, raw[k]]));
}
export function validatePiObservationEnvelope(input, now = Date.now()) {
  const typedKeys = ['schema','node_id','command','request_id','result_commit_sha','observation'];
  const outboxKeys = ['schema','node_id','producer_kind','observation_id',
    'source_path','result_commit_sha','record'];
  if (!isObject(input) || input.node_id !== 'cc-pi4'
      || typeof input.result_commit_sha !== 'string'
      || !/^[a-f0-9]{40}$/.test(input.result_commit_sha)) {
    reject('pi_observation_envelope_rejected');
  }
  if (input.schema === PI_ENVELOPE_SCHEMA) {
    if (!exactKeys(input, typedKeys) || input.command !== 'pi.ibkr_account_readonly'
        || typeof input.request_id !== 'string'
        || !/^[A-Za-z0-9._:-]{6,100}$/.test(input.request_id)) {
      reject('pi_observation_typed_identity_rejected');
    }
    return { schema: PI_ENVELOPE_SCHEMA, node_id: 'cc-pi4',
      command: input.command, request_id: input.request_id,
      result_commit_sha: input.result_commit_sha,
      observation: validatePiAccountObservation(input.observation, now) };
  }
  if (input.schema === PI_OUTBOX_ENVELOPE_SCHEMA) {
    // This verifies bounded shape only. Source authentication, exact Git commit
    // provenance, root approval and issuer replay MUST be independently verified
    // before a trusted OIDC publisher invokes the existing ingestion endpoint.
    const producer = 'root_approved_existing_agent_snapshot_reader';
    const recordKeys = ['schema','node_id','observation_id','observed_at',
      'snapshot_sha256','snapshot','producer','read_only','broker_mutation_attempted'];
    if (!exactKeys(input, outboxKeys)
        || input.producer_kind !== producer
        || typeof input.observation_id !== 'string'
        || !/^piobs-\d{14}-[a-f0-9]{16}$/.test(input.observation_id)
        || input.source_path !== `pi-node/observations/${input.observation_id}.json`
        || !exactKeys(input.record, recordKeys)
        || input.record.schema !== PI_OUTBOX_RECORD_SCHEMA
        || input.record.node_id !== 'cc-pi4'
        || input.record.observation_id !== input.observation_id
        || input.record.producer !== producer
        || input.record.read_only !== true
        || input.record.broker_mutation_attempted !== false
        || typeof input.record.snapshot_sha256 !== 'string'
        || !/^[a-f0-9]{64}$/.test(input.record.snapshot_sha256)
        || !input.record.observation_id.endsWith(input.record.snapshot_sha256.slice(0,16))) {
      reject('pi_observation_outbox_identity_rejected');
    }
    const clean = validatePiAccountObservation(input.record.snapshot, now);
    if (input.record.observed_at !== clean.observed_at) {
      reject('pi_observation_outbox_timestamp_rejected');
    }
    return { schema: PI_OUTBOX_ENVELOPE_SCHEMA, node_id:'cc-pi4',
      producer_kind:producer, observation_id:input.observation_id,
      source_path:input.source_path, result_commit_sha:input.result_commit_sha,
      observation:clean };
  }
  reject('pi_observation_envelope_kind_rejected');
}

// The internal replay ledger key is NOT a fabricated typed request ID.
// The two genuine producer namespaces cannot impersonate one another.
export function piReplayIdentity(envelope) {
  if (envelope?.schema === PI_ENVELOPE_SCHEMA) return envelope.request_id;
  if (envelope?.schema === PI_OUTBOX_ENVELOPE_SCHEMA) {
    return `outbox:${envelope.observation_id}`;
  }
  reject('pi_replay_envelope_kind_rejected');
}

// A matching self-reported digest is necessary but NOT authentication of the
// private Git commit or root. The independently admitted publisher owns those
// proofs, and this check rejects bitwise-inconsistent payloads at Worker ingress.
function canonicalSnapshot(value) {
  if (Array.isArray(value)) return '[' + value.map(canonicalSnapshot).join(',') + ']';
  if (isObject(value)) return '{' + Object.keys(value).sort()
    .map((k) => JSON.stringify(k) + ':' + canonicalSnapshot(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
export async function verifyPiOutboxSnapshotDigest(raw) {
  if (raw?.schema !== PI_OUTBOX_ENVELOPE_SCHEMA) return true;
  const record = raw?.record;
  if (!record || !isObject(record.snapshot)
      || typeof record.snapshot_sha256 !== 'string') {
    reject('pi_outbox_snapshot_digest_rejected');
  }
  const bytes = new TextEncoder().encode(canonicalSnapshot(record.snapshot));
  const hashed = await crypto.subtle.digest('SHA-256', bytes);
  const actual = [...new Uint8Array(hashed)]
    .map((b) => b.toString(16).padStart(2, '0')).join('');
  if (actual !== record.snapshot_sha256) reject('pi_outbox_snapshot_digest_rejected');
  return true;
}

export function piOperatorView(record, now = Date.now()) {
  const input = validatePiObservationEnvelope(record.envelope, now);
  return { schema: 'mmibkr.pi_account_operator_view.v1', node_id: 'cc-pi4',
    source: input.schema === PI_ENVELOPE_SCHEMA
      ? 'authenticated_typed_pi_result' : 'root_observation_outbox',
    observed_at: input.observation.observed_at,
    status: input.observation.status, reason: input.observation.reason,
    account_matched: input.observation.expected_account_matched,
    managed_account_count: input.observation.managed_account_count,
    position_count: input.observation.expected_account_position_count,
    open_order_count: input.observation.expected_account_open_order_count,
    recent_execution_count: input.observation.expected_account_recent_execution_count,
    symbol_position_counts: input.observation.expected_account_symbol_position_counts,
    symbol_open_order_counts: input.observation.expected_account_symbol_open_order_counts,
    git_receipt_sha: input.result_commit_sha,
    stored_at_utc: record.stored_at_utc,
    broker_mutation_authority: false, strategy_authority: false,
    live_execution_allowed: false, historical_fills_complete: false,
    canonical_execution_writer_verified: false };
}
