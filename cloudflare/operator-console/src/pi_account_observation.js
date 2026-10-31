// Strict public-side projection of the existing root-owned cc-pi4 account reader.
// This is operator observability, never a broker, strategy, or submit authority.
export const PI_ACCOUNT_SCHEMA = 'commandcenter.pi.ibkr_account_readonly_snapshot.v1';
export const PI_ENVELOPE_SCHEMA = 'mmibkr.pi_account_observation_envelope.v1';
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
        || raw.expected_account_position_count > raw.position_count_all_managed
        || raw.expected_account_open_order_count > raw.open_order_count_all_managed
        || raw.expected_account_recent_execution_count > raw.recent_execution_count_all_managed) {
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
  const keys = ['schema','node_id','command','request_id','result_commit_sha','observation'];
  if (!exactKeys(input, keys) || input.schema !== PI_ENVELOPE_SCHEMA
      || input.node_id !== 'cc-pi4' || input.command !== 'pi.ibkr_account_readonly'
      || typeof input.request_id !== 'string'
      || !/^[A-Za-z0-9._:-]{6,100}$/.test(input.request_id)
      || typeof input.result_commit_sha !== 'string'
      || !/^[a-f0-9]{40}$/.test(input.result_commit_sha)) {
    reject('pi_observation_envelope_rejected');
  }
  return { schema: PI_ENVELOPE_SCHEMA, node_id: 'cc-pi4',
    command: input.command, request_id: input.request_id,
    result_commit_sha: input.result_commit_sha,
    observation: validatePiAccountObservation(input.observation, now) };
}
export function piOperatorView(record, now = Date.now()) {
  const input = validatePiObservationEnvelope(record.envelope, now);
  return { schema: 'mmibkr.pi_account_operator_view.v1', node_id: 'cc-pi4',
    source: 'authenticated_typed_pi_result', observed_at: input.observation.observed_at,
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
