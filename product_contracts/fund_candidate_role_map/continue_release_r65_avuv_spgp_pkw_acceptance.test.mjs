import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='aeecbd4d713969e448f11b37e9c7856ac6eec367'
const claims=[
  {id:'MR_AVUV_BETA_MATCHED_20260911_R1',run:34637352756,state:'REJECTED_RECENT_TRANSPORT_AND_PERSISTENCE_FAILED'},
  {id:'MR_SPGP_BETA_MATCHED_20260911_R1',run:34637438513,state:'REJECTED_MAGNITUDE_RECENT_TRANSPORT_AND_PERSISTENCE_FAILED'},
  {id:'MR_PKW_BUYBACK_ALPHA_20260911_R1',run:34637794711,state:'REJECTED_BROAD_MARKET_OPPORTUNITY_COST_RECENT_TRANSPORT_AND_PERSISTENCE_FAILED'}
]
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r65 continuation head',()=>assert.equal(FOUNDRY_HEAD,'aeecbd4d713969e448f11b37e9c7856ac6eec367'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claims.map(x=>x.run),[34637352756,34637438513,34637794711]))
test('all terminal consequences remain fail-closed rejections',()=>assert.ok(claims.every(x=>x.state.startsWith('REJECTED_'))))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
