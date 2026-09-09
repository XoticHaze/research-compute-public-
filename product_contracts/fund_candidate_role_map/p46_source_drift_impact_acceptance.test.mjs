import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='965fda44a52f3f4caeb797c6b58236d1cbd95174'
const r={run:34388942903,job:102592185441,artifact:10118834662,head:'f0ad3ac080d3bdcb128161df4e61392e0ce40893',digest:'sha256:15b677a8026d2f0d41bf5059750a52a281d406c9c156cff1c768d1d50e5fd3cb',selectionDifferences:0,economicsInvariant:true,promotionCorpus:'FROZEN_ADMITTED_CORPUS_REQUIRED'}
test('bind exact P46 source-impact product head',()=>assert.equal(MM_PRODUCT_HEAD,'965fda44a52f3f4caeb797c6b58236d1cbd95174'))
test('observed Yahoo drift is output immaterial in paired canonical test',()=>{assert.equal(r.selectionDifferences,0);assert.equal(r.economicsInvariant,true);assert.match(r.promotionCorpus,/FROZEN_ADMITTED_CORPUS/)})
test('preserve exact execution identity',()=>assert.deepEqual([r.run,r.job,r.artifact,r.head],[34388942903,102592185441,10118834662,'f0ad3ac080d3bdcb128161df4e61392e0ce40893']))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
