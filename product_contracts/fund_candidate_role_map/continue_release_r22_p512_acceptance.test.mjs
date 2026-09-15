import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '727c83cf78d07e009e049b38f1c4879492e34774'
const claim = Object.freeze({child:'P512_PIT_ALIAS_RESOLUTION_R1', run:34552620919, job:103118489176, artifact:10181364142, digest:'6a656a9486484cac10da2d4217552e160411f40818f2c7e2c3724488326dd08c', classification:'FROZEN_2015_ALIAS_GATE_NOT_READY__2_OF_15_RESOLVED_BY_CONTEMPORANEOUS_NAME_ONLY'})
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r22 continuation head',()=>assert.equal(FOUNDRY_HEAD,'727c83cf78d07e009e049b38f1c4879492e34774'))
test('retain exact P512 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34552620919,103118489176,10181364142]))
test('require exact source artifact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('preserve fail-closed identity classification',()=>assert.equal(claim.classification,'FROZEN_2015_ALIAS_GATE_NOT_READY__2_OF_15_RESOLVED_BY_CONTEMPORANEOUS_NAME_ONLY'))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
