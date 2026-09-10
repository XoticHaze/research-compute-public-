import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = 'b9ad2598516d3d8d2cf7555643fc766671ee72bc'
const claim = Object.freeze({child:'P476_FX_CARRY_ROLE_R1', run:34543532097, job:103091161529, artifact:10178162311, digest:'4ef29ddfae5ac82136244c5bbd057dc5385b2e29805b742a9084448d9a1d18d4', classification:'FX_CARRY_ROLE_NOT_SUPPORTED__EXACT_G10_IMPLEMENTATION_REJECTED'})
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r19 continuation head',()=>assert.equal(FOUNDRY_HEAD,'b9ad2598516d3d8d2cf7555643fc766671ee72bc'))
test('retain exact P476 terminal execution identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34543532097,103091161529,10178162311]))
test('preserve fail-closed FX carry classification',()=>assert.equal(claim.classification,'FX_CARRY_ROLE_NOT_SUPPORTED__EXACT_G10_IMPLEMENTATION_REJECTED'))
test('require source artifact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
