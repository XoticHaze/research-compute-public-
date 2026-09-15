import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='a02232bef978b3eaa2940712d80d68313ec3a803'
const claim=Object.freeze({run:34580869021,job:103203841448,artifact:10191538178,classification:'P549_NOT_SUPPORTED_NO_RESCUE'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r36 continuation head',()=>assert.equal(FOUNDRY_HEAD,'a02232bef978b3eaa2940712d80d68313ec3a803'))
test('retain exact P549 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34580869021,103203841448,10191538178]))
test('preserve terminal classification',()=>assert.equal(claim.classification,'P549_NOT_SUPPORTED_NO_RESCUE'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
