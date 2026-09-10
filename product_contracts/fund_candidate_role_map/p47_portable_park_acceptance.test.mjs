import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '2b6a031426d62f8349653a008c2d11704b3e55aa'
const p47 = Object.freeze({
  decision:'PARK_STANDALONE_PRESERVE_COMPONENT_SCOPE',
  p164:Object.freeze({run:34416367307,job:102682031382,artifact:10129237160,head:'5bd250b9648f2ae44f8ef7632b851cb03b7c1fed',started:'2026-09-09T23:18:54.6783560Z',probability_nonpositive_2015:0.3804}),
  p162_failure:'one-additional-month implementation delay reversed 2015+ matched/SPY excess with 1/5 positive matched folds',
})
const portable = Object.freeze({schema:'mm.strategy_intelligence.crossasset_fund_candidate_browser_review.v3',active_secondary_candidate:false,historical_point_context_preserved:true})
const boundaries = Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM portable-review head', () => assert.equal(MM_PRODUCT_HEAD,'2b6a031426d62f8349653a008c2d11704b3e55aa'))
test('portable review exposes the admitted P47 park instead of active-secondary semantics', () => {
  assert.equal(portable.schema,'mm.strategy_intelligence.crossasset_fund_candidate_browser_review.v3')
  assert.equal(p47.decision,'PARK_STANDALONE_PRESERVE_COMPONENT_SCOPE')
  assert.equal(portable.active_secondary_candidate,false)
  assert.equal(portable.historical_point_context_preserved,true)
})
test('P47 park acceptance preserves exact P164 identity and independent timing failure', () => {
  assert.deepEqual([p47.p164.run,p47.p164.job,p47.p164.artifact,p47.p164.head],[34416367307,102682031382,10129237160,'5bd250b9648f2ae44f8ef7632b851cb03b7c1fed'])
  assert.ok(p47.p164.probability_nonpositive_2015 > 0.35)
  assert.match(p47.p162_failure,/1\/5 positive matched folds/)
})
test('portable correction grants no product authority', () => assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
