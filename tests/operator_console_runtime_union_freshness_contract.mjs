import assert from 'node:assert/strict';
import { mergeRuntimeProjection, OperatorState } from '../cloudflare/operator-console/src/index.js';

function snapshot(source, runtimes) {
  return {
    schema: 'mmibkr.cloud_operator_snapshot.v1',
    mode: 'paper', live_enabled: false,
    runtime: { source_sha: source }, runtimes, positions: [],
    privacy: {
      private_operator_state: true, account_identifiers_included: false,
      credentials_included: false, tokens_included: false,
      private_source_included: false, execution_authority_included: false,
    },
    authority: {
      presentation_projection_only: true, strategy_authority: false,
      execution_policy_authority: false, sizing_authority: false,
      broker_mutation_authority: false, live_execution_allowed: false,
    },
  };
}

const previousRow = {
  runtime_id: 'AMAT-15Min', symbol: 'AMAT', state: 'managing',
  last_action: 'BUY', candidate_ready: true, broker_action: true,
  position: { position: 4 }, broker_symbol_position: { position: 4 },
  broker_symbol_position_observed: true,
  position_ownership: { attributed: true, source: 'previous_only' },
  primary_metric: { current: 1, target: 2 },
  conditions: [{ status: 'pass' }], position_context: { open: true },
  market_context: { features: [{ name: 'RSI', value: 70 }], quote: { price: 150 } },
  data_health: { current: true, observed_this_boundary: true, target_bar_close_utc: '2026-10-25T14:00:00Z' },
};
const incomingRow = {
  runtime_id: 'MNQ-12Min', symbol: 'MNQ', state: 'watching',
  last_action: 'WAIT', candidate_ready: false, broker_action: false,
  data_health: { current: true, observed_this_boundary: true },
};
const previous = { snapshot: snapshot('a'.repeat(40), [previousRow]) };
const incoming = snapshot('a'.repeat(40), [incomingRow]);
const result = mergeRuntimeProjection(previous, incoming);
assert.equal(result.runtimeMergeApplied, true);
assert.equal(result.previousRuntimeCount, 1);
assert.equal(result.snapshot.runtimes.length, 2);
const carried = result.snapshot.runtimes.find((row) => row.runtime_id === previousRow.runtime_id);
const fresh = result.snapshot.runtimes.find((row) => row.runtime_id === incomingRow.runtime_id);
assert.deepEqual(fresh, incomingRow, 'fresh incoming runtime must win unchanged');
assert.equal(carried.state, 'unobserved');
assert.equal(carried.last_action, 'NOT_OBSERVED');
assert.equal(carried.candidate_ready, false);
assert.equal(carried.broker_action, false);
assert.equal(carried.position, null);
assert.equal(carried.broker_symbol_position, null);
assert.equal(carried.broker_symbol_position_observed, false);
assert.equal(carried.position_ownership.attributed, false);
assert.equal(carried.position_ownership.carried_from_previous_snapshot, true);
assert.equal(carried.position_ownership.attribution_unverified_this_boundary, true);
assert.equal(carried.primary_metric, null);
assert.deepEqual(carried.conditions, []);
assert.equal(carried.position_context, null);
assert.deepEqual(carried.market_context, { features: [], quote: null });
assert.equal(carried.data_health.current, false);
assert.equal(carried.data_health.observed_this_boundary, false);
assert.equal(carried.data_health.not_due_this_boundary, true);
assert.equal(carried.data_health.carried_from_previous_snapshot, true);
assert.equal(carried.data_health.target_bar_close_utc, '2026-10-25T14:00:00Z');
assert.equal(previousRow.data_health.current, true, 'never mutate durable prior record');
assert.equal(previousRow.position_ownership.attributed, true);
assert.equal(mergeRuntimeProjection(previous, snapshot('b'.repeat(40), [incomingRow])).snapshot.runtimes.length, 1,
  'different private source must not inherit previous runtime rows');
assert.deepEqual(
  mergeRuntimeProjection(previous, snapshot('a'.repeat(40), [{ ...previousRow, last_action: 'HOLD' }])).snapshot.runtimes[0].last_action,
  'HOLD', 'incoming same-ID runtime must replace previous row',
);
const empty = mergeRuntimeProjection(previous, snapshot('a'.repeat(40), []));
assert.equal(empty.snapshot.runtimes[0].data_health.current, false,
  'empty new boundary cannot renew prior positive freshness');
const repeated = mergeRuntimeProjection({ snapshot: result.snapshot }, snapshot('a'.repeat(40), []));
assert.ok(repeated.snapshot.runtimes.every((row) => row.data_health.current === false),
  'repeated carry cannot restore previous eligibility');
console.log('MMIBKR_OPERATOR_CONSOLE_CARRIED_RUNTIME_FRESHNESS=PASS');

const backing = new Map();
const storage = {
  async get(key) { return backing.get(key); },
  async put(key, value) { backing.set(key, value); },
};
const state = new OperatorState({ storage }, {});
async function storeBoundary(snapshotValue) {
  return state.fetch(new Request('https://operator-state.internal/store', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ snapshot: snapshotValue, transport: {} }),
  }));
}
const currentAt = new Date(Date.now() - 120_000).toISOString();
const olderAt = new Date(Date.now() - 240_000).toISOString();
const newerAt = new Date(Date.now() - 30_000).toISOString();
const firstBoundary = { ...snapshot('a'.repeat(40), [incomingRow]), generated_at_utc: currentAt };
assert.equal((await storeBoundary(firstBoundary)).status, 201);
const olderBoundary = { ...snapshot('a'.repeat(40), [previousRow]), generated_at_utc: olderAt };
const rejectedOlder = await storeBoundary(olderBoundary);
assert.equal(rejectedOlder.status, 409, 'older same-source run cannot overwrite fresh state');
assert.equal((await rejectedOlder.json()).error, 'snapshot_out_of_order');
assert.equal((await storage.get('latest')).snapshot.generated_at_utc, currentAt);
const rejectedOtherSource = await storeBoundary({ ...olderBoundary, runtime: { source_sha: 'b'.repeat(40) } });
assert.equal(rejectedOtherSource.status, 409, 'source changes cannot backdate the displayed observation');
assert.equal((await storage.get('latest')).snapshot.runtime.source_sha, 'a'.repeat(40));
assert.equal((await storeBoundary({ ...firstBoundary, generated_at_utc: 'not-utc' })).status, 400);
assert.equal((await storeBoundary({ ...firstBoundary, generated_at_utc: new Date(Date.now() + 300_000).toISOString() })).status, 400);
assert.equal((await storeBoundary({ ...firstBoundary, generated_at_utc: newerAt })).status, 201);
assert.equal((await storage.get('latest')).snapshot.generated_at_utc, newerAt);
console.log('MMIBKR_OPERATOR_CONSOLE_MONOTONIC_SNAPSHOT_FRESHNESS=PASS');

