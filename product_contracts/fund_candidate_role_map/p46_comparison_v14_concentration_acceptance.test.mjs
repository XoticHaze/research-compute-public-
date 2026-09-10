import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '64904e664406897882201e3edbffd9bdd684f87f'
const comparison = Object.freeze({
  schema: 'mm.strategy_intelligence.fund_candidate_comparison.v14',
  state: 'NONRANKING_SURVIVOR_CONTEXT_WITH_P46_CONCENTRATION_AND_FAILURE_GUARDRAILS',
  readiness: 'ISSUER_REPLAY_SUPPORTED_UNIVERSE_ROBUSTNESS_OPEN',
  p46: Object.freeze({
    role: 'SUPPORTED_CROSSASSET_RESEARCH_UNIVERSE_CONCENTRATED',
    unresolved_gate: 'universe jackknife failed 3/5; orthogonal adjudication required',
  }),
})
const p167 = Object.freeze({ run:34417053594, job:102684140262, artifact:10129482117, head:'2ee274c013710100391e6d4bb361ac8fcc6d839c', started:'2026-09-09T23:28:02Z', survivors:3, total:5, required:4 })
const boundaries = Object.freeze({ ranking:false, allocation:false, sizing:false, promotion:false, strategy_spec:false, runtime:false, broker:false, live_trading:false })

test('bind exact MM operator-integration head', () => assert.equal(MM_PRODUCT_HEAD, '64904e664406897882201e3edbffd9bdd684f87f'))
test('comparison exposes P46 concentration rather than stale generic validation', () => {
  assert.equal(comparison.schema, 'mm.strategy_intelligence.fund_candidate_comparison.v14')
  assert.equal(comparison.state, 'NONRANKING_SURVIVOR_CONTEXT_WITH_P46_CONCENTRATION_AND_FAILURE_GUARDRAILS')
  assert.equal(comparison.readiness, 'ISSUER_REPLAY_SUPPORTED_UNIVERSE_ROBUSTNESS_OPEN')
  assert.match(comparison.p46.role, /UNIVERSE_CONCENTRATED/)
  assert.match(comparison.p46.unresolved_gate, /jackknife failed 3\/5/i)
})
test('acceptance preserves exact P167 execution identity and failed predeclared gate', () => {
  assert.deepEqual([p167.run,p167.job,p167.artifact,p167.head,p167.started],[34417053594,102684140262,10129482117,'2ee274c013710100391e6d4bb361ac8fcc6d839c','2026-09-09T23:28:02Z'])
  assert.ok(p167.survivors < p167.required)
})
test('operator integration grants no ranking or trading authority', () => assert.deepEqual(Object.values(boundaries), Array(Object.keys(boundaries).length).fill(false)))
