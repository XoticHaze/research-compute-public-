import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='29d17ad4019e791797af8e01b40770a689de6d9a'
const claims=Object.freeze([
  {id:'FUNDAMENTAL_INDEX_AND_MANAGED_FUTURES_20260911',runs:[34590800573,34590907123,34591020658,34591103475],classification:'FAIL_CLOSED_FAMILIES__DBMF_VALIDATION_CHILD_PARKED'}
])
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r56 continuation head',()=>assert.equal(FOUNDRY_HEAD,'29d17ad4019e791797af8e01b40770a689de6d9a'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claims.map(c=>c.runs),[[34590800573,34590907123,34591020658,34591103475]]))
test('preserve fail-closed and parked classification',()=>assert.deepEqual(claims.map(c=>c.classification),['FAIL_CLOSED_FAMILIES__DBMF_VALIDATION_CHILD_PARKED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
