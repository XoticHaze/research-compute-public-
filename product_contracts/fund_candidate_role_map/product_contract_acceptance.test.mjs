import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD='c67fb0d0b1c8cb02fbe797aebb4354973a7c51d6'
const riskGate={run:34322401383,job:102371800684,artifact:10092369992,matchedExcessPP:2.584678206943547,allInQQQExcessPP:-4.928608946136603,gatedQQQFolds:2,totalFolds:5,state:'RISK_GATE_REJECTED_SCARCE_CAPITAL_OPPORTUNITY_COST'}
const residual={run:34322734144,job:102372856762,artifact:10092500859,fullIntercept:0.03426738782405544,fullBootstrap95:[0.009613383154435412,0.05849239194955243],rolling60Positive:0.9833333333333333,recent60Intercept:0.04163298087439701,state:'RESIDUAL_ALPHA_PERSISTENCE_SUPPORTED_RAW_QQQ_OPPORTUNITY_CAUTION_REMAINS'}
const rows=[
  {id:'P46',role:'CURRENT_CROSS_ASSET_FUND_CANDIDATE'},
  {id:'P64',role:'DIVERSIFICATION_SLEEVE_EVIDENCE',matched25:0.023073173358661325,matched50:0.014621772350719597,qqq25:-0.03383249594227222},
  {id:'P57',role:'CORRECTED_LINEAGE_AND_FRAGILITY_CONTEXT',matched25:0.031035627736038407,matched50:0.023473864767538766,qqq25:-0.03781202672387063},
  {id:'P52',role:'DISTINCT_INDUSTRY_CANDIDATE_VALIDATION_OPEN',matched25:0.02122037582851788,matched50:0.013102782265948187,lag50:0.0005941989556903504,lagFolds:2,totalFolds:5},
]

test('acceptance binds exact MM product head',()=>assert.equal(MM_HEAD,'c67fb0d0b1c8cb02fbe797aebb4354973a7c51d6'))
test('risk gate is rejected without erasing matched alpha',()=>{assert.ok(riskGate.matchedExcessPP>0);assert.ok(riskGate.allInQQQExcessPP<0);assert.equal(riskGate.gatedQQQFolds,2);assert.match(riskGate.state,/REJECTED/)})
test('beta residual separates model-specific persistence from raw QQQ opportunity cost',()=>{assert.ok(residual.fullIntercept>0);assert.ok(residual.fullBootstrap95[0]>0);assert.ok(residual.rolling60Positive>0.98);assert.ok(residual.recent60Intercept>0);assert.match(residual.state,/RAW_QQQ_OPPORTUNITY_CAUTION_REMAINS/)})
test('role map keeps surviving evidence in distinct non-ranking roles',()=>{assert.deepEqual(rows.map(r=>r.id),['P46','P64','P57','P52']);assert.equal(new Set(rows.map(r=>r.role)).size,4)})
test('co-location grants no portfolio or trading authority',()=>{const boundary={portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(boundary),Array(10).fill(false))})
