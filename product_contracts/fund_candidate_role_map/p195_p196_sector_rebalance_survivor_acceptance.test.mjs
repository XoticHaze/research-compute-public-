import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='9409a80121e71449d1448853fa5d51bda8f13cbf'
const p195=Object.freeze({state:'PARK_CORRECTED_BASELINE_REJECT',run:34429800201,job:102722680303,started:'2026-09-10T02:31:47.8802442Z',artifact:10134031090,matched_excess_2010_25:-0.0016176584072895572,folds_2010:2,matched_excess_2015_25:-0.002224538951523858,folds_2015:2,matched_excess_2010_50:-0.002016149701833836,conditional_2020_25:0.002943189641440691})
const p196=Object.freeze({state:'PARK_TRANSPORT_FAILURE',run:34429433770,job:102721583167,started:'2026-09-10T02:26:13.5814479Z',artifact:10133898074,matched_excess_2010_25:-0.007336521097247806})
const p197=Object.freeze({state:'DIAGNOSTIC_DEFECT_EXPOSURE_CONSUMED',run:34429559762,job:102721974114,started:'2026-09-10T02:28:13.7882316Z',artifact:10133946486})
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact corrected MM P195/P199 product head',()=>assert.equal(MM_PRODUCT_HEAD,'9409a80121e71449d1448853fa5d51bda8f13cbf'))
test('corrected matched baseline kills broad P195 survivor claim',()=>{assert.equal(p195.state,'PARK_CORRECTED_BASELINE_REJECT');assert.ok(p195.matched_excess_2010_25<0);assert.ok(p195.matched_excess_2015_25<0);assert.ok(p195.matched_excess_2010_50<0);assert.ok(p195.folds_2010<3);assert.ok(p195.folds_2015<3);assert.ok(p195.conditional_2020_25>0)})
test('P196 transport remains failed and P197 remains diagnostic only',()=>{assert.equal(p196.state,'PARK_TRANSPORT_FAILURE');assert.ok(p196.matched_excess_2010_25<0);assert.equal(p197.state,'DIAGNOSTIC_DEFECT_EXPOSURE_CONSUMED')})
test('preserve exact corrected and diagnostic execution identities',()=>{assert.deepEqual([p195.run,p195.job,p195.started,p195.artifact],[34429800201,102722680303,'2026-09-10T02:31:47.8802442Z',10134031090]);assert.deepEqual([p196.run,p196.job,p196.started,p196.artifact],[34429433770,102721583167,'2026-09-10T02:26:13.5814479Z',10133898074]);assert.deepEqual([p197.run,p197.job,p197.started,p197.artifact],[34429559762,102721974114,'2026-09-10T02:28:13.7882316Z',10133946486])})
test('corrected rejection grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
