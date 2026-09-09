import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='0b1941d0d1d899eab4fda9372569b3636b76011b'
const comparison={state:'NONRANKING_P46_P36_EVIDENCE_COMPARISON',roles:['SUPPORTED_CROSSASSET_RESEARCH','SUPPORTED_SEMICONDUCTOR_RESEARCH_RISK_UNRESOLVED'],boundaries:{portfolio_ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,broker:false,live:false}}
test('bind exact MM authority-correction head',()=>assert.equal(MM_PRODUCT_HEAD,'0b1941d0d1d899eab4fda9372569b3636b76011b'))
test('comparison is descriptive and nonranking',()=>{assert.equal(comparison.state,'NONRANKING_P46_P36_EVIDENCE_COMPARISON');assert.deepEqual(comparison.roles,['SUPPORTED_CROSSASSET_RESEARCH','SUPPORTED_SEMICONDUCTOR_RESEARCH_RISK_UNRESOLVED'])})
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values(comparison.boundaries),Array(8).fill(false)))
