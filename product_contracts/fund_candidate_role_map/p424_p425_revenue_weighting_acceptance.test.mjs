import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'b30d6fd69f49519827fadd7dc022bd9fbbf003fc'
const review = Object.freeze({
  schema: 'mm.strategy_intelligence.revenue_weighting_family_evidence.v2',
  authority: 'DESCRIPTIVE_RESEARCH_EVIDENCE_ONLY',
  state: 'SMALL_CAP_REVENUE_WEIGHTING_SCOPED_SURVIVOR__BROAD_FAMILY_TRANSPORT_REJECTED',
  p424: Object.freeze({ matched_vs_ijr_pp: [1.401, 1.648, 6.825], spy_opportunity_pp: [-0.866, -2.341, 1.365], chronology: [2,3], run: 34519388449, job: 103012799417, artifact: 10168998132 }),
  p425: Object.freeze({ matched_vs_spy_pp: [-0.492, -1.248, -0.497], qqq_opportunity_pp: [-5.175, -6.342, -5.612], chronology: [1,3], run: 34519528892, job: 103013274882, artifact: 10169051970 }),
  protected: Object.freeze({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, broker:false, live:false }),
})

test('bind exact revenue-weighting operator head', () => assert.equal(MM_PRODUCT_HEAD, 'b30d6fd69f49519827fadd7dc022bd9fbbf003fc'))
test('P424 remains a scoped small-cap survivor', () => { assert.equal(review.state, 'SMALL_CAP_REVENUE_WEIGHTING_SCOPED_SURVIVOR__BROAD_FAMILY_TRANSPORT_REJECTED'); assert.deepEqual(review.p424.matched_vs_ijr_pp, [1.401,1.648,6.825]); assert.deepEqual(review.p424.chronology,[2,3]) })
test('P425 rejects broad revenue-weighting transport', () => { assert.ok(review.p425.matched_vs_spy_pp.every((x) => x < 0)); assert.ok(review.p425.qqq_opportunity_pp.every((x) => x < 0)); assert.deepEqual(review.p425.chronology,[1,3]) })
test('exact external research identities are retained', () => { assert.deepEqual([review.p424.run,review.p424.job,review.p424.artifact],[34519388449,103012799417,10168998132]); assert.deepEqual([review.p425.run,review.p425.job,review.p425.artifact],[34519528892,103013274882,10169051970]) })
test('product review grants no portfolio or trading authority', () => assert.deepEqual(Object.values(review.protected), Array(8).fill(false)))
