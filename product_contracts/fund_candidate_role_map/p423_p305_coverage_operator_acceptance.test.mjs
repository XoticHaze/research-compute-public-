import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '59f3567f59da7179e865d31d1bf094ee4d35097a'
const state = Object.freeze({
  schema: 'mm_ibkr.fund_portfolio_role_current.v1',
  authority: 'DESCRIPTIVE_OPERATOR_RESEARCH_STATE_ONLY',
  core_capital_state: 'UNCHANGED_P249_PLUS_P373_PENDING_VALID_PROMOTION_EVIDENCE',
  candidate: Object.freeze({
    rank: 1,
    id: 'P305_DBMF_COMPLEMENTARITY',
    state: 'COVERAGE_VALID_MARGINAL_UTILITY_SUPPORTED__RANK_UNCHANGED_PENDING_COORDINATOR',
    coverage_common_months: 88,
    coverage_block_months: [29, 29, 30],
    full_matched_excess_pp: 5.056,
    chronology_matched_excess_pp: [4.937, 4.395, 5.823],
    challenger_minus_core_cagr_pp: 2.72,
    sharpe_delta: 0.3401,
    max_drawdown_improvement_pp: 6.42,
    run_id: 34519254351,
    job_id: 103012353988,
    artifact_id: 10168949628,
    artifact_sha256: '1e66a243355e69b295a8324800b91edb237b028d2fe5f5f0c7a12cbad7393faf',
  }),
  protected: Object.freeze({ allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }),
})

test('bind exact MM P305 coverage-valid operator head', () => assert.equal(MM_PRODUCT_HEAD, '59f3567f59da7179e865d31d1bf094ee4d35097a'))
test('coverage-valid chronology replaces stale coverage blocker', () => {
  assert.equal(state.candidate.state, 'COVERAGE_VALID_MARGINAL_UTILITY_SUPPORTED__RANK_UNCHANGED_PENDING_COORDINATOR')
  assert.equal(state.candidate.coverage_common_months, 88)
  assert.deepEqual(state.candidate.coverage_block_months, [29,29,30])
  assert.ok(state.candidate.chronology_matched_excess_pp.every((x) => x > 0))
})
test('operator keeps matched, risk, and exact execution context', () => {
  assert.equal(state.candidate.full_matched_excess_pp, 5.056)
  assert.equal(state.candidate.challenger_minus_core_cagr_pp, 2.72)
  assert.equal(state.candidate.sharpe_delta, 0.3401)
  assert.equal(state.candidate.max_drawdown_improvement_pp, 6.42)
  assert.equal(state.candidate.run_id, 34519254351)
  assert.equal(state.candidate.job_id, 103012353988)
  assert.equal(state.candidate.artifact_id, 10168949628)
  assert.equal(state.candidate.artifact_sha256, '1e66a243355e69b295a8324800b91edb237b028d2fe5f5f0c7a12cbad7393faf')
})
test('existing rank is descriptive and protected authorities remain false', () => {
  assert.equal(state.candidate.rank, 1)
  assert.equal(state.authority, 'DESCRIPTIVE_OPERATOR_RESEARCH_STATE_ONLY')
  assert.deepEqual(Object.values(state.protected), Array(8).fill(false))
})
