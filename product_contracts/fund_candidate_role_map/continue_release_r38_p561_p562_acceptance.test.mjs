import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='00a57b4ba3bb2205f114142b898ba6c72597cae3'
const claims=Object.freeze({
  P561:{run:34586097515,job:103220556605,artifact:10193642594,classification:'P561_ALPHA_REJECTED_RISK_OVERLAY_PRESERVED'},
  P562:{run:34586223524,job:103220950625,artifact:10193690846,classification:'P562_SUPPORTED_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r38 continuation head',()=>assert.equal(FOUNDRY_HEAD,'00a57b4ba3bb2205f114142b898ba6c72597cae3'))
test('retain exact P561 terminal identity',()=>assert.deepEqual([claims.P561.run,claims.P561.job,claims.P561.artifact],[34586097515,103220556605,10193642594]))
test('retain exact P562 terminal identity',()=>assert.deepEqual([claims.P562.run,claims.P562.job,claims.P562.artifact],[34586223524,103220950625,10193690846]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.P561.classification,claims.P562.classification],['P561_ALPHA_REJECTED_RISK_OVERLAY_PRESERVED','P562_SUPPORTED_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
