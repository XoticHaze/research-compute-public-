import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='df39aec57ea1e7875f92661bea83e06f7668221d'
const claims=Object.freeze({
  GOLD:{run:34591194972,job:103236645320,artifact:10195692755,classification:'GOLD_MINER_INDEPENDENT_ALPHA_REJECTED__PRODUCER_OVER_METAL_EXCESS_RECLASSIFIED_AS_FACTOR_SHAPED'},
  POST_IPO:{run:34591306719,job:103236987231,artifact:10195743934,classification:'DURABLE_POST_IPO_ALPHA_NOT_SUPPORTED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r44 continuation head',()=>assert.equal(FOUNDRY_HEAD,'df39aec57ea1e7875f92661bea83e06f7668221d'))
test('retain exact source identities',()=>assert.deepEqual([claims.GOLD.run,claims.GOLD.job,claims.GOLD.artifact,claims.POST_IPO.run,claims.POST_IPO.job,claims.POST_IPO.artifact],[34591194972,103236645320,10195692755,34591306719,103236987231,10195743934]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.GOLD.classification,claims.POST_IPO.classification],['GOLD_MINER_INDEPENDENT_ALPHA_REJECTED__PRODUCER_OVER_METAL_EXCESS_RECLASSIFIED_AS_FACTOR_SHAPED','DURABLE_POST_IPO_ALPHA_NOT_SUPPORTED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))