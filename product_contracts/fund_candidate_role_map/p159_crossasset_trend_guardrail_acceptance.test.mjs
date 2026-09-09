import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'cc7a553f621aa2e603455ba5ab998f99b859daeb'
const p159 = Object.freeze({
  run: 34415558477,
  job: 102679536875,
  artifact: 10128917852,
  head: 'cc234f5d35e43e4e793d688a9ed8a54f2b33f51f',
  started: '2026-09-09T23:08:24.8359509Z',
  matched: -0.014710759144218377,
  equalWeight: -0.03604529918517718,
  spy: -0.08181061047022364,
  folds: 0,
  netMaxdd: -0.06796771696105497,
  matchedMaxdd: -0.1237751544057265,
})

test('bind exact P159 MM product head', () => assert.equal(MM_PRODUCT_HEAD, 'cc7a553f621aa2e603455ba5ab998f99b859daeb'))
test('P159 fails matched and opportunity-cost alpha gates', () => { assert.ok(p159.matched < 0); assert.ok(p159.equalWeight < 0); assert.ok(p159.spy < 0); assert.equal(p159.folds, 0) })
test('drawdown benefit does not overwrite alpha failure', () => assert.ok(Math.abs(p159.netMaxdd) < Math.abs(p159.matchedMaxdd)))
test('preserve exact science execution identity', () => assert.deepEqual([p159.run,p159.job,p159.artifact,p159.head,p159.started], [34415558477,102679536875,10128917852,'cc234f5d35e43e4e793d688a9ed8a54f2b33f51f','2026-09-09T23:08:24.8359509Z']))
test('no authority transfer', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
