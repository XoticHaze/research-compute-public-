import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='d2126d970e7c779e69afe66a1f42e8fa7ab3e68a'
const claim=Object.freeze({run:34587887031,job:103226185115,artifact:10194360635,classification:'NOT_SUPPORTED_NO_RESCUE'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r51 continuation head',()=>assert.equal(FOUNDRY_HEAD,'d2126d970e7c779e69afe66a1f42e8fa7ab3e68a'))
test('retain exact labor-claims terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34587887031,103226185115,10194360635]))
test('preserve fail-closed classification',()=>assert.equal(claim.classification,'NOT_SUPPORTED_NO_RESCUE'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))