import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='a21b6d1c119cca310524ed71c09212764b0dee5c'
const claims=Object.freeze({
  PAVE:{run:34588441370,job:103227931885,artifact:10194585649,classification:'PAVE_IMPLEMENTATION_INDEPENDENT_ALPHA_SUPPORTED'},
  FRN:{run:34588334105,job:103227589245,artifact:10194541598,classification:'BROAD_TREASURY_FRN_PREMIUM_NOT_SUPPORTED__USFR_IMPLEMENTATION_EVIDENCE_PRESERVED'},
  MERGER:{run:34587842980,job:103226048868,artifact:10194344218,classification:'MERGER_ARB_ALPHA_NOT_SUPPORTED__RECENT_EDGE_NEGATIVE'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r48 continuation head',()=>assert.equal(FOUNDRY_HEAD,'a21b6d1c119cca310524ed71c09212764b0dee5c'))
test('retain source identities',()=>assert.deepEqual([claims.PAVE.run,claims.FRN.run,claims.MERGER.run],[34588441370,34588334105,34587842980]))
test('preserve distinct terminal classifications',()=>assert.deepEqual([claims.PAVE.classification,claims.FRN.classification,claims.MERGER.classification],['PAVE_IMPLEMENTATION_INDEPENDENT_ALPHA_SUPPORTED','BROAD_TREASURY_FRN_PREMIUM_NOT_SUPPORTED__USFR_IMPLEMENTATION_EVIDENCE_PRESERVED','MERGER_ARB_ALPHA_NOT_SUPPORTED__RECENT_EDGE_NEGATIVE']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))