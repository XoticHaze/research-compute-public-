/** Exact-account private Pi money consumer for the incumbent Access-locked operator Worker.
 *
 * No broker/Git read, no order authority, no unverified zero, no account ID in
 * operator responses. A separately admitted Pi root producer signs this exact
 * envelope; this module never authenticates the machine by trusting its body.
 */
export const FINANCE_SCHEMA = 'mmibkr.pi_live_account_private_envelope.v1';
export const ACCOUNT_SCHEMA = 'mmibkr.live_operator_account.v1';
export const FINANCE_DOMAIN = 'MMIBKR-PI-LIVE-ACCOUNT-PRIVATE-PROJECTION-V1\n';
export const FINANCE_MAX_BYTES = 262144;
const MONEY_NAMES = Object.freeze([
  'net_liquidation', 'cash', 'buying_power', 'available_funds',
  'excess_liquidity', 'initial_margin', 'maintenance_margin',
  'equity_with_loan_value', 'day_pnl', 'realized_pnl', 'unrealized_pnl',
]);
const SOURCE_NAMES = ['node_id', 'account_sha256', 'observed_at_utc',
  'cycle_id', 'transport', 'account_scope_verified'];
const SNAPSHOT_NAMES = ['schema', 'mode', 'account', 'positions', 'open_orders',
  'bot', 'risk', 'presentation_only', 'broker_mutation_authority'];
const RISK_NAMES = ['min_remaining_cushion_pct', 'observed_remaining_cushion_pct',
  'pending_order_reservations_verified', 'effective_writer_and_fill_commit_verified',
  'new_exposure_admitted'];
const POSITION_NAMES = ['symbol', 'local_symbol', 'security_type', 'contract_id',
  'quantity', 'avg_cost', 'market_value', 'unrealized_pnl', 'currency', 'ownership'];
const ORDER_NAMES = ['symbol', 'local_symbol', 'security_type', 'contract_id',
  'action', 'quantity', 'remaining_quantity', 'order_type', 'limit_price',
  'status', 'ownership', 'currency'];
const NUMERIC_STRING = /^-?(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,8})?$/;
const HEX64 = /^[a-f0-9]{64}$/;
const HEX_KEY = /^(?:[a-f0-9]{64}|[a-f0-9]{128})$/;
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/;

