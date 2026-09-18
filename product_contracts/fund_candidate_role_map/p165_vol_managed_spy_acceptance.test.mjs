import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '37904a591ec92a54214582d584fd1ff29007ebaa'
const p165 = Object.freeze({ run:34416477220, job:102682373000, artifact:10129266444, head:'62f6c5674d58dff8e8a1df4ea1755412d8b3f788', started:'2026-09-09T23:20:22.9644884Z', matched:-0.017452065882035628, spy:-0.04128756437496239, folds:1, maxdd:-0.16606473737198824, matchedMaxdd:-0.19919089536591894 })

test('bind exact P165 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '37904a591ec92a54214582d584fd1ff29007ebaa'))
test('P165 fails matched alpha and opportunity cost despite lower drawdown', () => { assert.ok(p165.matched < 0); assert.ok(p165.spy < 0); assert.equal(p165.folds,1); assert.ok(Math.abs(p165.maxdd) < Math.abs(p165.matchedMaxdd)) })
test('preserve exact P165 execution identity', () => assert.deepEqual([p165.run,p165.job,p165.artifact,p165.head,p165.started],[34416477220,102682373000,10129266444,'62f6c5674d58dff8e8a1df4ea1755412d8b3f788','2026-09-09T23:20:22.9644884Z']))
test('no target, lookback, cap, cost, window, or authority rescue', () => assert.deepEqual(Object.values({ target:false, lookback:false, cap:false, cost:false, windows:false, ranking:false, allocation:false, sizing:false, promotion:false, runtime:false, broker:false, live:false }), Array(12).fill(false)))
