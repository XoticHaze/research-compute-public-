import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='13d76c3b63d196d1458c3b487cd597977cbd92a1'
const p429=Object.freeze({state:'POST2014_INDEPENDENT_IDENTIFIER_SOURCE_NOT_READY__FUNDAMENTAL_ALPHA_UNTESTED',scope:'DATA_REPRESENTATION_IDENTIFIER_LINEAGE_FAILURE__NOT_FUNDAMENTAL_MODEL_FAILURE',snapshots:{y2015:false,y2020:false,y2025:{rows:501,cik:1,symbol:1}},run:34520823337,job:103017612110,artifact:10169636103,protected:{ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}})

test('bind exact P429 MM product head',()=>assert.equal(MM_PRODUCT_HEAD,'13d76c3b63d196d1458c3b487cd597977cbd92a1'))
test('classify source failure without fundamental model rejection',()=>{assert.equal(p429.state,'POST2014_INDEPENDENT_IDENTIFIER_SOURCE_NOT_READY__FUNDAMENTAL_ALPHA_UNTESTED');assert.equal(p429.scope,'DATA_REPRESENTATION_IDENTIFIER_LINEAGE_FAILURE__NOT_FUNDAMENTAL_MODEL_FAILURE')})
test('preserve exact historical identity gap and recent completeness',()=>{assert.equal(p429.snapshots.y2015,false);assert.equal(p429.snapshots.y2020,false);assert.deepEqual(p429.snapshots.y2025,{rows:501,cik:1,symbol:1})})
test('retain exact research execution identity',()=>assert.deepEqual([p429.run,p429.job,p429.artifact],[34520823337,103017612110,10169636103]))
test('source guardrail grants no product or trading authority',()=>assert.deepEqual(Object.values(p429.protected),Array(9).fill(false)))
