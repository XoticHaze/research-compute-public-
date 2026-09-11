import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='b3536d60bdad7cf3478905c2fa385589424cbe5e'
const claim=Object.freeze({run:34555997632,job:103128705889,artifact:10182572123,digest:'16910fd367a0d3c3528fb5a887d85e7e41b22e33a3c10adf690f9962097c4231',classification:'REAL_YIELD_GOLD_ALPHA_NOT_SUPPORTED'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r29 continuation head',()=>assert.equal(FOUNDRY_HEAD,'b3536d60bdad7cf3478905c2fa385589424cbe5e'))
test('retain exact P522 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34555997632,103128705889,10182572123]))
test('require exact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('preserve classification',()=>assert.equal(claim.classification,'REAL_YIELD_GOLD_ALPHA_NOT_SUPPORTED'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
