import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '3043430b1524482f2af8ad3c96536a224a783e6e'
const coordinator = Object.freeze({
  source_pr: 762,
  source_head: '4a63b8e5ff6aa2740de7b657f63f5382cae50d2a',
  durable_event: '7241738a1604c0e338fef6d87d7c9a8014583b78',
  core: 'UNCHANGED_P249_PLUS_P373',
  ranked: [
    ['INTERNATIONAL_FACTOR_COMBINATION', 1, 'SURVIVES_WITH_CAVEAT__NEXT_DIRECT_PORTFOLIO_DISCRIMINATOR'],
    ['AAA_CLO_CASH_PLUS_PREMIUM', 2, 'SURVIVES_WITH_CAVEAT__RISK_BUDGET_CHALLENGER'],
    ['P305_DBMF_COMPLEMENTARITY', 3, 'SURVIVES_WITH_CAVEAT__MATCHED_ALPHA_SUPPORTED_CORE_SUPERIORITY_UNPROVEN__DIRECT_PROMOTION_PRIORITY_DEMOTED'],
  ],
  p305: { matched_excess_pp: 5.056, common_months: 88, matched_p_nonpositive_pct: 4.84, core_p_nonpositive_pct: 21.76, gate_pct: 20.0 },
})

test('bind exact rerank consumer head', () => assert.equal(MM_PRODUCT_HEAD, '3043430b1524482f2af8ad3c96536a224a783e6e'))
test('consume exact Coordinator authority provenance', () => {
  assert.equal(coordinator.source_pr, 762)
  assert.equal(coordinator.source_head, '4a63b8e5ff6aa2740de7b657f63f5382cae50d2a')
  assert.equal(coordinator.durable_event, '7241738a1604c0e338fef6d87d7c9a8014583b78')
  assert.equal(coordinator.core, 'UNCHANGED_P249_PLUS_P373')
})
test('project Coordinator ordering without inventing a Trading Product rerank', () => {
  assert.deepEqual(coordinator.ranked.map((row)=>row.slice(0,2)), [['INTERNATIONAL_FACTOR_COMBINATION',1],['AAA_CLO_CASH_PLUS_PREMIUM',2],['P305_DBMF_COMPLEMENTARITY',3]])
})
test('P305 matched-alpha survivor evidence remains intact while direct promotion is demoted', () => {
  assert.equal(coordinator.p305.matched_excess_pp, 5.056)
  assert.equal(coordinator.p305.common_months, 88)
  assert.ok(coordinator.p305.matched_p_nonpositive_pct <= coordinator.p305.gate_pct)
  assert.ok(coordinator.p305.core_p_nonpositive_pct > coordinator.p305.gate_pct)
  assert.match(coordinator.ranked[2][2], /DIRECT_PROMOTION_PRIORITY_DEMOTED/)
})
test('consumer grants no independent portfolio or trading authority', () => assert.deepEqual(Object.values({ independentRanking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
