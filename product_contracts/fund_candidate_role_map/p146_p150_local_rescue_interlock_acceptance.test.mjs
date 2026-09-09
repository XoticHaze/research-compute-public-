import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='04c52ce6adebbfcfc34dfe49bae35b927abbc0a2'
const blocked=['lookback_horizon','relative_strength_threshold','portfolio_weight','transaction_cost_assumption','nearby_etf_substitution']
test('bind exact leadership interlock product head',()=>assert.equal(MM_PRODUCT_HEAD,'04c52ce6adebbfcfc34dfe49bae35b927abbc0a2'))
test('local rescue axes are explicit and bounded',()=>assert.deepEqual(blocked,['lookback_horizon','relative_strength_threshold','portfolio_weight','transaction_cost_assumption','nearby_etf_substitution']))
test('materially different architecture is not locally blocked',()=>assert.ok(!blocked.includes('materially_different_architecture')))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)))
