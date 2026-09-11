import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '05a237a28c8d829fa7d97ab521d4777496bce541'
const claims = Object.freeze([
  Object.freeze({child:'P514_GARP_DUAL_IMPLEMENTATION_R1', run:34553234498, job:103120297653, artifact:10181564347, digest:'2c70fb75b910acf21a7a4c0dde1a9ad4030fa7c1e07e8d62130b6fb57dfe880d', classification:'GARP_ALPHA_NOT_SUPPORTED'}),
  Object.freeze({child:'P515_ECONOMIC_MOAT_RESIDUAL_R1', run:34553282172, job:103120439807, artifact:10181581774, digest:'ac039754c405425e5dfcc6ebc4047b46e932738872f70a300c7b96820c378df5', classification:'ECONOMIC_MOAT_ALPHA_NOT_SUPPORTED'})
])
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r24 continuation head',()=>assert.equal(FOUNDRY_HEAD,'05a237a28c8d829fa7d97ab521d4777496bce541'))
test('retain exact P514 P515 terminal identities',()=>assert.deepEqual(claims.map(x=>[x.run,x.job,x.artifact]),[[34553234498,103120297653,10181564347],[34553282172,103120439807,10181581774]]))
test('require exact source artifact digests',()=>claims.forEach(x=>assert.match(x.digest,/^[0-9a-f]{64}$/)))
test('preserve terminal rejection classifications',()=>assert.deepEqual(claims.map(x=>x.classification),['GARP_ALPHA_NOT_SUPPORTED','ECONOMIC_MOAT_ALPHA_NOT_SUPPORTED']))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