function fail(code) { throw new Error(code); }
function record(x) {
  return x !== null && typeof x === 'object' && !Array.isArray(x)
    && Object.getPrototypeOf(x) === Object.prototype;
}
function exact(x, names) {
  return record(x) && Object.keys(x).length === names.length
    && names.every((name) => Object.hasOwn(x, name));
}
function hexBytes(v) {
  return Uint8Array.from(v.match(/.{2}/g), pair => parseInt(pair, 16));
}
export function canonicalPrivateJson(x) {
  // The Pi producer uses Python json.dumps(sort_keys=True, separators=(',', ':'),
  // ensure_ascii=False). All accepted keys and values are ASCII and quantities
  // are decimal strings, preventing JS/Python floating-point encodings drifting.
  if (x === null || typeof x === 'string' || typeof x === 'boolean') return JSON.stringify(x);
  if (typeof x === 'number' && Number.isSafeInteger(x)) return JSON.stringify(x);
  if (Array.isArray(x)) return `[${x.map(canonicalPrivateJson).join(',')}]`;
  if (record(x)) return `{${Object.keys(x).sort().map(k =>
    `${JSON.stringify(k)}:${canonicalPrivateJson(x[k])}`).join(',')}}`;
  return fail('pi_financial_canonical_shape_invalid');
}
function timeMs(raw, nowMs) {
  if (typeof raw !== 'string' || !ISO_UTC.test(raw)) fail('pi_financial_time_invalid');
  const ms = Date.parse(raw);
  if (!Number.isFinite(ms) || ms > nowMs + 60000 || ms < nowMs - 420000) {
    fail('pi_financial_stale');
  }
  return ms;
}
function money(item) {
  if (!exact(item, ['value', 'currency', 'status'])) fail('pi_financial_money_shape');
  if (item.status === 'UNVERIFIED') {
    if (item.value !== null || item.currency !== null) fail('pi_financial_unknown_money');
  } else if (item.status === 'OBSERVED') {
    if (typeof item.value !== 'string' || !NUMERIC_STRING.test(item.value)
        || typeof item.currency !== 'string' || !/^[A-Z]{3}$/.test(item.currency)) {
      fail('pi_financial_money_invalid');
    }
  } else fail('pi_financial_money_status');
}
function rows(section, kind) {
  if (!exact(section, ['status', 'count', 'rows']) || !Array.isArray(section.rows)
      || section.rows.length > 300) fail('pi_financial_rows_shape');
  if (section.status === 'UNVERIFIED') {
    if (section.count !== null || section.rows.length !== 0) fail('pi_financial_rows_unknown');
    return;
  }
  if (section.status !== 'OBSERVED' || !Number.isSafeInteger(section.count)
      || section.count !== section.rows.length) fail('pi_financial_rows_count');
  const fields = kind === 'positions' ? POSITION_NAMES : ORDER_NAMES;
  for (const row of section.rows) {
    if (!exact(row, fields) || typeof row.symbol !== 'string'
        || !/^[A-Za-z0-9._/-]{1,28}$/.test(row.symbol)
        || !['BOT_OWNED', 'EXTERNAL', 'UNVERIFIED'].includes(row.ownership)) {
      fail('pi_financial_row_identity');
    }
    for (const [name, value] of Object.entries(row)) {
      if (name === 'symbol' || name === 'ownership' || value === null) continue;
      if (typeof value !== 'string' && (!Number.isSafeInteger(value) || value < 0)) {
        fail('pi_financial_row_field');
      }
      if (typeof value === 'string' && (value.length > 120
          || !/^[\x20-\x7e]*$/.test(value))) fail('pi_financial_row_field');
    }
  }
}
function financeShape(input, expectedHash, nowMs) {
  if (!exact(input, ['schema', 'source', 'snapshot', 'mac_hex'])
      || input.schema !== FINANCE_SCHEMA || !HEX64.test(input.mac_hex)) fail('pi_financial_envelope_invalid');
  const { source, snapshot } = input;
  if (!exact(source, SOURCE_NAMES)
      || source.node_id !== 'cc-pi4'
      || source.account_sha256 !== expectedHash
      || source.transport !== 'authenticated_private_pi_delivery'
      || source.account_scope_verified !== true
      || typeof source.cycle_id !== 'string'
      || !/^[A-Za-z0-9._:-]{8,120}$/.test(source.cycle_id)) fail('pi_financial_source_invalid');
  const observedAtMs = timeMs(source.observed_at_utc, nowMs);
  if (!exact(snapshot, SNAPSHOT_NAMES) || snapshot.schema !== ACCOUNT_SCHEMA
      || snapshot.mode !== 'live' || snapshot.presentation_only !== true
      || snapshot.broker_mutation_authority !== false
      || !exact(snapshot.account, MONEY_NAMES)) fail('pi_financial_snapshot_invalid');
  for (const key of MONEY_NAMES) money(snapshot.account[key]);
  rows(snapshot.positions, 'positions'); rows(snapshot.open_orders, 'open_orders');
  if (!exact(snapshot.bot, ['ownership_state', 'runtimes'])
      || !['BOT_OWNED', 'EXTERNAL', 'UNVERIFIED'].includes(snapshot.bot.ownership_state)
      || !Array.isArray(snapshot.bot.runtimes) || snapshot.bot.runtimes.length) {
    fail('pi_financial_bot_authority');
  }
  if (!exact(snapshot.risk, RISK_NAMES)
      || snapshot.risk.min_remaining_cushion_pct !== 30
      || snapshot.risk.observed_remaining_cushion_pct !== null
      || snapshot.risk.pending_order_reservations_verified !== false
      || snapshot.risk.effective_writer_and_fill_commit_verified !== false
      || snapshot.risk.new_exposure_admitted !== false) fail('pi_financial_risk_authority');
  return observedAtMs;
}
export async function verifyPrivateFinancial(input, env, nowMs = Date.now()) {
  const keyHex = String(env?.PI_LIVE_FINANCE_HMAC_KEY || '');
  const expectedHash = String(env?.PI_LIVE_EXPECTED_ACCOUNT_SHA256 || '');
  if (!HEX_KEY.test(keyHex) || !HEX64.test(expectedHash)) fail('pi_financial_trust_unconfigured');
  if (!Number.isFinite(nowMs)) fail('pi_financial_clock_invalid');
  const observedAtMs = financeShape(input, expectedHash, nowMs);
  // Reject invalid values BEFORE JSON canonicalization. Source ownership and
  // signed money are then authenticated independently of Access machine identity.
  const body = canonicalPrivateJson({source: input.source, snapshot: input.snapshot});
  const message = new TextEncoder().encode(FINANCE_DOMAIN + body);
  const key = await crypto.subtle.importKey('raw', hexBytes(keyHex),
    {name:'HMAC', hash:'SHA-256'}, false, ['verify']);
  const verified = await crypto.subtle.verify('HMAC', key, hexBytes(input.mac_hex), message);
  if (!verified) fail('pi_financial_mac_invalid');
  return { observedAtMs, cycleId: input.source.cycle_id };
}
export async function storePrivateFinancial(storage, envelope, env, nowMs = Date.now()) {
  const verified = await verifyPrivateFinancial(envelope, env, nowMs);
  // Durable Object transaction prevents a concurrent lower-cycle write from
  // overwriting an accepted newer cycle. Never store a fake zero or paper data.
  const result = await storage.transaction(async (txn) => {
    const predecessor = await txn.get('pi_financial_latest');
    if (predecessor) {
      // Validate stored contract at its own observed time; corrupted history is
      // a held ledger, NOT authority to overwrite/restart financial tracking.
      const oldTime = Date.parse(predecessor?.envelope?.source?.observed_at_utc || '');
      if (!Number.isFinite(oldTime)) fail('pi_financial_predecessor_invalid');
      await verifyPrivateFinancial(predecessor.envelope, env, oldTime);
      if (verified.observedAtMs < oldTime) fail('pi_financial_replay');
      if (verified.observedAtMs === oldTime) {
        if (predecessor.envelope.source.cycle_id === verified.cycleId
            && predecessor.envelope.mac_hex === envelope.mac_hex) {
          return { same: true, storedAt: predecessor.stored_at_utc };
        }
        fail('pi_financial_conflict');
      }
    }
    const record = {schema:'mmibkr.pi_financial_private_store.v1',
      stored_at_utc: new Date(nowMs).toISOString(), envelope};
    await txn.put('pi_financial_latest', record);
    return {same:false, storedAt:record.stored_at_utc};
  });
  const reloaded = await storage.get('pi_financial_latest');
  if (!reloaded || reloaded.envelope.mac_hex !== envelope.mac_hex) {
    fail('pi_financial_readback_failed');
  }
  return {ok:true, accepted:!result.same, stored_at_utc:result.storedAt,
    broker_mutation_authority:false};
}
export async function readPrivateFinancial(storage, env, nowMs = Date.now()) {
  const record = await storage.get('pi_financial_latest');
  if (!record || record.schema !== 'mmibkr.pi_financial_private_store.v1') {
    fail('pi_financial_not_installed');
  }
  const { observedAtMs } = await verifyPrivateFinancial(record.envelope, env, nowMs);
  const { source, snapshot } = record.envelope;
  // This is an Access-verified human projection. Never return the machine MAC,
  // expected-account hash, secret, or raw signed source envelope to the client.
  return {...snapshot,
    source:{node_id:'cc-pi4',observed_at_utc:source.observed_at_utc,
      cycle_id:source.cycle_id,account_scope_verified:true,
      age_seconds:Math.round(Math.max(0,nowMs-observedAtMs)/100)/10},
    status:'VERIFIED_FRESH'};
}

