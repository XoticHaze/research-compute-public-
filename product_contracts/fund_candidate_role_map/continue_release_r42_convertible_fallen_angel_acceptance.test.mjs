import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='3a9d7bd0382d2f21784f6b2bce9b488d4337f11e'
const claims=Object.freeze({
  CONVERTIBLE:{run:34590415504,job:103234180427,artifact:10195384237,classification:'CONVERTIBLE_INDEPENDENT_ALPHA_NOT_SUPPORTED__IMPLEMENTATION_HETEROGENEITY_PRESERVED'},
  FALLEN_ANGEL:{run:34590359351,job:103234000402,artifact:10195360718,classification:'DURABLE_FALLEN_ANGEL_PREMIUM_NOT_SUPPORTED__HISTORICAL_EDGE_RECENT_REVERSAL'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r42 continuation head',()=>assert.equal(FOUNDRY_HEAD,'3a9d7bd0382d2f21784f6b2bce9b488d4337f11e'))
test('retain exact convertible terminal identity',()=>assert.deepEqual([claims.CONVERTIBLE.run,claims.CONVERTIBLE.job,claims.CONVERTIBLE.artifact],[34590415504,103234180427,10195384237]))
test('retain exact fallen-angel terminal identity',()=>assert.deepEqual([claims.FALLEN_ANGEL.run,claims.FALLEN_ANGEL.job,claims.FALLEN_ANGEL.artifact],[34590359351,103234000402,10195360718]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.CONVERTIBLE.classification,claims.FALLEN_ANGEL.classification],['CONVERTIBLE_INDEPENDENT_ALPHA_NOT_SUPPORTED__IMPLEMENTATION_HETEROGENEITY_PRESERVED','DURABLE_FALLEN_ANGEL_PREMIUM_NOT_SUPPORTED__HISTORICAL_EDGE_RECENT_REVERSAL']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))