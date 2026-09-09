import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='886594bb07d1a62c157915fda7d3b8b36833446a'
const family={state:'SIX_MONTH_BINARY_RELATIVE_LEADERSHIP_FAMILY_NOT_SUPPORTED_ROTATE_ARCHITECTURE',count:5,blocked:['lookback_horizon','relative_strength_threshold','portfolio_weight','transaction_cost_assumption','nearby_etf_substitution'],next:'MATERIALLY_DIFFERENT_ARCHITECTURE_WITH_INDEPENDENT_SCIENCE'}
test('bind exact P46 portable exclusion product head',()=>assert.equal(MM_PRODUCT_HEAD,'886594bb07d1a62c157915fda7d3b8b36833446a'))
test('portable P46 review carries exact adjacent-family exclusion',()=>{assert.equal(family.count,5);assert.match(family.state,/NOT_SUPPORTED_ROTATE_ARCHITECTURE/);assert.deepEqual(family.blocked,['lookback_horizon','relative_strength_threshold','portfolio_weight','transaction_cost_assumption','nearby_etf_substitution']);assert.match(family.next,/MATERIALLY_DIFFERENT_ARCHITECTURE/)})
test('exclusion cannot become P46 ranking or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
