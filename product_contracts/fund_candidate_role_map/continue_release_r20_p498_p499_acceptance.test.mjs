import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = 'afec3496f6b2813a914525c872372b1363ded9a8'
const claims = Object.freeze([
  Object.freeze({child:'P498_RWJ_FACTOR_RESIDUAL_R1', run:34547608274, job:103103506356, artifact:10179591135, digest:'218e8af74837e9f33607a697814eb860135954c382e6d50c209a3374fc001ae9', classification:'RWJ_REVENUE_RESIDUAL_SURVIVES_SMALL_VALUE_SPREAD_CONTROL'}),
  Object.freeze({child:'P499_PIT_ROE_2021_COVERAGE_R1', run:34547671452, job:103103690788, artifact:10179617753, digest:'81679fe4e7327c72a449e39e05e1b4a35d01fb4509b6fc9b4ca133b6629348ab', classification:'PIT_ROE_2021_BLOCKER_NARROWED_TO_THREE_HISTORICAL_SYMBOL_ENDPOINTS'})
])
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r20 continuation head',()=>assert.equal(FOUNDRY_HEAD,'afec3496f6b2813a914525c872372b1363ded9a8'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claims.map(x=>[x.run,x.job,x.artifact]),[[34547608274,103103506356,10179591135],[34547671452,103103690788,10179617753]]))
test('preserve fail-closed classifications',()=>assert.deepEqual(claims.map(x=>x.classification),['RWJ_REVENUE_RESIDUAL_SURVIVES_SMALL_VALUE_SPREAD_CONTROL','PIT_ROE_2021_BLOCKER_NARROWED_TO_THREE_HISTORICAL_SYMBOL_ENDPOINTS']))
test('require source artifact digests',()=>claims.forEach(x=>assert.match(x.digest,/^[0-9a-f]{64}$/)))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
