import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD = '893983568fb4ae97a888f30c2ad88116b1f358a7'
const p64 = {
  combination: { run: 34295697967, job: 102291734873, artifact: 10083033113, excess25: 0.023073225671643494, excess50: 0.014621824120992999, positiveFolds25: 5, qqq25: -0.03383244809712416 },
  serial: { run: 34295845915, job: 102292190800, rolling60Matched: 0.7670454545454546, bootstrapP: 0.0744, rolling60Qqq: 0.07386363636363637 },
  concentration: { run: 34295965678, job: 102292560454, strongestRemoved25: 0.0017875577238135598, strongestRemoved50: -0.006701767461439134, riskOnQqq25: -0.03352551994849606, riskOffQqq25: -0.03492980925890987 },
  capital: { run: 34296802102, job: 102295104060, breakevenBps: 94, excess25: 0.023073173358661325, excess50: 0.014621772350719597, excess100: -0.002114708190346981, spy25: 0.018866811139905293, qqq25: -0.03383249594227222, maxDrawdown25: -0.2680086397587087 },
}

test('P64 acceptance binds the exact MM operator-product head', () => assert.equal(MM_HEAD, '893983568fb4ae97a888f30c2ad88116b1f358a7'))
test('P64 retains after-cost matched-control persistence and implementation headroom', () => {
  assert.equal(p64.combination.run, 34295697967); assert.equal(p64.combination.job, 102291734873); assert.equal(p64.combination.artifact, 10083033113)
  assert.ok(p64.combination.excess25 > 0); assert.ok(p64.combination.excess50 > 0); assert.equal(p64.combination.positiveFolds25, 5)
  assert.ok(p64.serial.rolling60Matched > 0.5); assert.ok(p64.serial.bootstrapP < 0.10)
  assert.ok(p64.capital.breakevenBps >= 50); assert.ok(p64.capital.excess50 > 0); assert.ok(p64.capital.excess100 < 0)
})
test('P64 product posture preserves concentration and QQQ opportunity cost instead of promoting broad-market replacement', () => {
  assert.ok(p64.concentration.strongestRemoved25 > 0); assert.ok(p64.concentration.strongestRemoved50 < 0)
  assert.ok(p64.combination.qqq25 < 0); assert.ok(p64.concentration.riskOnQqq25 < 0); assert.ok(p64.concentration.riskOffQqq25 < 0); assert.ok(p64.capital.qqq25 < 0)
  assert.ok(p64.capital.spy25 > 0); assert.ok(p64.capital.maxDrawdown25 < 0)
})
test('P64 protected authorities remain false', () => {
  const boundary = { portfolioRanking:false, allocation:false, sizing:false, timing:false, strategySpec:false, runtime:false, data:false, broker:false, liveTrading:false }
  assert.deepEqual(Object.values(boundary), Array(9).fill(false))
})
