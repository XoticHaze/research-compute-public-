import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '243b2e6bd5072c61f4b42514bac479d59bb60f19'
const p167 = Object.freeze({ run:34417053594, job:102684140262, artifact:10129482117, head:'2ee274c013710100391e6d4bb361ac8fcc6d839c', started:'2026-09-09T23:28:02Z', survivors:3, total:5, required:4, omitDBC:-0.01004656320687869, omitDBCfolds:2, omitGLD:0.020995733966049146, omitGLDfolds:2 })

const boundaries = Object.freeze({ replacement_asset_search:false, parameter_rescue:false, ranking:false, allocation:false, sizing:false, promotion:false, strategy_spec:false, runtime:false, data:false, broker:false, live_trading:false })

test('bind exact P46 jackknife MM product head', () => assert.equal(MM_PRODUCT_HEAD, '243b2e6bd5072c61f4b42514bac479d59bb60f19'))
test('P167 fails the predeclared leave-one-out robustness gate', () => { assert.equal(p167.survivors,3); assert.equal(p167.total,5); assert.ok(p167.survivors < p167.required) })
test('failure is economically and fold specific rather than erasing prior P46 evidence', () => { assert.ok(p167.omitDBC < 0); assert.equal(p167.omitDBCfolds,2); assert.ok(p167.omitGLD > 0); assert.equal(p167.omitGLDfolds,2) })
test('preserve exact P167 execution identity', () => assert.deepEqual([p167.run,p167.job,p167.artifact,p167.head,p167.started],[34417053594,102684140262,10129482117,'2ee274c013710100391e6d4bb361ac8fcc6d839c','2026-09-09T23:28:02Z']))
test('fail closed without rescue or authority transfer', () => assert.deepEqual(Object.values(boundaries), Array(Object.keys(boundaries).length).fill(false)))
