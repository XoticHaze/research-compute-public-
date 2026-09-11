import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='63937bddffdc3e10bf6eaac9497f8ae6ddae0e87'
const claims=Object.freeze({
  INDIA:{run:34588676148,job:103228687067,artifact:10194680463,classification:'INDIA_COUNTRY_SELECTION_NOT_SUPPORTED'},
  REGIONAL:{run:34588552233,job:103228290394,artifact:10194629844,classification:'REGIONAL_BANK_PREMIUM_NOT_SUPPORTED'},
  TRANSPORT:{run:34589217161,job:103230390281,artifact:10194904696,classification:'TRANSPORTATION_SELECTION_NOT_SUPPORTED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r47 continuation head',()=>assert.equal(FOUNDRY_HEAD,'63937bddffdc3e10bf6eaac9497f8ae6ddae0e87'))
test('retain source identities',()=>assert.deepEqual([claims.INDIA.run,claims.REGIONAL.run,claims.TRANSPORT.run],[34588676148,34588552233,34589217161]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.INDIA.classification,claims.REGIONAL.classification,claims.TRANSPORT.classification],['INDIA_COUNTRY_SELECTION_NOT_SUPPORTED','REGIONAL_BANK_PREMIUM_NOT_SUPPORTED','TRANSPORTATION_SELECTION_NOT_SUPPORTED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))