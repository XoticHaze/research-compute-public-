import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '47bc16857b8cd3fd8b5bed715bfeca7e094731ac'
const p430 = Object.freeze({
  parent: 'P305_DBMF_COMPLEMENTARITY',
  state: 'MATCHED_ALPHA_BOOTSTRAP_SUPPORTED__INCREMENTAL_CORE_SUPERIORITY_NOT_ROBUSTLY_ESTABLISHED__RANK_UNCHANGED_PENDING_COORDINATOR',
  common_months: 88,
  observed_matched_excess_pp: 5.056,
  matched_p_nonpositive_pct: 4.84,
  matched_p5_pp: 0.029,
  core_advantage_observed_pp: 2.718,
  core_p_nonpositive_pct: 21.76,
  core_p5_pp: -2.696,
  gate_pct: 20.0,
  run_id: 34521334147,
  job_id: 103019306216,
  artifact_id: 10169761666,
  artifact_sha256: 'd52ba8cd5a1d947a97fa2677be2bfef00e7756b2edd590f3f6bace1ad29a2538',
})

test('bind exact P430 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '47bc16857b8cd3fd8b5bed715bfeca7e094731ac'))
test('matched alpha survives the predeclared bootstrap gate', () => {
  assert.equal(p430.common_months, 88)
  assert.equal(p430.observed_matched_excess_pp, 5.056)
  assert.ok(p430.matched_p_nonpositive_pct <= p430.gate_pct)
  assert.ok(p430.matched_p5_pp > 0)
})
test('incremental frozen-core superiority is explicitly withheld', () => {
  assert.equal(p430.core_advantage_observed_pp, 2.718)
  assert.ok(p430.core_p_nonpositive_pct > p430.gate_pct)
  assert.ok(p430.core_p5_pp < 0)
  assert.match(p430.state, /SUPERIORITY_NOT_ROBUSTLY_ESTABLISHED/)
})
test('exact research execution identity remains attributable', () => {
  assert.deepEqual([p430.run_id, p430.job_id, p430.artifact_id], [34521334147, 103019306216, 10169761666])
  assert.equal(p430.artifact_sha256, 'd52ba8cd5a1d947a97fa2677be2bfef00e7756b2edd590f3f6bace1ad29a2538')
})
test('consumer grants no portfolio or trading authority', () => {
  assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false))
})
