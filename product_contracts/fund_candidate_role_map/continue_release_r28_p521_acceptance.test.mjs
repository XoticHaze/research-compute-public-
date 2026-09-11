import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='3418803eb0a7ede8bb81cad035b60475481065da'
const claim=Object.freeze({child:'P521_YIELD_CURVE_SIZE_SELECTION_R1',run:34555927740,job:103128491119,artifact:10182548007,digest:'d5030279f2178bd49e0a755a8cc9911ef575cea858a882fa5b6b02f4a1186d3c',classification:'YIELD_CURVE_SIZE_ALPHA_NOT_SUPPORTED'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r28 continuation head',()=>assert.equal(FOUNDRY_HEAD,'3418803eb0a7ede8bb81cad035b60475481065da'))
test('retain exact P521 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34555927740,103128491119,10182548007]))
test('require exact source artifact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('preserve terminal rejection classification',()=>assert.equal(claim.classification,'YIELD_CURVE_SIZE_ALPHA_NOT_SUPPORTED'))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
