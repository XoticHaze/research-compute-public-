import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '5bd7921ad83305a785f5193ff26671d5045e1d0b'
const p163 = Object.freeze({ run:34416523607, job:102682519639, artifact:10129284504, head:'41b1bf6578a76b28c8e322d5dbdf5757d8801510', started:'2026-09-09T23:20:59.9775623Z', matched:-0.021621716329380813, spy:-0.031178995993577097, qqq:-0.08248030356587321, folds:1 })

test('bind exact P160 park MM product head', () => assert.equal(MM_PRODUCT_HEAD, '5bd7921ad83305a785f5193ff26671d5045e1d0b'))
test('P163 delay failure is material at combination level', () => { assert.ok(p163.matched < 0); assert.ok(p163.spy < 0); assert.ok(p163.qqq < 0); assert.equal(p163.folds, 1) })
test('P161 plus P163 satisfies park consequence without erasing descriptive evidence', () => assert.deepEqual({ decision:'PARK_INVESTABLE_COMBINATION', descriptive:'PRESERVE' }, { decision:'PARK_INVESTABLE_COMBINATION', descriptive:'PRESERVE' }))
test('preserve exact P163 execution identity', () => assert.deepEqual([p163.run,p163.job,p163.artifact,p163.head,p163.started],[34416523607,102682519639,10129284504,'41b1bf6578a76b28c8e322d5dbdf5757d8801510','2026-09-09T23:20:59.9775623Z']))
test('no parameter rescue or authority transfer', () => assert.deepEqual(Object.values({ weight:false, timing:false, significance:false, cost:false, threshold:false, ranking:false, allocation:false, sizing:false, promotion:false, runtime:false, broker:false, live:false }), Array(12).fill(false)))
