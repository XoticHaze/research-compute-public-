import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '35ef3e852f11ba4a898c55f3a28dc19732999c96'
const claim = Object.freeze({
  parent: 'DEVELOPED_EXUS_VALUE_FACTOR_ALPHA',
  child: 'P470_EXUS_VALUE_DOLLAR_REGIME_R1',
  run: 34538940467,
  job: 103076919503,
  artifact: 10176499906,
  digest: '468b46d2f50a242aca09bad7a7f6ecda4e35c63ef0d33501fb059de319afed68',
  classification: 'IMPLEMENTATION_SPECIFIC_CAUSAL_DOLLAR_REGIME_EVIDENCE__NO_UNIVERSAL_PROMOTION'
})
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r17 continuation head',()=>assert.equal(FOUNDRY_HEAD,'35ef3e852f11ba4a898c55f3a28dc19732999c96'))
test('retain exact P470 terminal execution identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34538940467,103076919503,10176499906]))
test('preserve implementation-specific evidence without universal promotion',()=>assert.equal(claim.classification,'IMPLEMENTATION_SPECIFIC_CAUSAL_DOLLAR_REGIME_EVIDENCE__NO_UNIVERSAL_PROMOTION'))
test('require source artifact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
