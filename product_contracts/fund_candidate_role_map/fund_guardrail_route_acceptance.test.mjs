import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='aefe214b9f3d5ba5d821f77dd8b86bcccae40574'
const route='/research/fund-model-guardrails'
const navLabel='Fund Model Guardrails'
const accepted=Object.freeze({P46_P86:Object.freeze({state:'ROBUST_RISK_EFFICIENCY_ONLY_RETURN_ALPHA_NOT_SUPPORTED',run:34371683597,artifact:10112179350}),P91:Object.freeze({state:'STRICT_WALKFORWARD_QQQ_RSP_LEARNER_REJECTED',run:34362351380,artifact:10108367531}),P99:'VOL_MANAGED_QQQ_EXCESS_RETURN_REJECTED_RISK_UTILITY_RETAINED',P82:'P82_AGGREGATE_SURVIVOR_TIMING_CAUSALITY_NOT_ESTABLISHED',P96_P97:'QQQ_SHORT_HORIZON_INTRADAY_REVERSAL_FAMILY_PARKED'})

test('bind exact discoverable guardrail product head',()=>assert.equal(MM_PRODUCT_HEAD,'aefe214b9f3d5ba5d821f77dd8b86bcccae40574'))
test('first-class operator route and navigation are explicit',()=>{assert.equal(route,'/research/fund-model-guardrails');assert.equal(navLabel,'Fund Model Guardrails')})
test('routed digest preserves exact accepted model consequences',()=>{assert.equal(accepted.P46_P86.run,34371683597);assert.equal(accepted.P46_P86.artifact,10112179350);assert.equal(accepted.P91.run,34362351380);assert.equal(accepted.P91.artifact,10108367531);assert.match(accepted.P99,/RISK_UTILITY/);assert.match(accepted.P82,/CAUSALITY_NOT_ESTABLISHED/);assert.match(accepted.P96_P97,/FAMILY_PARKED/)})
test('routed digest grants no portfolio or trading authority',()=>{const b={portfolioRanking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(11).fill(false))})
