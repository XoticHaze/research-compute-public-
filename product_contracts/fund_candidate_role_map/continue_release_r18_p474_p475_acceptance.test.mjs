import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '62a445c194e7b7c067e2602bfa3501a54de8d1a9'
const claims = Object.freeze([
  {child:'P474_LOW_VOL_CORE_CHALLENGER_R1', run:34543222149, job:103090196680, artifact:10178048092, digest:'fd9138547bb735695349080dc023185d78626fc11a81f5d38e9a819c567be6d3', classification:'LOW_VOL_CORE_ALPHA_NOT_SUPPORTED__RISK_SHAPING_ONLY'},
  {child:'P475_REIT_REAL_ASSET_ROLE_R1', run:34543352227, job:103090600797, artifact:10178094165, digest:'24d18579eaa8d20f8e1fb4f3b5e674f62b7631825592580e219ce657957ba557', classification:'REIT_REAL_ASSET_ALPHA_NOT_SUPPORTED__RETURN_ROLE_REJECTED'}
])
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r18 continuation head',()=>assert.equal(FOUNDRY_HEAD,'62a445c194e7b7c067e2602bfa3501a54de8d1a9'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claims.map(c=>[c.run,c.job,c.artifact]),[[34543222149,103090196680,10178048092],[34543352227,103090600797,10178094165]]))
test('preserve fail-closed classifications',()=>assert.deepEqual(claims.map(c=>c.classification),['LOW_VOL_CORE_ALPHA_NOT_SUPPORTED__RISK_SHAPING_ONLY','REIT_REAL_ASSET_ALPHA_NOT_SUPPORTED__RETURN_ROLE_REJECTED']))
test('require source artifact digests',()=>claims.forEach(c=>assert.match(c.digest,/^[0-9a-f]{64}$/)))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
