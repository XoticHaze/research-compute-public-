import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '235f25c13b6a8cfbc48ef263ce29c7beae93c122'
const claims = Object.freeze([
  {child:'P517_VOL_TERM_STRUCTURE_REGIME_R1', run:34555416202, job:103126962426, artifact:10182364389, digest:'07471380c5e95f9ee079a53cda9579c8b6721120497f61775503e97fb2fdb52c', classification:'VOL_TERM_STRUCTURE_REGIME_ALPHA_NOT_SUPPORTED'},
  {child:'P518_INFLATION_REGIME_ALLOCATION_R1', run:34555549801, job:103127369511, artifact:10182414525, digest:'d138bf5902e075df4924d259ce9128892657e034c96e2cb7fee4a49e353d40f2', classification:'INFLATION_REGIME_ALPHA_NOT_SUPPORTED'},
  {child:'P519_FINANCIAL_CONDITIONS_REGIME_R1', run:34555599318, job:103127518725, artifact:10182432132, digest:'1521169e6901e0321c1757665ead26c0bbff327b2beff53a367c0d5e0f499692', classification:'FINANCIAL_CONDITIONS_REGIME_ALPHA_NOT_SUPPORTED'}
])
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r26 continuation head',()=>assert.equal(FOUNDRY_HEAD,'235f25c13b6a8cfbc48ef263ce29c7beae93c122'))
test('retain exact terminal identities',()=>assert.deepEqual(claims.map(c=>[c.run,c.job,c.artifact]),[[34555416202,103126962426,10182364389],[34555549801,103127369511,10182414525],[34555599318,103127518725,10182432132]]))
test('require exact source artifact digests',()=>claims.forEach(c=>assert.match(c.digest,/^[0-9a-f]{64}$/)))
test('preserve terminal classifications',()=>assert.deepEqual(claims.map(c=>c.classification),['VOL_TERM_STRUCTURE_REGIME_ALPHA_NOT_SUPPORTED','INFLATION_REGIME_ALPHA_NOT_SUPPORTED','FINANCIAL_CONDITIONS_REGIME_ALPHA_NOT_SUPPORTED']))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
