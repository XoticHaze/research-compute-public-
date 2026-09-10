import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='51eae79536f6f0f8ca985f3bf233bdbe4ddca4c3'
const p191=Object.freeze({run:34428779237,job:102719579451,started:'2026-09-10T02:16:14.3522498Z',artifact:10133661205,matched_excess_50:-0.02440036357543396,matched_excess_25:-0.0013695724637075024,positive_folds_50:1,positive_folds_25:2,turnover:0.6761229314420805,state:'PARK'})
const p192=Object.freeze({run:34428862019,job:102719834013,started:'2026-09-10T02:17:29.7156371Z',artifact:10133691239,matched_excess_50:-0.005930579313752515,matched_excess_25:-0.0015875364877937503,matched_excess_2020_50:-0.017800293449252935,positive_folds:1,sharpe:1.0283936819243218,matched_sharpe:1.0591143031653227,state:'PARK'})
const family='P189_P192_SIMPLE_WITHIN_SECTOR_PRICE_FACTOR_FAMILY_EXHAUSTED'
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM P191/P192 product head',()=>assert.equal(MM_PRODUCT_HEAD,'51eae79536f6f0f8ca985f3bf233bdbe4ddca4c3'))
test('P191 reversal remains rejected at both declared cost points',()=>{assert.equal(p191.state,'PARK');assert.ok(p191.matched_excess_50<0);assert.ok(p191.matched_excess_25<0);assert.ok(p191.positive_folds_50<3);assert.ok(p191.positive_folds_25<3);assert.ok(p191.turnover>0.67)})
test('P192 fixed blend does not rescue the component family',()=>{assert.equal(p192.state,'PARK');assert.ok(p192.matched_excess_50<0);assert.ok(p192.matched_excess_25<0);assert.ok(p192.matched_excess_2020_50<0);assert.equal(p192.positive_folds,1);assert.ok(p192.sharpe<p192.matched_sharpe);assert.equal(family,'P189_P192_SIMPLE_WITHIN_SECTOR_PRICE_FACTOR_FAMILY_EXHAUSTED')})
test('preserve exact terminal execution identities',()=>{assert.deepEqual([p191.run,p191.job,p191.started,p191.artifact],[34428779237,102719579451,'2026-09-10T02:16:14.3522498Z',10133661205]);assert.deepEqual([p192.run,p192.job,p192.started,p192.artifact],[34428862019,102719834013,'2026-09-10T02:17:29.7156371Z',10133691239])})
test('family closure grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
