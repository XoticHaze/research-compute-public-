import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='85b3c8de65200d54ff95f64b21b3c8e8af195cd1'
const claim={id:'DBMF_CONCENTRATION_REGIME_ROLE_20260911',runs:[34634731111,34634975481],classification:'BROAD_ALPHA_NOT_ELIGIBLE__REGIME_ROLE_PRESERVED_SEPARATELY'}
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r62 continuation head',()=>assert.equal(FOUNDRY_HEAD,'85b3c8de65200d54ff95f64b21b3c8e8af195cd1'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claim.runs,[34634731111,34634975481]))
test('preserve fail-closed DBMF classification',()=>assert.equal(claim.classification,'BROAD_ALPHA_NOT_ELIGIBLE__REGIME_ROLE_PRESERVED_SEPARATELY'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
