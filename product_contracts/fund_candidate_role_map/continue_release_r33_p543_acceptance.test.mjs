import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='f38b6250958e1245a3bd78e2bc3335ed5d3d7589'
const claim=Object.freeze({run:34571301493,job:103173778222,artifact:10187864780,classification:'NOT_SUPPORTED_NO_RESCUE',matchedExcessCagr:-0.010798341257548083,oosMonths:167,positiveChronologyFolds:0})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r33 continuation head',()=>assert.equal(FOUNDRY_HEAD,'f38b6250958e1245a3bd78e2bc3335ed5d3d7589'))
test('retain exact P543 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34571301493,103173778222,10187864780]))
test('preserve P543 terminal classification',()=>assert.equal(claim.classification,'NOT_SUPPORTED_NO_RESCUE'))
test('preserve OOS and matched-control failure',()=>assert.deepEqual([claim.oosMonths,claim.positiveChronologyFolds],[167,0]))
test('preserve negative matched opportunity result',()=>assert.ok(claim.matchedExcessCagr<0))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))