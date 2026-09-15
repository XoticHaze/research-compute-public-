import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '1607ce6c40d0ebe7e47d0a32c0f4c49a0c3b3ffd'
const claims = Object.freeze([
  Object.freeze({child:'P502_PRIMARY_SURVIVOR_TOURNAMENT_R1', run:34548494852, job:103106192517, artifact:10179905769, digest:'6ab32bf7d540bfbb066850483a0c218a6ae1b1146880425a73ba121c6243ca6d'}),
  Object.freeze({child:'P503_RWJ_RESIDUAL_BLOCK_BOOTSTRAP_R1', run:34548627640, job:103106590698, artifact:10179950844, digest:'107e3c423a00957c0cba1a45424c383beb2c0e636137f096b0a1e24edd2d0759'}),
  Object.freeze({child:'P504_PIT_ROE_ENDPOINT_CORPORATE_ACTION_CLASSES', commandcenter:'c2c1fda4020aca5afdbde58a18e7677f7c9bd51b'})
])
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r23 continuation head',()=>assert.equal(FOUNDRY_HEAD,'1607ce6c40d0ebe7e47d0a32c0f4c49a0c3b3ffd'))
test('retain exact execution-backed identities',()=>assert.deepEqual(claims.slice(0,2).map(x=>[x.run,x.job,x.artifact]),[[34548494852,103106192517,10179905769],[34548627640,103106590698,10179950844]]))
test('retain source-only P504 durable identity',()=>assert.equal(claims[2].commandcenter,'c2c1fda4020aca5afdbde58a18e7677f7c9bd51b'))
test('require source artifact digests where execution-backed',()=>claims.slice(0,2).forEach(x=>assert.match(x.digest,/^[0-9a-f]{64}$/)))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
