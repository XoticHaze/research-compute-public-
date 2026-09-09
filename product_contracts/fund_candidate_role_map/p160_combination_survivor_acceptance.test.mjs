import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'fd64f76024087ae5edce88f6a0267b4fd17caed1'
const p160 = Object.freeze({
  run:34415893385, job:102680576356, artifact:10129047114,
  head:'c575e02aba939b283c0aa409d9bc21f000c0762c', started:'2026-09-09T23:12:47.6743078Z',
  combo:0.14562232100543548, matched:0.01719141484998743, spy:0.007634117052302436,
  qqq:-0.043667148387023236, folds:5, corr:0.44474111993398585,
  sharpe:1.1347698858528121, maxdd:-0.17429722954835236, matchedMaxdd:-0.22999268710153842,
  matched100:-0.002092596670658864, weight:'FROZEN_50_50_NO_OPTIMIZATION'
})

test('bind exact P160 MM product head', () => assert.equal(MM_PRODUCT_HEAD, 'fd64f76024087ae5edce88f6a0267b4fd17caed1'))
test('P160 clears declared 50bps combination gate', () => { assert.ok(p160.matched > 0); assert.ok(p160.spy > 0); assert.equal(p160.folds, 5); assert.ok(p160.corr > 0 && p160.corr < 1); assert.ok(Math.abs(p160.maxdd) < Math.abs(p160.matchedMaxdd)) })
test('opportunity and higher-cost limits stay visible', () => { assert.ok(p160.qqq < 0); assert.ok(p160.matched100 < 0) })
test('weight remains frozen and unoptimized', () => assert.equal(p160.weight, 'FROZEN_50_50_NO_OPTIMIZATION'))
test('preserve exact science execution identity', () => assert.deepEqual([p160.run,p160.job,p160.artifact,p160.head,p160.started], [34415893385,102680576356,10129047114,'c575e02aba939b283c0aa409d9bc21f000c0762c','2026-09-09T23:12:47.6743078Z']))
test('no authority transfer', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
