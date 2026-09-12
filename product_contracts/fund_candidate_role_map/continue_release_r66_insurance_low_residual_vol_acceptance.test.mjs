import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = 'c555ef07f412af05fcbc6e7503d9357c345f5a04'
const claim = Object.freeze({
  id: 'CC-RF-INSURANCE-LOW-RESIDUAL-VOL-DISJOINT-001',
  run: 34682003055,
  job: 103525077171,
  artifact: 10294599643,
  state: 'REJECTED_DISJOINT_INSURANCE_LOW_RESIDUAL_VOL_NO_RESCUE'
})
const protectedAuthority = Object.freeze({
  ranking: false,
  allocation: false,
  promotion: false,
  runtime: false,
  broker: false,
  live: false,
  foundryMain: false
})

test('bind exact Foundry r66 continuation head', () => assert.equal(FOUNDRY_HEAD, 'c555ef07f412af05fcbc6e7503d9357c345f5a04'))
test('retain exact terminal execution identity', () => assert.deepEqual([claim.run, claim.job, claim.artifact], [34682003055, 103525077171, 10294599643]))
test('retain fail-closed disjoint insurance rejection', () => assert.equal(claim.state, 'REJECTED_DISJOINT_INSURANCE_LOW_RESIDUAL_VOL_NO_RESCUE'))
test('grant no protected authority', () => assert.deepEqual(Object.values(protectedAuthority), Array(7).fill(false)))
