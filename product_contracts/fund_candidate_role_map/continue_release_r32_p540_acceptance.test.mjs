import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='a78483115bfc28f26d9398dc7e6e202758434075'
const claim=Object.freeze({run:34570773146,job:103172191050,artifact:10187678174,classification:'NOT_SUPPORTED_NO_RESCUE',matchedExcessCagr:-0.023968079865782643,positiveChronologyFolds:0})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r32 continuation head',()=>assert.equal(FOUNDRY_HEAD,'a78483115bfc28f26d9398dc7e6e202758434075'))
test('retain exact P540 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34570773146,103172191050,10187678174]))
test('preserve P540 terminal classification',()=>assert.equal(claim.classification,'NOT_SUPPORTED_NO_RESCUE'))
test('preserve negative matched opportunity result',()=>assert.ok(claim.matchedExcessCagr<0))
test('preserve chronology failure',()=>assert.equal(claim.positiveChronologyFolds,0))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))