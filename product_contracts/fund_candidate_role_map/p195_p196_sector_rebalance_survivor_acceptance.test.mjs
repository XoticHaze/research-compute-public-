import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='f51541664cf4219ed310e3bb37960977a0b67eca'
const p195=Object.freeze({run:34429370146,job:102721388692,started:'2026-09-10T02:25:14.8708234Z',artifact:10133876307,prior_matched_excess_2010_25:0.010577151378041272,prior_matched_excess_2015_25:0.010448669649134823,state:'SUSPENDED_COMPARATOR_SEMANTICS_DEFECT'})
const p196=Object.freeze({run:34429433770,job:102721583167,started:'2026-09-10T02:26:13.5814479Z',artifact:10133898074,matched_excess_2010_25:-0.007336521097247806,state:'PARK_TRANSPORT_FAILURE_SECONDARY_WHILE_P195_SUSPENDED'})
const p197=Object.freeze({run:34429559762,job:102721974114,started:'2026-09-10T02:28:13.7882316Z',artifact:10133946486,reset_matched_excess_2010_25:-0.0016176562665353167,reset_matched_excess_2015_25:-0.002224544461471467,state:'DIAGNOSTIC_DEFECT_BLOCKER'})
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact corrected MM P195/P197 product head',()=>assert.equal(MM_PRODUCT_HEAD,'f51541664cf4219ed310e3bb37960977a0b67eca'))
test('P197 suspends prior P195 matched-alpha support rather than converting it to a robustness failure',()=>{assert.equal(p195.state,'SUSPENDED_COMPARATOR_SEMANTICS_DEFECT');assert.equal(p197.state,'DIAGNOSTIC_DEFECT_BLOCKER');assert.ok(p195.prior_matched_excess_2010_25>0);assert.ok(p195.prior_matched_excess_2015_25>0);assert.ok(p197.reset_matched_excess_2010_25<0);assert.ok(p197.reset_matched_excess_2015_25<0)})
test('P196 transport failure remains secondary while P195 support is suspended',()=>{assert.equal(p196.state,'PARK_TRANSPORT_FAILURE_SECONDARY_WHILE_P195_SUSPENDED');assert.ok(p196.matched_excess_2010_25<0)})
test('preserve exact P195/P196/P197 execution identities',()=>{assert.deepEqual([p195.run,p195.job,p195.started,p195.artifact],[34429370146,102721388692,'2026-09-10T02:25:14.8708234Z',10133876307]);assert.deepEqual([p196.run,p196.job,p196.started,p196.artifact],[34429433770,102721583167,'2026-09-10T02:26:13.5814479Z',10133898074]);assert.deepEqual([p197.run,p197.job,p197.started,p197.artifact],[34429559762,102721974114,'2026-09-10T02:28:13.7882316Z',10133946486])})
test('suspension grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
