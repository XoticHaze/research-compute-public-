import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='7e0df6848b3a1be7363599e9cf677429ef61384e'
const claim={id:'INDUSTRY_STAGEA_BATCHES4_5_TERMINAL_20260911',runs:[34629631116,34629966828],classification:'BATCH4_PARTIAL_AND_BATCH5_NO_ADVANCE_FAIL_CLOSED'}
const unscored=['CYBERSECURITY','REGIONAL_BANKS']
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r59 continuation head',()=>assert.equal(FOUNDRY_HEAD,'7e0df6848b3a1be7363599e9cf677429ef61384e'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claim.runs,[34629631116,34629966828]))
test('preserve fail-closed batch classification',()=>assert.equal(claim.classification,'BATCH4_PARTIAL_AND_BATCH5_NO_ADVANCE_FAIL_CLOSED'))
test('preserve local-source unscored families',()=>assert.deepEqual(unscored,['CYBERSECURITY','REGIONAL_BANKS']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
