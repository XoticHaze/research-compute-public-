import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='09fdd2c15016d423e868b9fe6486dab508d8d76a'
const claim=Object.freeze({run:34580747496,job:103203456969,artifact:10191489244,classification:'P548_NOT_SUPPORTED_NO_RESCUE'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r35 continuation head',()=>assert.equal(FOUNDRY_HEAD,'09fdd2c15016d423e868b9fe6486dab508d8d76a'))
test('retain exact P548 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34580747496,103203456969,10191489244]))
test('preserve terminal classification',()=>assert.equal(claim.classification,'P548_NOT_SUPPORTED_NO_RESCUE'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
