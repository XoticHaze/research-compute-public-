import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '0c2078f72dcf8c5aaacc4ab9bc3883ceae7cf79b'
const p157 = { run:34414536658, job:102676338030, artifact:10128534735, head:'2fcc9482ad8fcd62002633e2be3ae44227049d03', matched:-0.06138181360077333, spy:-0.0793738957850676 }
const p158 = { run:34414596317, job:102676529883, artifact:10128557883, head:'0fe564ccd79e0d5239e1acf215cd5936f39f779c', matched:-0.023555595639495053, spy:-0.043734023523485765, scope:'SPY_ONLY_DO_NOT_DEMOTE_MES_ES', netMaxdd:-0.17480744752222255, matchedMaxdd:-0.20537301465487645 }

test('bind exact P157-P158 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '0c2078f72dcf8c5aaacc4ab9bc3883ceae7cf79b'))
test('P157 rejects opposite-sign sector rescue', () => { assert.ok(p157.matched < 0); assert.ok(p157.spy < 0) })
test('P158 is a scoped SPY transfer failure despite drawdown reduction', () => { assert.ok(p158.matched < 0); assert.ok(p158.spy < 0); assert.ok(Math.abs(p158.netMaxdd) < Math.abs(p158.matchedMaxdd)); assert.equal(p158.scope, 'SPY_ONLY_DO_NOT_DEMOTE_MES_ES') })
test('preserve exact science execution identities', () => assert.deepEqual([[p157.run,p157.job,p157.artifact,p157.head],[p158.run,p158.job,p158.artifact,p158.head]], [[34414536658,102676338030,10128534735,'2fcc9482ad8fcd62002633e2be3ae44227049d03'],[34414596317,102676529883,10128557883,'0fe564ccd79e0d5239e1acf215cd5936f39f779c']]))
test('no ranking allocation or trading authority', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
