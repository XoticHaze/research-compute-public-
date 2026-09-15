import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='e8f77dac7806b760c297fc0ed6882c5ba7faa9f5'
const claim=Object.freeze({run:34595794225,job:103251118024,artifact:10261597593,classification:'NOT_SUPPORTED_NO_RESCUE'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r53 continuation head',()=>assert.equal(FOUNDRY_HEAD,'e8f77dac7806b760c297fc0ed6882c5ba7faa9f5'))
test('retain exact international-quality terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34595794225,103251118024,10261597593]))
test('preserve fail-closed classification',()=>assert.equal(claim.classification,'NOT_SUPPORTED_NO_RESCUE'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))