export function requireFinancePublisherAdmission(env) {
  // Both independent operations (approved exact origin/Access route and root
  // collector) must be admitted. An accidental secret-only deploy stays OFF.
  if (env?.PI_LIVE_FINANCE_INGEST_ENABLED !== '1'
      || env?.PI_LIVE_FINANCE_ORIGIN_ADMITTED !== '1') {
    fail('pi_financial_ingest_not_admitted');
  }
  if (!HEX_KEY.test(String(env?.PI_LIVE_FINANCE_HMAC_KEY || ''))
      || !HEX64.test(String(env?.PI_LIVE_EXPECTED_ACCOUNT_SHA256 || ''))
      || !/^[a-f0-9]{24,128}$/.test(String(env?.PI_LIVE_FINANCE_ACCESS_AUD || ''))
      || !/^[A-Za-z0-9._-]{16,160}$/.test(String(env?.PI_LIVE_FINANCE_SERVICE_CLIENT_ID || ''))) {
    fail('pi_financial_machine_identity_unconfigured');
  }
}

export function requireFinanceServiceClaims(claims, env, expectedIssuer) {
  // Caller must already have passed the existing verified RS256 Access JWT
  // validator. A user session cannot impersonate an Access service token.
  if (!record(claims) || claims.type !== 'app'
      || claims.iss !== expectedIssuer
      || !((Array.isArray(claims.aud) ? claims.aud : [claims.aud])
        .includes(env.PI_LIVE_FINANCE_ACCESS_AUD))
      || claims.common_name !== env.PI_LIVE_FINANCE_SERVICE_CLIENT_ID
      || claims.sub !== '' || (claims.email !== undefined && claims.email !== '')) {
    fail('pi_financial_service_principal_rejected');
  }
  return true;
}