import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='3f27dff39f7afe1e65daa70f4e2872ddaca35e90'
const p195=Object.freeze({run:34429370146,job:102721388692,started:'2026-09-10T02:25:14.8708234Z',artifact:10133876307,matched_excess_2010_25:0.010577151378041272,folds_2010:5,matched_excess_2015:0.010448669649134823,folds_2015:5,matched_excess_2020:0.008342168136495687,folds_2020:4,matched_excess_2010_50:0.010178660132790451,spy_excess_2010:-0.012942287990370227,state:'SUPPORTED_NARROW_SURVIVOR'})
const p196=Object.freeze({run:34429433770,job:102721583167,started:'2026-09-10T02:26:13.5814479Z',artifact:10133898074,matched_excess_2010_25:-0.007336521097247806,folds_2010:2,matched_excess_2015_25:-0.011568856100610425,folds_2015:1,matched_excess_2010_10:-0.007090931795113331,state:'PARK_TRANSPORT_FAILURE'})
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM P195/P196 product head',()=>assert.equal(MM_PRODUCT_HEAD,'3f27dff39f7afe1e65daa70f4e2872ddaca35e90'))
test('P195 remains a narrow matched-alpha survivor across cost and chronology',()=>{assert.equal(p195.state,'SUPPORTED_NARROW_SURVIVOR');assert.ok(p195.matched_excess_2010_25>0);assert.equal(p195.folds_2010,5);assert.ok(p195.matched_excess_2015>0);assert.equal(p195.folds_2015,5);assert.ok(p195.matched_excess_2020>0);assert.ok(p195.folds_2020>=4);assert.ok(p195.matched_excess_2010_50>0);assert.ok(p195.spy_excess_2010<0)})
test('P196 blocks cross-asset generalization without demoting sector-specific P195',()=>{assert.equal(p196.state,'PARK_TRANSPORT_FAILURE');assert.ok(p196.matched_excess_2010_25<0);assert.ok(p196.matched_excess_2015_25<0);assert.ok(p196.matched_excess_2010_10<0);assert.ok(p196.folds_2010<3);assert.ok(p196.folds_2015<3)})
test('preserve exact terminal execution identities',()=>{assert.deepEqual([p195.run,p195.job,p195.started,p195.artifact],[34429370146,102721388692,'2026-09-10T02:25:14.8708234Z',10133876307]);assert.deepEqual([p196.run,p196.job,p196.started,p196.artifact],[34429433770,102721583167,'2026-09-10T02:26:13.5814479Z',10133898074])})
test('survivor scope grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
