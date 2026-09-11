import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='3b6b7c3f6010737e8b6c643492d7058ffe2f4e44'
const claim={id:'INDUSTRY_STAGEA_BATCHES6_7_TERMINAL_20260911',runs:[34629990398,34630015750],classification:'BATCH6_PARTIAL_AND_BATCH7_NO_NEW_ADVANCE_FAIL_CLOSED'}
const unscored=['AIRLINES','PAYMENTS','CHEMICALS']
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r61 continuation head',()=>assert.equal(FOUNDRY_HEAD,'3b6b7c3f6010737e8b6c643492d7058ffe2f4e44'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claim.runs,[34629990398,34630015750]))
test('preserve fail-closed batch classification',()=>assert.equal(claim.classification,'BATCH6_PARTIAL_AND_BATCH7_NO_NEW_ADVANCE_FAIL_CLOSED'))
test('preserve local-source unscored families',()=>assert.deepEqual(unscored,['AIRLINES','PAYMENTS','CHEMICALS']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
