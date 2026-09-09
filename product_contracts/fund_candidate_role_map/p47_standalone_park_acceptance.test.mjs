import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '0e9dbbfe403cb4397146551b6b4516f0d70ef8fe'
const p164 = Object.freeze({ run:34416367307, job:102682031382, artifact:10129237160, head:'5bd250b9648f2ae44f8ef7632b851cb03b7c1fed', started:'2026-09-09T23:18:54.6783560Z', pNonPositive2015:0.3804, pNonPositive2020:0.312, ci2015:[-0.03785047576653117,0.05204212161584363] })

test('bind exact P47 park MM product head', () => assert.equal(MM_PRODUCT_HEAD, '0e9dbbfe403cb4397146551b6b4516f0d70ef8fe'))
test('P164 statistical weakness is material', () => { assert.equal(p164.pNonPositive2015,0.3804); assert.equal(p164.pNonPositive2020,0.312); assert.ok(p164.ci2015[0] < 0 && p164.ci2015[1] > 0) })
test('two independent weaknesses justify standalone park, not component erasure', () => assert.deepEqual({ standalone:'PARK', component:'PRESERVE_BOUNDED_SCOPE' }, { standalone:'PARK', component:'PRESERVE_BOUNDED_SCOPE' }))
test('preserve exact P164 execution', () => assert.deepEqual([p164.run,p164.job,p164.artifact,p164.head,p164.started],[34416367307,102682031382,10129237160,'5bd250b9648f2ae44f8ef7632b851cb03b7c1fed','2026-09-09T23:18:54.6783560Z']))
test('no parameter rescue or authority transfer', () => assert.deepEqual(Object.values({ timing:false, factors:false, topK:false, costs:false, bootstrap:false, ranking:false, allocation:false, sizing:false, promotion:false, runtime:false, broker:false, live:false }), Array(12).fill(false)))
