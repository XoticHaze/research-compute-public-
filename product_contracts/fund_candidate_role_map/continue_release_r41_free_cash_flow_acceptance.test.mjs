import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='da7dbf80c164ab459a3f3a870bf0c6acdf5ecfd9'
const claim=Object.freeze({run:34590982689,job:103235978164,artifact:10195611567,classification:'TRANSPORTABLE_FREE_CASH_FLOW_ALPHA_NOT_SUPPORTED__OLDER_CALF_STRENGTH_PRESERVED'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r41 continuation head',()=>assert.equal(FOUNDRY_HEAD,'da7dbf80c164ab459a3f3a870bf0c6acdf5ecfd9'))
test('retain exact free-cash-flow terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34590982689,103235978164,10195611567]))
test('preserve terminal classification',()=>assert.equal(claim.classification,'TRANSPORTABLE_FREE_CASH_FLOW_ALPHA_NOT_SUPPORTED__OLDER_CALF_STRENGTH_PRESERVED'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))