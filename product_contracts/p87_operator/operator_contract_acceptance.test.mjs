import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD='6d66946fe784e9e848e5a138018e213982319871'
const operator={route:'/research/crossasset-implementation-risk',nav:'P87 Implementation & Risk',sections:['Implementation robustness','State concentration / opportunity cost','NOT A RISK CONTROL','DIVERSIFICATION EVIDENCE'],protected:['portfolio ranking','allocation','sizing','promotion','StrategySpec mutation','runtime mutation','broker action','live-trading change']}
const states={implementation:'IMPLEMENTATION_ROBUST_STATE_CONCENTRATION_VISIBLE',p95:'REPLICATES_DIRECTION_EDGE_TOO_SMALL_AND_RISK_WORSE',p96:'SERIAL_DIVERSIFICATION_SUPPORTED_CONTROL_BOOTSTRAP_UNRESOLVED'}

test('acceptance is bound to exact MM operator candidate',()=>assert.equal(MM_HEAD,'6d66946fe784e9e848e5a138018e213982319871'))
test('operator contract exposes implementation, concentration, failed-risk-control, and diversification states',()=>{
  assert.equal(operator.route,'/research/crossasset-implementation-risk')
  assert.equal(operator.nav,'P87 Implementation & Risk')
  assert.deepEqual(operator.sections,['Implementation robustness','State concentration / opportunity cost','NOT A RISK CONTROL','DIVERSIFICATION EVIDENCE'])
  assert.equal(states.implementation,'IMPLEMENTATION_ROBUST_STATE_CONCENTRATION_VISIBLE')
  assert.equal(states.p95,'REPLICATES_DIRECTION_EDGE_TOO_SMALL_AND_RISK_WORSE')
  assert.equal(states.p96,'SERIAL_DIVERSIFICATION_SUPPORTED_CONTROL_BOOTSTRAP_UNRESOLVED')
})
test('operator contract preserves all authority boundaries',()=>{
  assert.deepEqual(operator.protected,['portfolio ranking','allocation','sizing','promotion','StrategySpec mutation','runtime mutation','broker action','live-trading change'])
})
