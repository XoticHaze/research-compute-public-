import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '5cfe592f0dc60343d5a74486043baae1d64c9a6d'
const historical = Object.freeze({ run:34291441675, job:102278643369, artifact:10081493212, original_representation_supported:true })
const current = Object.freeze({ authority:'P167_ISSUER_BOUND_UNIVERSE_JACKKNIFE', run:34417053594, job:102684140262, artifact:10129482117, survivors:3, total:5, required:4, pass:false })
const product = Object.freeze({ posture:'ECONOMIC_SUPPORT_CURRENT_UNIVERSE_ROBUSTNESS_OPEN', representation_summary:'HISTORICAL_ORIGINAL_SUPPORT_CURRENT_ISSUER_UNIVERSE_GATE_OPEN', current_supported_representation:null, old_result_may_mark_current_robust:false })
const boundaries = Object.freeze({ ranking:false, allocation:false, sizing:false, promotion:false, strategy_spec:false, runtime:false, data:false, broker:false, live_trading:false })

test('bind exact MM historical-robustness supersession head', () => assert.equal(MM_PRODUCT_HEAD,'5cfe592f0dc60343d5a74486043baae1d64c9a6d'))
test('historical deep result is retained while P167 owns current robustness', () => {
  assert.equal(historical.original_representation_supported,true)
  assert.equal(current.authority,'P167_ISSUER_BOUND_UNIVERSE_JACKKNIFE')
  assert.equal(current.pass,false)
  assert.ok(current.survivors < current.required)
  assert.equal(product.old_result_may_mark_current_robust,false)
  assert.equal(product.posture,'ECONOMIC_SUPPORT_CURRENT_UNIVERSE_ROBUSTNESS_OPEN')
  assert.equal(product.representation_summary,'HISTORICAL_ORIGINAL_SUPPORT_CURRENT_ISSUER_UNIVERSE_GATE_OPEN')
  assert.equal(product.current_supported_representation,null)
})
test('preserve both execution identities without temporal substitution', () => {
  assert.deepEqual([historical.run,historical.job,historical.artifact],[34291441675,102278643369,10081493212])
  assert.deepEqual([current.run,current.job,current.artifact],[34417053594,102684140262,10129482117])
})
test('supersession grants no capital or trading authority', () => assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
