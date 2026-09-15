import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='36d354e3d2ca7d689a28d50550afe2e3be1af03e'
const claims=Object.freeze({
  GOLD_MINERS:{run:34590840552,job:103235525120,artifact:10195556256,classification:'GOLD_MINER_OVER_METAL_ALPHA_SUPPORTED_PENDING_ORTHOGONAL_ATTRIBUTION'},
  COVERED_CALL:{run:34590912698,job:103235755061,artifact:10195588094,classification:'COVERED_CALL_ALPHA_REJECTED__DRAWDOWN_SHAPING_ONLY'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r40 continuation head',()=>assert.equal(FOUNDRY_HEAD,'36d354e3d2ca7d689a28d50550afe2e3be1af03e'))
test('retain exact gold-miner terminal identity',()=>assert.deepEqual([claims.GOLD_MINERS.run,claims.GOLD_MINERS.job,claims.GOLD_MINERS.artifact],[34590840552,103235525120,10195556256]))
test('retain exact covered-call terminal identity',()=>assert.deepEqual([claims.COVERED_CALL.run,claims.COVERED_CALL.job,claims.COVERED_CALL.artifact],[34590912698,103235755061,10195588094]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.GOLD_MINERS.classification,claims.COVERED_CALL.classification],['GOLD_MINER_OVER_METAL_ALPHA_SUPPORTED_PENDING_ORTHOGONAL_ATTRIBUTION','COVERED_CALL_ALPHA_REJECTED__DRAWDOWN_SHAPING_ONLY']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))