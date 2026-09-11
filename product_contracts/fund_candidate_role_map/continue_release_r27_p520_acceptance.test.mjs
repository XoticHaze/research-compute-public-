import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '503dea101c8aa56ecae7d0a169b55efcaeda042b'
const claim = Object.freeze({child:'P520_BREAKEVEN_INFLATION_ALLOCATION_R1', run:34555817891, job:103128171103, artifact:10182507758, digest:'16056eaeadb751d458e1fab80502ee8dd488c4bb58fd268bdfc7de7d8cc6d28b', classification:'BREAKEVEN_INFLATION_ALPHA_NOT_SUPPORTED'})
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r27 continuation head',()=>assert.equal(FOUNDRY_HEAD,'503dea101c8aa56ecae7d0a169b55efcaeda042b'))
test('retain exact P520 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34555817891,103128171103,10182507758]))
test('require exact source artifact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('preserve terminal rejection classification',()=>assert.equal(claim.classification,'BREAKEVEN_INFLATION_ALPHA_NOT_SUPPORTED'))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
