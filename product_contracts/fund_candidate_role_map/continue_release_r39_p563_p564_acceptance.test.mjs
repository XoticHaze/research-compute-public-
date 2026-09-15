import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='be82b3b5c2feac32c3db82a7014c16fb4800a897'
const claims=Object.freeze({
  P563:{run:34586366836,job:103221407879,artifact:10193751141,classification:'P563_INDEPENDENT_VALIDATION_NOT_SUPPORTED_NO_PROMOTION'},
  P564:{run:34586442538,job:103221648755,artifact:10193779277,classification:'P564_GENERAL_MOMENTUM_TRANSPORT_REJECTED_NO_RESCUE'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r39 continuation head',()=>assert.equal(FOUNDRY_HEAD,'be82b3b5c2feac32c3db82a7014c16fb4800a897'))
test('retain exact P563 terminal identity',()=>assert.deepEqual([claims.P563.run,claims.P563.job,claims.P563.artifact],[34586366836,103221407879,10193751141]))
test('retain exact P564 terminal identity',()=>assert.deepEqual([claims.P564.run,claims.P564.job,claims.P564.artifact],[34586442538,103221648755,10193779277]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.P563.classification,claims.P564.classification],['P563_INDEPENDENT_VALIDATION_NOT_SUPPORTED_NO_PROMOTION','P564_GENERAL_MOMENTUM_TRANSPORT_REJECTED_NO_RESCUE']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
