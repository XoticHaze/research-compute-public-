import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'ad303f19ee102e7334336a3ec9c9d1e24ecb1ee0'
const rendered = Object.freeze({
  schema: 'mm.strategy_intelligence.crossasset_fund_candidate_browser_review.v2',
  ids: ['P151','P152','P153','P154','P155','P156'],
  runs: [34413216975,34413324583,34413636900,34413796066,34413867273,34414128238],
  jobs: [102672163347,102672502198,102673477302,102673978542,102674204983,102675034072],
  artifacts: [10128051533,10128082029,10128198474,10128256712,10128286292,10128377236],
})

test('bind exact challenger-detail MM product head', () => assert.equal(MM_PRODUCT_HEAD, 'ad303f19ee102e7334336a3ec9c9d1e24ecb1ee0'))
test('portable review version carries six inspectable challenger rows', () => { assert.equal(rendered.schema, 'mm.strategy_intelligence.crossasset_fund_candidate_browser_review.v2'); assert.deepEqual(rendered.ids, ['P151','P152','P153','P154','P155','P156']) })
test('rendered provenance remains exact and row-addressable', () => { assert.equal(rendered.runs.length, 6); assert.equal(rendered.jobs.length, 6); assert.equal(rendered.artifacts.length, 6); assert.equal(rendered.runs[0], 34413216975); assert.equal(rendered.jobs[3], 102673978542); assert.equal(rendered.artifacts[5], 10128377236) })
test('consumer grants no portfolio or trading authority', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
