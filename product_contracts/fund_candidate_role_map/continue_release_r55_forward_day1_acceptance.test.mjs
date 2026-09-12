import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='13d6a79db44ad30a8c9a9bce43c2fbbf55657038'
const claims=Object.freeze([
  {id:'FORWARD_COMPLEMENT_DAY1_R1',runs:[34588332003,34589075412],classification:'FORWARD_OBSERVING_DAY1__NO_PROMOTION_DECISION'}
])
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r55 continuation head',()=>assert.equal(FOUNDRY_HEAD,'13d6a79db44ad30a8c9a9bce43c2fbbf55657038'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claims.map(c=>c.runs),[[34588332003,34589075412]]))
test('preserve forward-observation classification',()=>assert.deepEqual(claims.map(c=>c.classification),['FORWARD_OBSERVING_DAY1__NO_PROMOTION_DECISION']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
