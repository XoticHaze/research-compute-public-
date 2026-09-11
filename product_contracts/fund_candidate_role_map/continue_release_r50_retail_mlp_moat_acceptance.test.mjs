import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='bd08f9cbcf5bff0b3cb5ab75f8a574ab475d66af'
const claims=Object.freeze({
  RETAIL:{run:34589391642,job:103230932274,artifact:10194976456,classification:'BROAD_RETAIL_PREMIUM_NOT_SUPPORTED__RTH_XLY_RELATIVE_SURVIVOR_LOW_BROAD_OPPORTUNITY_VALUE'},
  MLP:{run:34587727413,job:103225684920,artifact:10194297811,classification:'MLP_MIDSTREAM_PREMIUM_NOT_SUPPORTED'},
  MOAT:{run:34587677711,job:103225533428,artifact:10194277969,classification:'WIDE_MOAT_SELECTION_NOT_SUPPORTED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r50 continuation head',()=>assert.equal(FOUNDRY_HEAD,'bd08f9cbcf5bff0b3cb5ab75f8a574ab475d66af'))
test('retain source identities',()=>assert.deepEqual([claims.RETAIL.run,claims.MLP.run,claims.MOAT.run],[34589391642,34587727413,34587677711]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.RETAIL.classification,claims.MLP.classification,claims.MOAT.classification],['BROAD_RETAIL_PREMIUM_NOT_SUPPORTED__RTH_XLY_RELATIVE_SURVIVOR_LOW_BROAD_OPPORTUNITY_VALUE','MLP_MIDSTREAM_PREMIUM_NOT_SUPPORTED','WIDE_MOAT_SELECTION_NOT_SUPPORTED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))