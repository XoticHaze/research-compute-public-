import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='ed3bcffa98c5b7733b24b7f5d19dd072cbba71d0'
const claim={id:'BETA_MATCHED_DEFENSIVE_PREMIA_REJECTED_20260911',runs:[34590261306,34590388104,34590497511],classification:'THREE_FAMILIES_REJECTED_NO_RESCUE'}
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r57 continuation head',()=>assert.equal(FOUNDRY_HEAD,'ed3bcffa98c5b7733b24b7f5d19dd072cbba71d0'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claim.runs,[34590261306,34590388104,34590497511]))
test('preserve fail-closed classification',()=>assert.equal(claim.classification,'THREE_FAMILIES_REJECTED_NO_RESCUE'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
