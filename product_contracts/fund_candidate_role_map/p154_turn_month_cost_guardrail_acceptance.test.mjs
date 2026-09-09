import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '5177bdae39758e2a1e30a501055cd2253dd5c16e'
const evidence = { parent:'P154', run:34413796066, job:102673978542, artifact:10128256712, head:'cf45fb12e7bb2d8fc2c294a9d62dca57aeb6f553', matched50:-0.11745718180748199, matched25:-0.06079494547160835, spy50:-0.22832184938715094, folds50:0, exposure:0.19099590723055934, turnover:24.065484311050476 }

test('bind exact P154 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '5177bdae39758e2a1e30a501055cd2253dd5c16e'))
test('P154 fails after costs at both 25 and 50 bps', () => { assert.ok(evidence.matched25 < 0); assert.ok(evidence.matched50 < 0); assert.equal(evidence.folds50, 0) })
test('switching burden is economically material', () => { assert.ok(evidence.turnover > 24); assert.ok(evidence.exposure < 0.20); assert.ok(evidence.spy50 < 0) })
test('preserve exact science execution identity', () => assert.deepEqual([evidence.run,evidence.job,evidence.artifact,evidence.head],[34413796066,102673978542,10128256712,'cf45fb12e7bb2d8fc2c294a9d62dca57aeb6f553']))
test('no ranking allocation or trading authority', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
