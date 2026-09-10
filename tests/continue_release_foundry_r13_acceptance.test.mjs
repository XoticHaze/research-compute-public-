import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '882149017f961b456db9d3a8a8237d907b9e9419'
const queue = Object.freeze({
  schema: 'foundry.release_acceptance_queue.v1',
  authority: 'RESEARCH_ONLY',
  claims: [
    { parent:'DEVELOPED_EXUS_VALUE_FACTOR_ALPHA', run:34528296423, job:103042511605, artifact:10172445362, digest:'a848a01aea4c9a305288522f2dbdb2d3cecb46fa18f6e92dc5ac601a6a7b5071', classification:'RECENT_EXUS_VALUE_EXCESS_POSITIVE__DURABLE_ALPHA_NOT_SUPPORTED' },
    { parent:'US_DIVIDEND_GROWTH_FUND_ALPHA', run:34528365644, job:103042733603, artifact:10172473245, digest:'66ad7c3ef0e0e5802513ae03eb40be1e287323aa6cd857ccb6f0e6f4752d0cf1', classification:'TWO_IMPLEMENTATION_DIVIDEND_GROWTH_ALPHA_NOT_SUPPORTED' },
    { parent:'SECTOR_SELECTION_FUND_MODEL', run:34528427931, job:103042945280, artifact:10172496253, digest:'d36cc5cfc5c413603f9d987e8ec120a3767ec11e015a572d2fe80dffb8e58a12', classification:'FIXED_SECTOR_ROTATION_ALPHA_NOT_SUPPORTED__DRAWDOWN_CONTEXT_ONLY' }
  ],
  protected: { automatic:false, ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false }
})

test('bind exact Foundry r13 continuation head',()=>assert.equal(FOUNDRY_HEAD,'882149017f961b456db9d3a8a8237d907b9e9419'))
test('retain exact external execution identities',()=>assert.deepEqual(queue.claims.map(x=>[x.run,x.job,x.artifact]),[[34528296423,103042511605,10172445362],[34528365644,103042733603,10172473245],[34528427931,103042945280,10172496253]]))
test('preserve ex-US value as recent-regime evidence not durable alpha',()=>assert.equal(queue.claims[0].classification,'RECENT_EXUS_VALUE_EXCESS_POSITIVE__DURABLE_ALPHA_NOT_SUPPORTED'))
test('preserve dividend-growth rejection',()=>assert.equal(queue.claims[1].classification,'TWO_IMPLEMENTATION_DIVIDEND_GROWTH_ALPHA_NOT_SUPPORTED'))
test('preserve sector-rotation rejection with drawdown context only',()=>assert.equal(queue.claims[2].classification,'FIXED_SECTOR_ROTATION_ALPHA_NOT_SUPPORTED__DRAWDOWN_CONTEXT_ONLY'))
test('require sha256-sized artifact digests',()=>queue.claims.forEach(x=>assert.match(x.digest,/^[0-9a-f]{64}$/)))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(queue.protected),Array(8).fill(false)))
